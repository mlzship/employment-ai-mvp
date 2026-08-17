from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")


class MatchRequest(BaseModel):
    batch_id: str = Field(min_length=3, max_length=80)
    job_id: str = Field(min_length=1, max_length=80)
    top_n: int = Field(default=10, ge=1, le=50)


class ReviewRequest(BaseModel):
    match_id: str
    decision: str
    reason: str = Field(default="", max_length=500)


class FeedbackRequest(BaseModel):
    match_id: str
    outcome: str
    reason: str = Field(default="", max_length=500)


def _context(request: Request) -> Any:
    return request.app.state.context


def _user(request: Request) -> dict[str, str]:
    settings = _context(request).settings
    if settings.auth_disabled:
        return {"username": "test-user", "role": "reviewer"}
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def _reviewer(request: Request) -> dict[str, str]:
    user = _user(request)
    if user["role"] != "reviewer":
        raise HTTPException(status_code=403, detail="该操作需要审核人角色")
    return user


@router.get("/healthz")
def health(request: Request) -> dict[str, Any]:
    context = _context(request)
    plugins = request.app.state.registry.status()
    failed = [item["id"] for item in plugins if item["state"] == "failed"]
    return {
        "status": "ok" if not failed else "degraded",
        "database": "ok",
        "plugins": plugins,
        "capabilities": context.services.snapshot(),
    }


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    if request.session.get("user"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "app_name": _context(request).settings.app_name},
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    settings = _context(request).settings
    credentials = {
        "operator": (settings.operator_password, "operator"),
        "reviewer": (settings.reviewer_password, "reviewer"),
    }
    expected = credentials.get(username)
    if not expected or password != expected[0]:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "账号或密码不正确", "app_name": settings.app_name},
            status_code=401,
        )
    request.session.clear()
    request.session["user"] = {"username": username, "role": expected[1]}
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    try:
        user = _user(request)
    except HTTPException:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"user": user, "app_name": _context(request).settings.app_name},
    )


@router.get("/api/plugins")
def list_plugins(request: Request) -> list[dict[str, Any]]:
    _user(request)
    return request.app.state.registry.status()


@router.get("/api/llm/status")
def llm_status(request: Request) -> dict[str, Any]:
    _user(request)
    try:
        return _context(request).services.get("llm.rerank").status()
    except KeyError as exc:
        raise HTTPException(status_code=503, detail="大模型提供方插件未启用") from exc


@router.post("/api/plugins/{plugin_id}/enable")
def enable_plugin(plugin_id: str, request: Request) -> dict[str, Any]:
    user = _reviewer(request)
    try:
        request.app.state.registry.enable(plugin_id, actor=user["username"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"plugin_id": plugin_id, "status": "enabled"}


@router.post("/api/plugins/{plugin_id}/disable")
def disable_plugin(plugin_id: str, request: Request) -> dict[str, Any]:
    user = _reviewer(request)
    try:
        request.app.state.registry.disable(plugin_id, actor=user["username"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"plugin_id": plugin_id, "status": "disabled"}


@router.get("/api/batches")
def list_batches(request: Request) -> list[dict[str, Any]]:
    _user(request)
    return _context(request).db.list_batches()


@router.get("/api/jobs")
def list_jobs(batch_id: str, request: Request) -> list[dict[str, Any]]:
    _user(request)
    return _context(request).db.get_jobs(batch_id)


@router.post("/api/import")
async def import_xlsx(
    request: Request,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    user = _user(request)
    filename = Path(file.filename or "snapshot.xlsx").name
    if Path(filename).suffix.lower() != ".xlsx":
        raise HTTPException(status_code=400, detail="只接受 .xlsx 文件")
    limit = _context(request).settings.max_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=413, detail="上传文件超过大小限制")
    if not content.startswith(b"PK"):
        raise HTTPException(status_code=400, detail="文件内容不是有效的 xlsx 容器")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as handle:
            handle.write(content)
            temporary_path = Path(handle.name)
        return (
            _context(request)
            .services.get("data.source.excel")
            .import_workbook(temporary_path, filename, actor=user["username"])
        )
    except KeyError as exc:
        raise HTTPException(status_code=503, detail="Excel数据源插件未启用") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


@router.post("/api/matches/run")
def run_matches(payload: MatchRequest, request: Request) -> list[dict[str, Any]]:
    user = _user(request)
    try:
        return (
            _context(request)
            .services.get("match.rank")
            .rank(payload.batch_id, payload.job_id, payload.top_n, actor=user["username"])
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/matches")
def list_matches(batch_id: str, job_id: str, request: Request) -> list[dict[str, Any]]:
    _user(request)
    return _context(request).db.list_matches(batch_id, job_id)


@router.post("/api/reviews")
def record_review(payload: ReviewRequest, request: Request) -> dict[str, str]:
    user = _reviewer(request)
    try:
        return (
            _context(request)
            .services.get("review.workflow")
            .review(payload.match_id, payload.decision, payload.reason, actor=user["username"])
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/feedback")
def record_feedback(payload: FeedbackRequest, request: Request) -> dict[str, str]:
    user = _user(request)
    try:
        return (
            _context(request)
            .services.get("feedback.metrics")
            .record(payload.match_id, payload.outcome, payload.reason, actor=user["username"])
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/metrics")
def metrics(batch_id: str, request: Request) -> dict[str, Any]:
    _user(request)
    try:
        return _context(request).services.get("feedback.metrics").metrics(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=503, detail="指标插件未启用") from exc


@router.get("/api/export")
def export_matches(batch_id: str, job_id: str, request: Request) -> Response:
    user = _user(request)
    try:
        content = (
            _context(request)
            .services.get("export.matches")
            .export_csv(batch_id, job_id, actor=user["username"])
        )
    except KeyError as exc:
        raise HTTPException(status_code=503, detail="导出插件未启用") from exc
    safe_job_id = "".join(
        character for character in job_id if character.isalnum() or character in "-_"
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="matches-{safe_job_id}.csv"'},
    )
