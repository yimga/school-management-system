"""Template context processors for platform_runtime."""

from __future__ import annotations

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from apps.platform_runtime.shell_contract import resolve_shell_contract


def rum_ingest_context(request):
    """
    Expose RUM endpoint + token to templates when RUM_INGEST_KEY is configured (>= 16 chars).
    """
    key = (getattr(settings, "RUM_INGEST_KEY", None) or "").strip()
    if len(key) < 16:
        return {"rum_ingest_url": None, "rum_ingest_key": None}
    try:
        path = reverse("rum_ingest")
    except NoReverseMatch:
        return {"rum_ingest_url": None, "rum_ingest_key": None}
    url = request.build_absolute_uri(path)
    return {"rum_ingest_url": url, "rum_ingest_key": key}


def demo_sandbox_banner(request):
    """Expose demo mode for tenant shells (RUNMYCAMPUS_DEMO_SANDBOX, DEMO_MODE, or RUNMYCAMPUS_DEMO_MODE)."""
    enabled = bool(getattr(settings, "RUNMYCAMPUS_DEMO_ENABLED", False))
    return {
        "runmycampus_demo_sandbox": enabled,
        "runmycampus_demo_mode": bool(getattr(settings, "RUNMYCAMPUS_DEMO_MODE", False)),
        "runmycampus_demo_enabled": enabled,
    }


def ai_operating_layer_context(request):
    """
    Operational AI layer: governance summary + optional anomaly nudge (aggregates only).
    """
    school = getattr(request, "school", None)
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False) or school is None:
        return {
            "rmc_ai_governance": None,
            "rmc_ai_anomaly_nudge": None,
        }
    try:
        from apps.platform_runtime.ai_governance import get_public_ai_governance_context
        from apps.platform_runtime.ai_system_layer import generate_anomaly_risk_nudge

        gov = get_public_ai_governance_context(school=school)
        nudge = generate_anomaly_risk_nudge(school, user)
        return {
            "rmc_ai_governance": gov,
            "rmc_ai_anomaly_nudge": nudge,
        }
    except Exception:  # noqa: BLE001
        return {
            "rmc_ai_governance": None,
            "rmc_ai_anomaly_nudge": None,
        }


def shell_contract_context(request):
    """
    Expose ``rmc_shell`` (route/layout/nav classification) to all template renders.

    See ``apps.platform_runtime.shell_contract`` — descriptive only, not authorization.
    """
    return {"rmc_shell": resolve_shell_contract(request)}
