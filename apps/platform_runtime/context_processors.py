"""Template context processors for platform_runtime."""

from __future__ import annotations

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from apps.platform_runtime.rmc_os_shell import resolve_rmc_os_shell
from apps.platform_runtime.shell_contract import resolve_shell_contract
from apps.siteconfig.deploy_meta import build_deploy_freshness_context


def deploy_freshness_context(request):
    """Expose deploy commit + SW cache version for post-deploy reload guard."""
    del request
    return build_deploy_freshness_context()


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
    layout_enabled = bool(
        getattr(settings, "RMC_LAYOUT_OBSERVABILITY_ENABLED", True)
    )
    if len(key) < 16:
        return {
            "rum_ingest_url": None,
            "rum_ingest_key": None,
            "rmc_layout_observability_enabled": layout_enabled,
        }
    try:
        path = reverse("rum_ingest")
    except NoReverseMatch:
        return {
            "rum_ingest_url": None,
            "rum_ingest_key": None,
            "rmc_layout_observability_enabled": layout_enabled,
        }
    url = request.build_absolute_uri(path)
    return {
        "rum_ingest_url": url,
        "rum_ingest_key": key,
        "rmc_layout_observability_enabled": layout_enabled,
    }


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
            "rmc_ai_layer_enabled": False,
        }
    try:
        from apps.platform_runtime.ai_governance import get_public_ai_governance_context
        from apps.platform_runtime.ai_providers import get_ai_runtime_config
        from apps.platform_runtime.ai_system_layer import generate_anomaly_risk_nudge

        # The tenant AI strip is the consolidated AI home. It only renders when the
        # school's AI assistant is enabled — in rules-only mode its rows merely restate
        # richer purpose-built widgets already on the dashboard (operational health strip,
        # onboarding card, ranked-anomaly widget), so showing it then is duplication.
        ai_enabled = bool(get_ai_runtime_config(school=school).get("enabled"))
        gov = get_public_ai_governance_context(school=school)
        nudge = generate_anomaly_risk_nudge(school, user)
        return {
            "rmc_ai_governance": gov,
            "rmc_ai_anomaly_nudge": nudge,
            "rmc_ai_layer_enabled": ai_enabled,
        }
    except Exception:  # noqa: BLE001
        return {
            "rmc_ai_governance": None,
            "rmc_ai_anomaly_nudge": None,
            "rmc_ai_layer_enabled": False,
        }


def zero_click_hub_context(request):
    """Smart Action Hub strip (action_hub_kernel) for authenticated portal users."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"rmc_zero_click_hub": None, "rmc_zero_click_hub_available": False}
    if getattr(request, "public_host_kind", None) == "manager":
        return {"rmc_zero_click_hub": None, "rmc_zero_click_hub_available": False}
    try:
        from apps.platform_runtime.action_engine import infer_primary_audience
        from apps.platform_runtime.action_hub_kernel import resolve_hub_for_audience

        audience = infer_primary_audience(user)
        hub = resolve_hub_for_audience(audience)
        return {
            "rmc_zero_click_hub": hub,
            "rmc_zero_click_hub_available": bool(hub.non_empty_actions),
        }
    except Exception:  # noqa: BLE001
        return {"rmc_zero_click_hub": None, "rmc_zero_click_hub_available": False}


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


def remote_support_context(request):
    """Expose the tenant's open remote-support session for the consent banner.

    Drives ``partials/_remote_support_banner.html``: shows "an operator is
    assisting" transparency + the consent button. One indexed query, guarded.
    RemoteSupportSession is a SHARED (public-schema) model so it reads cleanly
    from tenant context.
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"rmc_remote_support": None}
    school = getattr(request, "school", None)
    if school is None:
        return {"rmc_remote_support": None}
    try:
        from apps.platform_runtime.models_remote_support import (
            RemoteSupportSession,
        )

        session = (
            RemoteSupportSession.objects.filter(
                school_id=school.pk,
                status__in=RemoteSupportSession.OPEN_STATUSES,
            )
            .order_by("-created_at")
            .first()
        )
    except Exception:  # noqa: BLE001
        return {"rmc_remote_support": None}
    if session is None:
        return {"rmc_remote_support": None}
    return {
        "rmc_remote_support": {
            "session_id": str(session.id),
            "status": session.status,
            "needs_consent": (
                session.status == RemoteSupportSession.Status.ACCEPTED
                and not session.consent_satisfied
            ),
            "is_active": session.status == RemoteSupportSession.Status.ACTIVE,
        }
    }


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


def operational_nav_groups(request):
    """Default steering path pills for /super/ operational workbenches."""
    from apps.platform_runtime.super_operational_frames import DEFAULT_SUPER_NAV_GROUPS

    return {"operational_nav_groups": DEFAULT_SUPER_NAV_GROUPS}


def tenant_experience_context(request):
    """Inject next-best actions and AI help routing into tenant templates."""
    school = getattr(request, "school", None)
    user = getattr(request, "user", None)
    if not school or not user or not getattr(user, "is_authenticated", False):
        return {}

    from apps.platform_runtime.tenant_ai_help import (
        build_tenant_ai_help_context,
        offline_help_actions,
    )
    from apps.platform_runtime.tenant_daily_ops import (
        next_best_actions_for_role,
        resolve_action_urls,
    )

    actions = resolve_action_urls(next_best_actions_for_role(school, user))
    ai_ctx = build_tenant_ai_help_context(request)
    offline = offline_help_actions()
    return {
        "tenant_daily_ops_actions": actions,
        "tenant_ai_help": ai_ctx,
        "tenant_offline_help_actions": offline,
    }
