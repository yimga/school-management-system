"""Typed normalization for signup and day-two configuration recommendations.

This module is intentionally independent of Django models and HTTP requests.  It
is the single boundary between untrusted form/stored JSON values and the
deterministic recommendation engine.  Callers choose ``strict=True`` for a new
signup (invalid explicit answers become errors) and the forgiving default when
repairing older persisted manifests (invalid legacy values are recorded and
replaced by safe defaults).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence, TypedDict

IssueSeverity = Literal["warning", "error"]


class InstitutionProfile(TypedDict):
    funding_type: str
    organization_scope: str
    learner_scale: str
    student_capacity: int
    campus_count: int
    staff_count: int
    lms_preference: str
    operating_model: str
    operational_services: list[str]
    connectivity_profile: str
    payment_profile: str
    assessment_profile: str
    identity_profile: str
    data_residency_requirement: str
    accessibility_profile: str
    migration_complexity: str
    automation_preference: str
    go_live_timeline: str
    session_pattern: str
    curriculum_board: str
    governance_profile: str
    migration_vendor: str
    migration_domains: list[str]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    field: str
    code: str
    message: str
    severity: IssueSeverity
    supplied_value: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "supplied_value": self.supplied_value,
        }


@dataclass(frozen=True, slots=True)
class NormalizedInstitutionProfile:
    values: InstitutionProfile
    issues: tuple[ValidationIssue, ...]
    explicit_inputs: tuple[str, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    def issue_payload(self) -> list[dict[str, str]]:
        return [issue.as_dict() for issue in self.issues]


CHOICES: dict[str, frozenset[str]] = {
    "funding_type": frozenset(
        {"", "public", "private", "mission", "charter", "nonprofit", "other"}
    ),
    "organization_scope": frozenset({"single", "district", "network"}),
    "learner_scale": frozenset({"under-1000", "1000-4999", "5000-plus"}),
    "lms_preference": frozenset(
        {
            "none",
            "native",
            "google-classroom",
            "microsoft-teams",
            "canvas",
            "moodle",
            "other",
        }
    ),
    "operating_model": frozenset({"day", "boarding", "mixed"}),
    "connectivity_profile": frozenset(
        {"reliable", "mixed", "limited", "offline-first"}
    ),
    "payment_profile": frozenset(
        {"basic", "cash-only", "online", "multi-channel", "complex-aid"}
    ),
    "assessment_profile": frozenset(
        {"country-default", "national", "competency", "international", "mixed"}
    ),
    "identity_profile": frozenset(
        {"password", "google-sso", "microsoft-sso", "federated", "mixed"}
    ),
    "data_residency_requirement": frozenset(
        {"country-default", "regional", "country-locked", "self-hosted"}
    ),
    "accessibility_profile": frozenset({"standard", "enhanced", "intensive"}),
    "migration_complexity": frozenset(
        {"none", "single-system", "multi-system", "legacy-high-risk"}
    ),
    "automation_preference": frozenset({"guided", "balanced", "automation-first"}),
    "go_live_timeline": frozenset({"exploring", "90-days", "30-days", "urgent"}),
    "session_pattern": frozenset({"single", "double", "continuous"}),
    "governance_profile": frozenset({"standard", "strict"}),
}

LIST_CHOICES: dict[str, frozenset[str]] = {
    "operational_services": frozenset(
        {"boarding", "transport", "cafeteria", "clinic", "athletics"}
    ),
    "migration_domains": frozenset(
        {
            "students",
            "staff",
            "guardians",
            "academics",
            "attendance",
            "grades",
            "fees",
            "discipline",
            "health",
        }
    ),
}

DEFAULTS: dict[str, str] = {
    "funding_type": "",
    "organization_scope": "single",
    "learner_scale": "under-1000",
    "lms_preference": "none",
    "operating_model": "day",
    "connectivity_profile": "mixed",
    "payment_profile": "basic",
    "assessment_profile": "country-default",
    "identity_profile": "password",
    "data_residency_requirement": "country-default",
    "accessibility_profile": "standard",
    "migration_complexity": "none",
    "automation_preference": "balanced",
    "go_live_timeline": "exploring",
    "session_pattern": "single",
    "governance_profile": "standard",
}

_SLUG_CODE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _raw_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _choice(
    field: str,
    raw: Any,
    *,
    strict: bool,
    issues: list[ValidationIssue],
) -> str:
    supplied = _raw_text(raw).lower()
    if not supplied:
        return DEFAULTS[field]
    if supplied in CHOICES[field]:
        return supplied
    issues.append(
        ValidationIssue(
            field=field,
            code="unsupported_choice",
            message=f"Choose a supported value for {field.replace('_', ' ')}.",
            severity="error" if strict else "warning",
            supplied_value=supplied[:120],
        )
    )
    return DEFAULTS[field]


def _bounded_int(
    field: str,
    raw: Any,
    *,
    maximum: int,
    strict: bool,
    issues: list[ValidationIssue],
) -> int:
    text = _raw_text(raw)
    if not text:
        return 0
    try:
        value = int(text)
    except (TypeError, ValueError, OverflowError):
        issues.append(
            ValidationIssue(
                field=field,
                code="invalid_integer",
                message=f"Enter a whole number for {field.replace('_', ' ')}.",
                severity="error" if strict else "warning",
                supplied_value=text[:120],
            )
        )
        return 0
    if value < 0 or value > maximum:
        issues.append(
            ValidationIssue(
                field=field,
                code="out_of_range",
                message=f"{field.replace('_', ' ').title()} must be between 0 and {maximum:,}.",
                severity="error" if strict else "warning",
                supplied_value=text[:120],
            )
        )
        return min(maximum, max(0, value))
    return value


def _list_values(raw: Any) -> list[str]:
    if raw is None:
        return []
    values: Sequence[Any]
    if isinstance(raw, str):
        values = raw.replace("|", ",").split(",")
    elif isinstance(raw, Sequence):
        values = raw
    else:
        values = [raw]
    return list(
        dict.fromkeys(_raw_text(value).lower() for value in values if _raw_text(value))
    )


def _choice_list(
    field: str,
    raw: Any,
    *,
    strict: bool,
    issues: list[ValidationIssue],
) -> list[str]:
    values = _list_values(raw)
    invalid = [value for value in values if value not in LIST_CHOICES[field]]
    if invalid:
        issues.append(
            ValidationIssue(
                field=field,
                code="unsupported_list_choice",
                message=f"Remove unsupported {field.replace('_', ' ')} values.",
                severity="error" if strict else "warning",
                supplied_value=", ".join(invalid)[:120],
            )
        )
    return [value for value in values if value in LIST_CHOICES[field]]


def _slug_code(
    field: str,
    raw: Any,
    *,
    maximum: int,
    strict: bool,
    issues: list[ValidationIssue],
) -> str:
    """Normalize an extensible registry slug while rejecting executable text."""

    supplied = _raw_text(raw).lower()
    if not supplied:
        return ""
    if len(supplied) <= maximum and _SLUG_CODE_RE.fullmatch(supplied):
        return supplied
    issues.append(
        ValidationIssue(
            field=field,
            code="invalid_slug_code",
            message=f"Choose a supported {field.replace('_', ' ')} value.",
            severity="error" if strict else "warning",
            supplied_value=supplied[:120],
        )
    )
    return ""


def normalize_institution_profile(
    raw: Mapping[str, Any] | None,
    *,
    strict: bool = False,
) -> NormalizedInstitutionProfile:
    """Normalize untrusted profile input without ever raising on bad values."""

    source: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    issues: list[ValidationIssue] = []
    explicit = tuple(
        sorted(
            str(key)
            for key, value in source.items()
            if _raw_text(value) or (isinstance(value, Sequence) and bool(value))
        )
    )
    values: InstitutionProfile = {
        "funding_type": _choice("funding_type", source.get("funding_type"), strict=strict, issues=issues),
        "organization_scope": _choice("organization_scope", source.get("organization_scope"), strict=strict, issues=issues),
        "learner_scale": _choice("learner_scale", source.get("learner_scale"), strict=strict, issues=issues),
        "student_capacity": _bounded_int("student_capacity", source.get("student_capacity"), maximum=1_000_000, strict=strict, issues=issues),
        "campus_count": _bounded_int("campus_count", source.get("campus_count"), maximum=10_000, strict=strict, issues=issues),
        "staff_count": _bounded_int("staff_count", source.get("staff_count"), maximum=1_000_000, strict=strict, issues=issues),
        "lms_preference": _choice("lms_preference", source.get("lms_preference"), strict=strict, issues=issues),
        "operating_model": _choice("operating_model", source.get("operating_model"), strict=strict, issues=issues),
        "operational_services": _choice_list("operational_services", source.get("operational_services"), strict=strict, issues=issues),
        "connectivity_profile": _choice("connectivity_profile", source.get("connectivity_profile"), strict=strict, issues=issues),
        "payment_profile": _choice("payment_profile", source.get("payment_profile"), strict=strict, issues=issues),
        "assessment_profile": _choice("assessment_profile", source.get("assessment_profile"), strict=strict, issues=issues),
        "identity_profile": _choice("identity_profile", source.get("identity_profile"), strict=strict, issues=issues),
        "data_residency_requirement": _choice("data_residency_requirement", source.get("data_residency_requirement"), strict=strict, issues=issues),
        "accessibility_profile": _choice("accessibility_profile", source.get("accessibility_profile"), strict=strict, issues=issues),
        "migration_complexity": _choice("migration_complexity", source.get("migration_complexity"), strict=strict, issues=issues),
        "automation_preference": _choice("automation_preference", source.get("automation_preference"), strict=strict, issues=issues),
        "go_live_timeline": _choice("go_live_timeline", source.get("go_live_timeline"), strict=strict, issues=issues),
        "session_pattern": _choice("session_pattern", source.get("session_pattern"), strict=strict, issues=issues),
        "curriculum_board": _slug_code("curriculum_board", source.get("curriculum_board"), maximum=32, strict=strict, issues=issues),
        "governance_profile": _choice("governance_profile", source.get("governance_profile"), strict=strict, issues=issues),
        "migration_vendor": _raw_text(source.get("migration_vendor"))[:120].lower(),
        "migration_domains": _choice_list("migration_domains", source.get("migration_domains"), strict=strict, issues=issues),
    }

    # Backward-compatible inference: a boarding operating model necessarily
    # requires the boarding service even when an older client omitted the new
    # multi-select field.
    if values["operating_model"] in {"boarding", "mixed"}:
        values["operational_services"] = list(
            dict.fromkeys(["boarding", *values["operational_services"]])
        )
    if values["organization_scope"] != "single" and values["campus_count"] == 0:
        values["campus_count"] = 2
        issues.append(
            ValidationIssue(
                field="campus_count",
                code="inferred_multi_campus_count",
                message="Campus count was inferred as 2 and can be reviewed before provisioning.",
                severity="warning",
            )
        )
    if values["student_capacity"] == 0 and _raw_text(source.get("learner_scale")):
        inferred_capacity = {
            "under-1000": 500,
            "1000-4999": 1_500,
            "5000-plus": 5_000,
        }[values["learner_scale"]]
        values["student_capacity"] = inferred_capacity
        issues.append(
            ValidationIssue(
                field="student_capacity",
                code="inferred_capacity_from_band",
                message=(
                    f"Expected learners was inferred as {inferred_capacity:,} from the selected "
                    "scale band and can be refined before provisioning."
                ),
                severity="warning",
            )
        )
    return NormalizedInstitutionProfile(
        values=values,
        issues=tuple(issues),
        explicit_inputs=explicit,
    )


__all__ = [
    "CHOICES",
    "DEFAULTS",
    "InstitutionProfile",
    "LIST_CHOICES",
    "NormalizedInstitutionProfile",
    "ValidationIssue",
    "normalize_institution_profile",
]
