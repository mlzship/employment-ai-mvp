from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from employment_ai.core.context import AppContext
from employment_ai.core.database import Database
from employment_ai.core.events import EventBus
from employment_ai.core.registry import PluginRegistry
from employment_ai.core.services import ServiceContainer
from employment_ai.plugins.catalog import built_in_plugins
from employment_ai.settings import Settings
from employment_ai.web.routes import router

PACKAGE_ROOT = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active_settings.validate_security()
        active_settings.ensure_runtime()
        database = Database(active_settings.database_path)
        database.init_schema()
        context = AppContext(
            settings=active_settings,
            db=database,
            events=EventBus(),
            services=ServiceContainer(),
        )
        registry = PluginRegistry(context)
        for plugin in built_in_plugins():
            registry.register(plugin)
        registry.enable_all(active_settings.disabled_plugins)
        app.state.context = context
        app.state.registry = registry

        if (
            active_settings.auto_seed
            and database.batch_count() == 0
            and active_settings.seed_xlsx.exists()
            and context.services.has("data.source.excel")
        ):
            context.services.get("data.source.excel").import_workbook(
                active_settings.seed_xlsx,
                active_settings.seed_xlsx.name,
                actor="system:auto-seed",
            )
        try:
            yield
        finally:
            registry.shutdown()

    app = FastAPI(
        title=active_settings.app_name,
        version="0.2.0",
        docs_url="/docs" if active_settings.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=active_settings.session_secret,
        same_site="lax",
        https_only=active_settings.cookie_secure,
        max_age=8 * 60 * 60,
    )

    @app.middleware("http")
    async def security_headers(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.mount(
        "/static",
        StaticFiles(directory=PACKAGE_ROOT / "web/static"),
        name="static",
    )
    app.include_router(router)
    return app


app = create_app()
