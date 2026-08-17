from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from employment_ai.core.context import AppContext
from employment_ai.core.contracts import Plugin, PluginManifest

EDUCATION_LEVELS = ("小学", "初中", "高中", "中专", "大专", "本科", "硕士", "博士")
SKILL_LEVELS = ("无", "初级", "中级", "高级", "技师", "高级技师")
EMPLOYMENT_STATUSES = ("在职", "求职中", "失业", "灵活就业")
SHIFTS = ("白班", "两班倒", "三班倒", "不限")

PERSON_REQUIRED = (
    "person_id",
    "education",
    "skills",
    "employment_status",
    "expected_salary_min",
    "expected_salary_max",
    "preferred_region",
    "town",
    "years_experience",
    "available_shift",
    "source_updated_at",
)
JOB_REQUIRED = (
    "job_id",
    "employer_name",
    "job_title",
    "region",
    "salary_min",
    "salary_max",
    "education_min",
    "experience_min",
    "required_skills",
    "industry",
    "shift",
    "headcount",
    "valid_until",
    "status",
)


@dataclass(slots=True)
class QualityReport:
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": self.errors, "warnings": self.warnings}


def _issue(
    sheet: str,
    row: int,
    field: str,
    code: str,
    message: str,
    severity: str = "error",
) -> dict[str, Any]:
    return {
        "sheet": sheet,
        "row": row,
        "field": field,
        "code": code,
        "message": message,
        "severity": severity,
    }


class DataQualityService:
    def validate(self, people: list[dict[str, Any]], jobs: list[dict[str, Any]]) -> QualityReport:
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        person_ids: set[str] = set()
        job_ids: set[str] = set()

        if not people:
            errors.append(_issue("person_snapshot", 1, "*", "EMPTY_SHEET", "人员表为空"))
        if not jobs:
            errors.append(_issue("job_snapshot", 1, "*", "EMPTY_SHEET", "岗位表为空"))

        for index, person in enumerate(people, start=2):
            for field in PERSON_REQUIRED:
                if person.get(field) in (None, "", []):
                    errors.append(
                        _issue("person_snapshot", index, field, "REQUIRED", f"{field}不能为空")
                    )
            person_id = str(person.get("person_id", ""))
            if person_id in person_ids:
                errors.append(
                    _issue(
                        "person_snapshot",
                        index,
                        "person_id",
                        "DUPLICATE_ID",
                        f"person_id重复：{person_id}",
                    )
                )
            person_ids.add(person_id)
            if person.get("education") not in EDUCATION_LEVELS:
                errors.append(
                    _issue(
                        "person_snapshot",
                        index,
                        "education",
                        "INVALID_ENUM",
                        "学历枚举无效",
                    )
                )
            if person.get("skill_level", "无") not in SKILL_LEVELS:
                errors.append(
                    _issue(
                        "person_snapshot",
                        index,
                        "skill_level",
                        "INVALID_ENUM",
                        "技能等级枚举无效",
                    )
                )
            if person.get("employment_status") not in EMPLOYMENT_STATUSES:
                errors.append(
                    _issue(
                        "person_snapshot",
                        index,
                        "employment_status",
                        "INVALID_ENUM",
                        "就业状态枚举无效",
                    )
                )
            if person.get("available_shift") not in SHIFTS:
                errors.append(
                    _issue(
                        "person_snapshot",
                        index,
                        "available_shift",
                        "INVALID_ENUM",
                        "班次枚举无效",
                    )
                )
            minimum = person.get("expected_salary_min")
            maximum = person.get("expected_salary_max")
            if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)):
                if minimum < 0 or maximum < minimum:
                    errors.append(
                        _issue(
                            "person_snapshot",
                            index,
                            "expected_salary_min",
                            "INVALID_RANGE",
                            "期望薪资区间无效",
                        )
                    )
            if person.get("employment_status") == "在职":
                warnings.append(
                    _issue(
                        "person_snapshot",
                        index,
                        "employment_status",
                        "CURRENTLY_EMPLOYED",
                        "在职人员默认不进入候选池",
                        "warning",
                    )
                )

        for index, job in enumerate(jobs, start=2):
            for field in JOB_REQUIRED:
                if job.get(field) in (None, "", []):
                    errors.append(
                        _issue("job_snapshot", index, field, "REQUIRED", f"{field}不能为空")
                    )
            job_id = str(job.get("job_id", ""))
            if job_id in job_ids:
                errors.append(
                    _issue(
                        "job_snapshot",
                        index,
                        "job_id",
                        "DUPLICATE_ID",
                        f"job_id重复：{job_id}",
                    )
                )
            job_ids.add(job_id)
            if job.get("education_min") not in EDUCATION_LEVELS:
                errors.append(
                    _issue(
                        "job_snapshot",
                        index,
                        "education_min",
                        "INVALID_ENUM",
                        "最低学历枚举无效",
                    )
                )
            if job.get("shift") not in SHIFTS:
                errors.append(
                    _issue("job_snapshot", index, "shift", "INVALID_ENUM", "班次枚举无效")
                )
            minimum = job.get("salary_min")
            maximum = job.get("salary_max")
            if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)):
                if minimum < 0 or maximum < minimum:
                    errors.append(
                        _issue(
                            "job_snapshot",
                            index,
                            "salary_min",
                            "INVALID_RANGE",
                            "岗位薪资区间无效",
                        )
                    )
            if job.get("status") not in ("active", "closed"):
                errors.append(
                    _issue("job_snapshot", index, "status", "INVALID_ENUM", "岗位状态无效")
                )
            valid_until = str(job.get("valid_until", ""))[:10]
            try:
                if valid_until and date.fromisoformat(valid_until) < date.today():
                    warnings.append(
                        _issue(
                            "job_snapshot",
                            index,
                            "valid_until",
                            "EXPIRED_JOB",
                            "岗位已过有效期，不进入匹配",
                            "warning",
                        )
                    )
            except ValueError:
                errors.append(
                    _issue(
                        "job_snapshot",
                        index,
                        "valid_until",
                        "INVALID_DATE",
                        "岗位有效期格式应为YYYY-MM-DD",
                    )
                )

        return QualityReport(errors=errors, warnings=warnings)


class DataQualityPlugin(Plugin):
    manifest = PluginManifest(
        id="data-quality",
        version="1.0.0",
        name="数据质量门",
        description="校验必填、枚举、范围、重复ID和岗位有效期，错误定位到行/字段",
        provides=("data.quality",),
        permissions=("snapshot:read",),
        events_out=("data.quality.checked",),
        cleanup_strategy="remove validation service; imported snapshots remain immutable",
    )

    def install(self, context: AppContext) -> None:
        context.services.register("data.quality", self.manifest.id, DataQualityService())
