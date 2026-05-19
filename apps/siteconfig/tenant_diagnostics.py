"""Tenant Health & Diagnostic Canvas — self-service checks for school administrators."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.schools.tenant_access import has_school_permission, user_belongs_to_school

# Core modules used for adoption scoring (subset of get_tenant_modules).
_ADOPTION_PROBE_CODES = (
    "attendance",
    "grades",
    "academics",
    "finance",
    "reports",
    "portal",
    "people",
    "communication",
)


def compute_adoption_dimension(school) -> int:
    """0–100 adoption score from enabled tenant modules (replaces hardcoded 70)."""
    if school is None:
        return 0
    try:
        from apps.siteconfig.tenant_config import get_tenant_modules

        modules = [str(m).strip().lower() for m in (get_tenant_modules(school) or []) if m]
    except (ImportError, AttributeError, TypeError, ValueError):
        modules = []
    if not modules:
        addons = getattr(school, "addons", None) or []
        if isinstance(addons, list):
            modules = [str(x).strip().lower() for x in addons if x]
    if not modules:
        return 25
    hits = 0
    for probe in _ADOPTION_PROBE_CODES:
        if any(probe in mod or mod in probe for mod in modules):
            hits += 1
    return min(100, 25 + int((hits / len(_ADOPTION_PROBE_CODES)) * 75))


def run_tenant_diagnostics(request) -> dict[str, Any]:
    """
    Run instant diagnostic checks for the active tenant session.

    Returns a structured payload the Tenant Health & Diagnostic Canvas renders.
    """
    user = getattr(request, "user", None)
    school = getattr(request, "school", None)
    checks: list[dict[str, Any]] = []

    def add(
        key: str,
        label: str,
        status: str,
        detail: str,
        *,
        remedy_url: str = "",
        remedy_label: str = "",
    ) -> None:
        checks.append(
            {
                "key": key,
                "label": label,
                "status": status,
                "detail": detail,
                "remedy_url": remedy_url,
                "remedy_label": remedy_label,
            }
        )

    if school is None:
        add(
            "tenant_context",
            "Tenant context",
            "fail",
            "No school bound to this request. Session school_id may be missing.",
        )
        return {"checks": checks, "overall": "fail", "school_id": None}

    add(
        "tenant_context",
        "Tenant context",
        "pass",
        f"Active school: {school.name} ({getattr(school, 'slug', '') or school.pk}).",
    )

    if not user or not user.is_authenticated:
        add("auth", "Authentication", "fail", "Sign in required.")
        return {"checks": checks, "overall": "fail", "school_id": str(school.pk)}

    if user_belongs_to_school(user, school):
        add("membership", "School membership", "pass", "User is a member of this school.")
    else:
        add(
            "membership",
            "School membership",
            "fail",
            "User is not a member of this school — rosters and grades will be empty.",
        )

    for action, label in (
        ("view", "View data"),
        ("edit", "Edit records"),
        ("export", "Export data"),
        ("admin", "Administer settings"),
    ):
        ok = has_school_permission(user, school, action)  # type: ignore[arg-type]
        add(
            f"perm_{action}",
            label,
            "pass" if ok else "warn",
            "Allowed for your role." if ok else "Not granted for your role on this school.",
        )

    adoption = compute_adoption_dimension(school)
    add(
        "adoption",
        "Module adoption",
        "pass" if adoption >= 60 else "warn",
        f"Adoption score {adoption}/100 from enabled modules.",
        remedy_url="/siteconfig/configuration/runtime/",
        remedy_label="Runtime configuration",
    )

    try:
        from apps.customersuccess.services import compute_tenant_health_score

        score, dimensions = compute_tenant_health_score(school)
        dim_adoption = dimensions.get("adoption", adoption)
        add(
            "health_score",
            "Tenant health score",
            "pass" if float(score) >= 60 else "warn",
            f"Composite {score}/100 (activity={dimensions.get('activity')}, "
            f"workflows={dimensions.get('workflows')}, adoption={dim_adoption}).",
            remedy_url="/siteconfig/zero-ticket/health/",
            remedy_label="Health dashboard",
        )
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        add("health_score", "Tenant health score", "warn", f"Could not compute: {exc}")

    last = getattr(school, "last_activity", None)
    if last:
        days = (timezone.now() - last).days
        add(
            "last_activity",
            "Last platform activity",
            "pass" if days <= 14 else "warn",
            f"Last activity {days} day(s) ago.",
        )
    else:
        add(
            "last_activity",
            "Last platform activity",
            "warn",
            "No recorded activity — verify teachers are signing in.",
        )

    overall = "pass"
    if any(c["status"] == "fail" for c in checks):
        overall = "fail"
    elif any(c["status"] == "warn" for c in checks):
        overall = "warn"

    return {
        "checks": checks,
        "overall": overall,
        "school_id": str(school.pk),
        "generated_at": timezone.now().isoformat(),
    }
