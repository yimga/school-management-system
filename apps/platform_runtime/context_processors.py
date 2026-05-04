"""Template context processors for platform_runtime."""

from __future__ import annotations

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from apps.platform_runtime.rmc_os_shell import resolve_rmc_os_shell
from apps.platform_runtime.shell_contract import resolve_shell_contract


def click_tracking_context(request):
    """
    Tenant click instrumentation: POST ingest URL + phase label for deliberate activation telemetry.

    See apps.platform_runtime.click_tracking for definitions and acceptance gates.
    """
    phase = (getattr(settings, "CLICK_MEASUREMENT_PHASE", None) or "current").strip().lower()
    if phase not in ("baseline", "current"):
        phase = "current"
    out: dict = {
        "click_measurement_phase": phase,
        "click_tracking_ingest_url": None,
        "click_measurement_dashboard_url": None,
    }
    user = getattr(request, "user", None)
    school = getattr(request, "school", None)
    if not user or not getattr(user, "is_authenticated", False) or school is None:
        return out
    try:
        out["click_tracking_ingest_url"] = reverse("record_click_event")
        out["click_measurement_dashboard_url"] = reverse("click_measurement_dashboard")
    except NoReverseMatch:
        pass
    return out


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
    from urllib.parse import urlencode

    from apps.schools.host_routing import get_canonical_base_domain

    enabled = bool(getattr(settings, "RUNMYCAMPUS_DEMO_ENABLED", False))
    out: dict = {
        "runmycampus_demo_sandbox": enabled,
        "runmycampus_demo_mode": bool(getattr(settings, "RUNMYCAMPUS_DEMO_MODE", False)),
        "runmycampus_demo_enabled": enabled,
        "demo_create_school_url": None,
        "demo_parent_child_results_url": None,
    }
    if not enabled:
        return out

    scheme = "https"
    if getattr(settings, "MARKETING_BASE_SCHEME", None):
        scheme = str(getattr(settings, "MARKETING_BASE_SCHEME", "https"))
    elif getattr(request, "scheme", None):
        scheme = request.scheme
    base = f"{scheme}://{get_canonical_base_domain()}"
    params: dict[str, str] = {"ref": "demo"}
    school = getattr(request, "school", None)
    if school and getattr(school, "name", None):
        sn = (school.name or "").strip()[:200]
        if sn:
            params["school_name"] = sn
    out["demo_create_school_url"] = f"{base.rstrip('/')}/signup/?{urlencode(params)}"

    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        role = (getattr(user, "role", None) or "").upper()
        if role == "PARENT":
            from apps.people.models import StudentGuardian

            link = (
                StudentGuardian.objects.filter(
                    guardian_user=user, can_view_results=True
                )
                .order_by("id")
                .first()
            )
            if link:
                try:
                    out["demo_parent_child_results_url"] = reverse(
                        "portal:parent_child_results",
                        kwargs={"student_id": link.student_id},
                    )
                except NoReverseMatch:
                    pass
    return out


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


def system_actions_context(request):
    """
    Cross-cutting next actions for dashboard strips (apps.platform_runtime.action_engine).

    Uses tenant ``request.school`` when present; otherwise staff users get control-plane actions.
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"rmc_system_actions": [], "rmc_system_actions_available": False}
    try:
        from apps.platform_runtime.action_engine import (
            get_actions_for_user,
            serialize_actions,
        )

        school = getattr(request, "school", None)
        from django.conf import settings as dj_settings

        lim = (
            1
            if getattr(dj_settings, "CONVERSION_SINGLE_ACTION_ENFORCED", False)
            else 6
        )
        actions = get_actions_for_user(user, school, request=request, limit=lim)
        ser = serialize_actions(actions)
        return {
            "rmc_system_actions": ser,
            "rmc_system_actions_available": bool(ser),
        }
    except Exception:  # noqa: BLE001
        return {"rmc_system_actions": [], "rmc_system_actions_available": False}


def offline_sync_bar_context(request):
    """
    Lightweight queue counts for the offline status bar (``offline_sync_status_bar.html``).

    Merges sync_engine/mobile counts with tenant ``OfflineAction`` rows when ``request.school`` is set.
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"rmc_offline_sync_state": None}
    try:
        from apps.platform_runtime.offline_queue import get_merged_sync_bar_state

        school = getattr(request, "school", None)
        sid = school.pk if school is not None else None
        return {"rmc_offline_sync_state": get_merged_sync_bar_state(user.pk, sid)}
    except Exception:  # noqa: BLE001
        return {"rmc_offline_sync_state": None}


def shell_contract_context(request):
    """
    Expose ``rmc_shell`` (route/layout/nav classification) to all template renders.

    See ``apps.platform_runtime.shell_contract`` — descriptive only, not authorization.
    """
    return {"rmc_shell": resolve_shell_contract(request)}


def rmc_os_shell_context(request):
    """RunMyCampus OS shell markers (role cluster, page slug, surface kind)."""
    shell = resolve_rmc_os_shell(request)
    try:
        from apps.platform_runtime.rmc_os_nav_registry import job_clusters_for

        shell = {
            **shell,
            "nav_job_clusters": job_clusters_for(shell.get("role_cluster", "")),
        }
    except Exception:  # noqa: BLE001
        shell = {**shell, "nav_job_clusters": ()}
    return {"rmc_os_shell": shell}
