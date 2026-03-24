"""
LMS + district roster certification rows for super One SIS surface (single source of truth).

Status values: Certified | In progress | Adapter shipped (native vendor API client in repo).
"""

from __future__ import annotations

from typing import Any, Final

LMS_CERTIFICATION_ROWS: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "Google Classroom / Workspace",
        "status": "Certified",
        "api_surface": "LTI 1.3, OIDC, Workspace roster",
    },
    {
        "name": "Microsoft Teams / 365",
        "status": "Certified",
        "api_surface": "LTI 1.3, Entra OIDC",
    },
    {
        "name": "Canvas",
        "status": "Certified",
        "api_surface": "LTI 1.3 AGS, REST provisioning",
    },
    {
        "name": "D2L Brightspace",
        "status": "In progress",
        "api_surface": "LTI 1.3, Brightspace API",
    },
    {
        "name": "Moodle",
        "status": "Certified",
        "api_surface": "LTI 1.3, OAuth 2 service",
    },
    {
        "name": "Blackboard Learn Ultra",
        "status": "In progress",
        "api_surface": "LTI 1.3, REST learn admin",
    },
    {
        "name": "Clever (API v3.1 — district bearer)",
        "status": "Adapter shipped",
        "api_surface": "GET /users, /schools, /sections; OAuth code exchange",
    },
    {
        "name": "ClassLink (OneRoster v1p1 host)",
        "status": "Adapter shipped",
        "api_surface": "Bearer /users, /courses; per-district base URL",
    },
)


def list_lms_certification_rows() -> tuple[dict[str, str], ...]:
    return LMS_CERTIFICATION_ROWS


def row_badge_class(status: str) -> str:
    if status == "Certified":
        return "bg-success"
    if status == "Adapter shipped":
        return "bg-info text-dark"
    return "bg-warning text-dark"


def as_template_rows() -> list[dict[str, Any]]:
    return [
        {**r, "badge_class": row_badge_class(r["status"])} for r in LMS_CERTIFICATION_ROWS
    ]
