# -*- coding: utf-8 -*-
"""
Studio OS shared services: preview, publish/rollback, activity, recommendations.
One model for all modes. Unified preview URL is the single entry point for embed/preview per mode.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError
from django.db.models import ObjectDoesNotExist
from django.urls import NoReverseMatch

from apps.platform_runtime.structured_logging import (
    log_exception_with_context,
    request_context_for_log,
)

logger = logging.getLogger(__name__)

# §2.4 Typed exceptions for optional/audit paths (no broad except).
_STUDIO_SOFT_FAILURES = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    ObjectDoesNotExist,
    DatabaseError,
    NoReverseMatch,
)

# §4.2–4.6 Plan "Must support" checklist (RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).
# Experience: ExperiencePack, theme tokens, portal shell layouts, dashboard visual packs, school website blocks,
#   communication style packs, role/device preview, compare, publish/rollback, website brand import, AI recommendations.
# Automation: visual builder, natural-language workflow generation, simulation engine, dependency graph,
#   conflict detection, staged activation, replay/rollback, workflow health metrics.
# Output: ReportPack, DocumentPack, sample-data preview, branding inheritance, signature requirements,
#   retention/lifecycle controls, dependency graph, publish/rollback.
# Launch: create school, select plan, recommend blueprint, import branding, choose starter stack, choose migration path,
#   preview by role, launch checklist, setup health score, launch confidence summary.
# Control: capability management, runtime/source tracing, policy/entitlement/pack/integration governance,
#   registry overlays, metadata governance, diff/impact summary, rollback/staged rollout, AI cleanup suggestions.

# Mode -> (reverse_name, query_param). Single source for Studio embed/preview URLs.
STUDIO_MODE_EMBED_TARGETS = {
    "experience": ("siteconfig:theme_colors", "embed=1"),
    "automation": ("studio_os:workflow_center", "embed=1"),
    "output": ("studio_os:output", "embed=1"),
    "launch": ("siteconfig:guided_onboarding", "embed=1"),
    "control": ("siteconfig:feature_control_panel", "embed=1"),
}


def get_studio_preview_url(mode: str, request: Any = None) -> str:
    """
    Unified preview/embed URL for the given Studio mode. Use this instead of
    building embed URLs ad hoc so preview engine behavior is consistent and
    single-sourced (e.g. ?embed=1 for iframe, no redirect back to Studio).
    """
    from django.urls import NoReverseMatch, reverse

    target = STUDIO_MODE_EMBED_TARGETS.get((mode or "").strip().lower())
    if not target:
        return ""
    name, qs = target
    try:
        base = reverse(name)
        out = f"{base}?{qs}" if qs else base
    except NoReverseMatch:
        from apps.studio_os.deep_links import studio_resolve_url

        base = studio_resolve_url(name, request=request)
        if not base:
            return ""
        out = f"{base}?{qs}" if qs else base
    if request is not None:
        from apps.studio_os.deep_links import url_is_cross_origin_request

        if url_is_cross_origin_request(request, out):
            return ""
    return out


def get_studio_preview_context(mode: str, request: Any = None) -> dict[str, Any]:
    """
    §5.6 Live Previews: optional impact summary and dependency warnings for preview API.
    §4.6 Control Studio: diff/impact summary so client can show governance impact without a second request.
    For mode=launch, returns health_summary, recommended_next, impact_summary, dependency_warnings.
    For mode=control, returns impact_summary (governance/runtime impact).
    Other modes may be extended later.
    """
    out: dict[str, Any] = {}
    mode_key = (mode or "").strip().lower()

    if mode_key == "control":
        # §4.6 Control Studio optional: diff/impact summary for governance preview
        out["impact_summary"] = (
            "Review feature toggles and runtime state before publishing. "
            "Use Runtime inspector for impact and source tracing."
        )
        out["dependency_warnings"] = []
        return out

    if mode_key == "automation":
        out["workflow_simulation_hint"] = (
            "Use Workflow center simulations before activating changes; "
            "review staging vs production package stages in Automation Studio."
        )
        out["staging_vs_production_note"] = (
            "Installed packages may be sandbox or production — promote before treating workflows as live."
        )
        out["publish_rollback_readiness_note"] = (
            "Publish when staged activation checks pass; rollback requires governed APIs or session snapshots."
        )
        out["dependency_warnings"] = []
        return out

    if mode_key != "launch":
        return out
    school = getattr(request, "school", None) if request else None
    if not school:
        return out
    try:
        from apps.setup_studio.services import get_setup_studio_payload

        payload = get_setup_studio_payload(school)
        out["health_summary"] = payload.get("health_summary")
        out["recommended_next"] = payload.get("recommended_next")
        # §5.6: impact summary (launch readiness and blockers)
        launch_blockers = payload.get("launch_blockers") or []
        launch_ready = payload.get("launch_ready", False)
        impact_parts = []
        if launch_ready:
            impact_parts.append("Launch ready; run final previews before go-live.")
        elif launch_blockers:
            impact_parts.append(
                f"{len(launch_blockers)} blocker(s) must be cleared before launch."
            )
        if impact_parts:
            out["impact_summary"] = " ".join(impact_parts)
        else:
            out["impact_summary"] = (
                payload.get("health_summary", {}).get("detail") or "Review setup steps."
            )
        # §5.6: dependency warnings (blockers as dependency-style warnings)
        out["dependency_warnings"] = [
            {
                "key": b.get("key"),
                "label": b.get("label"),
                "detail": b.get("detail") or b.get("label"),
            }
            for b in launch_blockers
            if isinstance(b, dict)
        ][:10]
    except _STUDIO_SOFT_FAILURES as e:
        ctx = request_context_for_log(request) if request else {}
        log_exception_with_context(
            "Studio preview context (launch) failed",
            exc_info=False,
            extra={"studio_mode": "launch", "error": str(e), **ctx},
        )
    return out


def get_studio_activity_feed(request, limit: int = 15) -> list[dict[str, Any]]:
    """
    Recent Studio-relevant actions: theme publishes, feature control changes, workflow runs, etc.
    Reuses FeatureControlAudit and theme_recent_change_meta; can be extended.
    """
    from django.urls import NoReverseMatch, reverse

    def _safe(name: str) -> str | None:
        try:
            return reverse(name)
        except NoReverseMatch:
            return None

    feed = []
    school = getattr(request, "school", None)
    if not school:
        return feed

    # Theme recent change (session)
    theme_meta = request.session.get("theme_recent_change_meta")
    if theme_meta and theme_meta.get("status") == "saved":
        url = _safe("studio_os:experience")
        if not url:
            return feed[:limit]
        feed.append(
            {
                "kind": "theme_publish",
                "label": "Theme & experience published",
                "timestamp": theme_meta.get("timestamp", ""),
                "actor": theme_meta.get("actor", ""),
                "detail": f"{theme_meta.get('changed_count', 0)} fields",
                "url": url,
            }
        )

    # Feature control audit (last N)
    try:
        from apps.siteconfig.models_dashboard import FeatureControlAudit

        control_url = _safe("studio_os:control")
        for entry in FeatureControlAudit.objects.select_related("user").order_by(
            "-created_at"
        )[:limit]:
            if not control_url:
                break
            feed.append(
                {
                    "kind": "feature_control",
                    "label": "Feature control"
                    + (" reverted" if entry.action == "revert" else " saved"),
                    "timestamp": entry.created_at.strftime("%Y-%m-%d %H:%M")
                    if entry.created_at
                    else "",
                    "actor": entry.user.get_username() if entry.user else "system",
                    "detail": entry.action or "save",
                    "url": control_url,
                }
            )
    except _STUDIO_SOFT_FAILURES as e:
        logger.debug("Studio activity: feature control audit unavailable: %s", e)

    # §4.1 Extend to package/workflow: recent InstalledPackage apply (if any)
    try:
        from apps.packages.models import InstalledPackage

        pkg_url = _safe("studio_os:control")
        # tenant-isolation-allow: studio_os control-plane activity feed (reviewed 2026-05-14)
        for pkg in InstalledPackage.objects.filter(is_active=True).order_by(
            "-applied_at"
        )[:5]:
            if not pkg_url:
                break
            feed.append(
                {
                    "kind": "package_apply",
                    "label": f"Package {pkg.package_id}@{pkg.version} applied",
                    "timestamp": pkg.applied_at.strftime("%Y-%m-%d %H:%M")
                    if pkg.applied_at
                    else "",
                    "actor": str(pkg.applied_by_id) if pkg.applied_by_id else "system",
                    "detail": pkg.apply_stage or "production",
                    "url": pkg_url,
                }
            )
    except _STUDIO_SOFT_FAILURES as e:
        logger.debug("Studio activity: package feed unavailable: %s", e)

    # Sort by timestamp desc (simplified: theme first then audit then package)
    return feed[:limit]


def get_studio_role_preview_entries(request: Any) -> list[dict[str, Any]]:
    """
    §4.1 Unified role/device preview switcher. Returns list of {role, label, url} for shell.
    Uses Launch payload when available; otherwise minimal role list with preview links.
    """
    from django.urls import NoReverseMatch, reverse

    school = getattr(request, "school", None)
    if not school:
        return []
    try:
        from apps.setup_studio.services import get_setup_studio_payload

        payload = get_setup_studio_payload(school)
        role_previews = payload.get("role_previews") or []
        if isinstance(role_previews, list) and role_previews:
            return [
                {
                    "role": r.get("role", ""),
                    "label": r.get("label", r.get("role", "")),
                    "url": r.get("url", ""),
                }
                for r in role_previews
                if isinstance(r, dict)
            ][:8]
    except _STUDIO_SOFT_FAILURES as e:
        logger.debug("Studio role preview entries: %s", e)

    # Fallback: minimal role list
    def _safe(name: str) -> str:
        try:
            return reverse(name)
        except NoReverseMatch:
            return ""

    from apps.studio_os.deep_links import studio_resolve_url

    def _role_url(name: str) -> str:
        try:
            return reverse(name)
        except NoReverseMatch:
            return studio_resolve_url(name) or "#"

    return [
        {
            "role": "principal",
            "label": "Principal",
            "url": _role_url("accounts:backend_dashboard"),
        },
        {
            "role": "teacher",
            "label": "Teacher",
            "url": _role_url("accounts:backend_dashboard"),
        },
        {
            "role": "parent",
            "label": "Parent",
            "url": _role_url("portal:parent_dashboard"),
        },
    ]


STUDIO_MODE_DECK_META: dict[str, dict[str, str]] = {
    "experience": {"icon": "bi-palette2", "url_name": "studio_os:experience"},
    "automation": {"icon": "bi-diagram-3", "url_name": "studio_os:automation"},
    "output": {"icon": "bi-file-earmark-richtext", "url_name": "studio_os:output"},
    "launch": {"icon": "bi-rocket-takeoff", "url_name": "studio_os:launch"},
    "control": {"icon": "bi-sliders2", "url_name": "studio_os:control"},
}


def get_studio_overview_deck(
    request: Any,
    *,
    modes: list[dict[str, Any]],
    recommendations: list[dict[str, Any]] | None = None,
    activity_feed: list[dict[str, Any]] | None = None,
    legacy_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Studio home (/studio/) command deck: mode cards, tenant context, quick stats, hub links.
    """
    from django.urls import NoReverseMatch, reverse
    from django.utils.translation import gettext as _

    from apps.schools.control_plane import use_control_plane_shell

    legacy_urls = legacy_urls or {}
    recommendations = recommendations or []
    activity_feed = activity_feed or []

    mode_cards: list[dict[str, Any]] = []
    for index, mode in enumerate(modes, start=1):
        mode_id = (mode.get("id") or "").strip().lower()
        meta = STUDIO_MODE_DECK_META.get(mode_id, {})
        url = ""
        url_name = meta.get("url_name") or ""
        if url_name:
            try:
                url = reverse(url_name)
            except NoReverseMatch:
                from apps.studio_os.deep_links import studio_resolve_url

                url = studio_resolve_url(url_name, request=request) or ""
        mode_cards.append(
            {
                "id": mode_id,
                "label": mode.get("label", ""),
                "description": mode.get("description", ""),
                "url": url,
                "icon": meta.get("icon", "bi-box"),
                "shortcut_digit": str(index) if index <= 5 else "",
            }
        )

    tenant_banner = None
    tenant_context = None
    if use_control_plane_shell(request) and not getattr(request, "school", None):
        try:
            schools_url = reverse("super:schools_list")
        except NoReverseMatch:
            try:
                schools_url = reverse("super:dashboard")
            except NoReverseMatch:
                schools_url = ""
        tenant_banner = {
            "title": _("Pick a tenant for live preview"),
            "detail": _(
                "Theme, launch, and experience embeds need a selected school. "
                "Browse tenants, open one, then return to Studio."
            ),
            "cta_url": schools_url,
            "cta_label": _("Browse tenants"),
        }
    else:
        school = getattr(request, "school", None)
        if school is not None:
            tenant_context = {
                "name": getattr(school, "name", "") or str(school),
                "slug": getattr(school, "slug", "") or "",
            }

    hub_specs = (
        ("approval_hub", _("Approval hub"), "bi-check2-circle"),
        ("workflow_center", _("Workflow center"), "bi-bezier2"),
        ("import_hub", _("Import hub"), "bi-box-arrow-in-down"),
        ("document_library", _("Document library"), "bi-folder2-open"),
        ("report_library", _("Report library"), "bi-journal-text"),
        ("rbac", _("RBAC & permissions"), "bi-shield-lock"),
        ("feature_control", _("Feature control"), "bi-toggles"),
        ("communication_groups", _("Message groups"), "bi-chat-dots"),
    )
    operational_hubs: list[dict[str, str]] = []
    for key, label, icon in hub_specs:
        url = legacy_urls.get(key) or ""
        if url:
            operational_hubs.append({"label": label, "url": url, "icon": icon})

    return {
        "mode_cards": mode_cards,
        "tenant_banner": tenant_banner,
        "tenant_context": tenant_context,
        "quick_stats": [
            {"label": _("Work modes"), "value": str(len(modes))},
            {"label": _("Suggestions"), "value": str(len(recommendations))},
            {"label": _("Recent items"), "value": str(len(activity_feed))},
        ],
        "operational_hubs": operational_hubs,
        "show_command_hint": True,
    }


def get_studio_operator_toolbar(request: Any, *, current_mode: str | None = None) -> dict[str, Any] | None:
    """
    Manager Studio toolbar: in-shell tenant switcher + live preview strip (session school_id).
    """
    from django.urls import NoReverseMatch, reverse

    from apps.schools.control_plane import use_control_plane_shell
    from apps.schools.models import School
    from apps.schools.tenant_url import build_tenant_backend_url

    if not use_control_plane_shell(request):
        return None

    try:
        set_school_url = reverse("studio_os:set_operator_school")
    except NoReverseMatch:
        set_school_url = ""

    schools: list[dict[str, Any]] = []
    try:
        for row in School.objects.filter(is_active=True).order_by("name").values(
            "id", "name", "slug"
        )[:80]:
            schools.append(
                {
                    "id": str(row["id"]),
                    "name": row["name"] or "",
                    "slug": row["slug"] or "",
                }
            )
    except _STUDIO_SOFT_FAILURES as e:
        logger.debug("Studio operator toolbar schools: %s", e)

    school = getattr(request, "school", None)
    if school is None:
        session_sid = (getattr(request, "session", None) or {}).get("school_id")
        if session_sid:
            try:
                school = School.objects.filter(pk=session_sid, is_active=True).first()
            except (TypeError, ValueError, DatabaseError):
                school = None
    selected_id = str(school.pk) if school is not None else ""
    live_preview = None
    mode_key = (current_mode or "").strip().lower()
    if school is not None:
        portal_url = ""
        try:
            portal_url = build_tenant_backend_url(request, school, "/authentication/backend/")
        except (TypeError, ValueError, AttributeError):
            portal_url = ""
        embed_preview_url = get_studio_preview_url(mode_key, request) if mode_key else ""
        live_preview = {
            "school_name": getattr(school, "name", "") or str(school),
            "school_slug": getattr(school, "slug", "") or "",
            "portal_url": portal_url,
            "embed_preview_url": embed_preview_url,
            "mode": mode_key,
            "has_embed": bool(embed_preview_url),
        }

    return {
        "set_school_url": set_school_url,
        "schools": schools,
        "selected_school_id": selected_id,
        "live_preview": live_preview,
        "return_path": (getattr(request, "path", None) or "/studio/"),
    }


def get_studio_mode_hero_context(
    mode: str,
    request: Any,
    *,
    legacy_urls: dict[str, str] | None = None,
    launch_payload: dict[str, Any] | None = None,
    theme_contrast_report: dict[str, Any] | None = None,
    output_readiness_summary: dict[str, Any] | None = None,
    automation_primary_url: str | None = None,
    automation_secondary_url: str | None = None,
    automation_health_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Template kwargs for studio_os/partials/_mode_hero.html on manager + tenant shells."""
    from django.utils.translation import gettext as _

    from apps.schools.control_plane import use_control_plane_shell

    legacy_urls = legacy_urls or {}
    mode_key = (mode or "").strip().lower()
    school = getattr(request, "school", None)
    needs_tenant = use_control_plane_shell(request) and school is None

    if mode_key == "experience":
        hero: dict[str, Any] = {
            "mode_label": _("Experience"),
            "mode_purpose": _(
                "Brand identity, theme packs, and portal layout. "
                "Changes flow through the configurability cascade so the tenant brand wins."
            ),
            "primary_cta_url": legacy_urls.get("theme_colors") or "",
            "primary_cta_label": _("Theme & colors"),
            "secondary_cta_url": legacy_urls.get("customizer") or "",
            "secondary_cta_label": _("Customizer"),
        }
        if theme_contrast_report:
            ok = theme_contrast_report.get("status") == "ok"
            hero["mode_health_label"] = (
                _("Contrast: pass") if ok else _("Contrast: check")
            )
            hero["mode_health_status"] = "ok" if ok else "warn"
        elif needs_tenant:
            hero["mode_health_label"] = _("Select tenant for live theme")
            hero["mode_health_status"] = "warn"
        return hero

    if mode_key == "launch":
        hero = {
            "mode_label": _("Launch"),
            "mode_purpose": _(
                "Plan, role-preview, and infrastructure for going live. "
                "Guided onboarding is the fastest path."
            ),
            "primary_cta_url": legacy_urls.get("guided_onboarding") or "",
            "primary_cta_label": _("Guided onboarding"),
        }
        payload = launch_payload if isinstance(launch_payload, dict) else {}
        if payload:
            score = payload.get("health_score", 0)
            hero["mode_health_label"] = f"{score}% ready"
            hero["mode_health_status"] = (
                "ok" if payload.get("launch_ready") else "warn"
            )
        elif needs_tenant:
            hero["mode_health_label"] = _("Select tenant for launch data")
            hero["mode_health_status"] = "warn"
        return hero

    if mode_key == "automation":
        hero = {
            "mode_label": _("Automation"),
            "mode_purpose": _(
                "Workflows, approvals, simulation, and staged activation. "
                "Run outcomes in the canvas; use the sidebar to jump between tools."
            ),
            "primary_cta_url": automation_primary_url
            or legacy_urls.get("workflow_hub")
            or "",
            "primary_cta_label": _("Workflow center"),
            "secondary_cta_url": automation_secondary_url
            or legacy_urls.get("workflow_flow_gallery")
            or "",
            "secondary_cta_label": _("Simulation engine"),
        }
        summary = (
            automation_health_summary
            if isinstance(automation_health_summary, dict)
            else {}
        )
        if summary.get("service_online"):
            failing = int(summary.get("failing_count") or 0)
            paused = int(summary.get("paused_count") or 0)
            if failing:
                hero["mode_health_label"] = _("{count} failed runs").format(
                    count=failing
                )
                hero["mode_health_status"] = "warn"
            elif paused:
                hero["mode_health_label"] = _("{count} paused packs").format(
                    count=paused
                )
                hero["mode_health_status"] = "warn"
            else:
                hero["mode_health_label"] = _("Workflows healthy")
                hero["mode_health_status"] = "ok"
        elif needs_tenant:
            hero["mode_health_label"] = _("Select tenant for workflow context")
            hero["mode_health_status"] = "warn"
        return hero

    if mode_key == "output":
        hero = {
            "mode_label": _("Outputs"),
            "mode_purpose": _(
                "Reports, documents, credentials, and branding inheritance. "
                "Everything publishes through governed output packs."
            ),
            "primary_cta_url": legacy_urls.get("report_library") or "",
            "primary_cta_label": _("Report library"),
            "secondary_cta_url": legacy_urls.get("reportcard_builder") or "",
            "secondary_cta_label": _("Report builder"),
        }
        summary = (
            output_readiness_summary
            if isinstance(output_readiness_summary, dict)
            else {}
        )
        if summary.get("service_online"):
            missing = int(summary.get("packs_missing_deps") or 0)
            if missing:
                hero["mode_health_label"] = _("{count} packs need dependencies").format(
                    count=missing
                )
                hero["mode_health_status"] = "warn"
            else:
                hero["mode_health_label"] = _("Outputs ready")
                hero["mode_health_status"] = "ok"
        elif needs_tenant:
            hero["mode_health_label"] = _("Select tenant for output preview")
            hero["mode_health_status"] = "warn"
        return hero

    if mode_key == "control":
        hero = {
            "mode_label": _("Control"),
            "mode_purpose": _(
                "Capabilities, feature flags, audit, and platform governance. "
                "Review impact before rollback."
            ),
            "primary_cta_url": legacy_urls.get("feature_control") or "",
            "primary_cta_label": _("Feature control"),
            "secondary_cta_url": legacy_urls.get("rbac") or "",
            "secondary_cta_label": _("RBAC & permissions"),
        }
        if needs_tenant:
            hero["mode_health_label"] = _("Platform-wide control plane")
            hero["mode_health_status"] = "ok"
        return hero

    return {}


def get_studio_recommendations(request, mode: str | None) -> list[dict[str, Any]]:
    """
    Next-best-action recommendations for the shell. Mode-specific when current_mode is set.
    """
    from django.urls import NoReverseMatch, reverse

    from apps.studio_os.deep_links import studio_resolve_url

    def _url(name: str) -> str | None:
        try:
            return reverse(name)
        except NoReverseMatch:
            u = studio_resolve_url(name, request=request)
            return u or None

    recs = []
    school = getattr(request, "school", None)
    if not school:
        return recs

    if mode == "launch":
        try:
            from apps.setup_studio.services import get_setup_studio_payload

            payload = get_setup_studio_payload(school)
            rec = payload.get("recommended_next") or payload.get("health_summary")
            if rec:
                if isinstance(rec, dict):
                    direct = (rec.get("link") or "").strip()
                    if direct and direct != "#":
                        url = direct
                    else:
                        url = _url("studio_os:launch")
                    if url:
                        recs.append(
                            {
                                "label": rec.get("label", "Launch"),
                                "detail": rec.get("detail", "")
                                or rec.get("description", "")
                                or rec.get("evidence", ""),
                                "url": url,
                                "tone": rec.get("tone", "neutral"),
                            }
                        )
                else:
                    url = _url("studio_os:launch")
                    if url:
                        recs.append(
                            {
                                "label": "Launch",
                                "detail": str(rec),
                                "url": url,
                                "tone": "neutral",
                            }
                        )
            if payload.get("launch_blockers"):
                url = _url("studio_os:launch")
                if url:
                    recs.append(
                        {
                            "label": "Resolve launch blockers",
                            "detail": f"{len(payload['launch_blockers'])} blocker(s)",
                            "url": url,
                            "tone": "risk",
                        }
                    )
        except _STUDIO_SOFT_FAILURES as e:
            logger.debug("Studio recommendations: launch payload unavailable: %s", e)

    if mode == "experience":
        url = _url("studio_os:experience")
        if url:
            recs.append(
                {
                    "label": "Check contrast",
                    "detail": "Use Live preview and confirm accessibility before publishing.",
                    "url": url,
                    "tone": "neutral",
                }
            )

    if mode == "control":
        url = _url("siteconfig:feature_control_audit")
        if url:
            recs.append(
                {
                    "label": "Review audit",
                    "detail": "Check feature control audit before rolling back.",
                    "url": url,
                    "tone": "neutral",
                }
            )

    if not mode or mode == "overview":
        url = _url("studio_os:shell")
        if url:
            recs.append(
                {
                    "label": "Open Studio",
                    "detail": "Choose a mode to shape experience, automate, publish, launch, or govern.",
                    "url": url,
                    "tone": "neutral",
                }
            )

    return recs[:5]


def get_studio_command_palette_entries(request) -> list[dict[str, Any]]:
    """Commands for global search / command palette. Resolves to Studio modes or actions."""
    from django.urls import NoReverseMatch, reverse

    from apps.studio_os.deep_links import studio_resolve_url

    def _safe(name: str) -> str | None:
        try:
            return reverse(name)
        except NoReverseMatch:
            return studio_resolve_url(name, request=request) or None

    entries = []

    def _add(label: str, url_name: str, *, keywords: str) -> None:
        url = _safe(url_name)
        if not url:
            return
        entries.append(
            {
                "label": label,
                "url": url,
                "keywords": keywords,
            }
        )

    _add(
        "Change school branding",
        "studio_os:experience",
        keywords="brand theme colors experience",
    )
    _add(
        "Preview parent portal",
        "portal:parent_dashboard",
        keywords="preview parent portal",
    )
    _add(
        "Install attendance workflow",
        "studio_os:automation",
        keywords="install attendance workflow automation",
    )
    _add(
        "Open fee reminder automation",
        "studio_os:automation",
        keywords="fee reminder automation workflow",
    )
    _add(
        "Configure grade reports",
        "studio_os:output",
        keywords="grade reports configure output reports",
    )
    _add("Set up grade reports", "studio_os:output", keywords="reports output")
    try:
        out_base = reverse("studio_os:output")
        entries.append(
            {
                "label": "Document library (Output Studio)",
                "url": f"{out_base}?pane=documents",
                "keywords": "documents files library output upload retention",
            }
        )
        entries.append(
            {
                "label": "Report library & letters (Output Studio)",
                "url": f"{out_base}?pane=reports",
                "keywords": "report library packs bulk letters output reports",
            }
        )
        entries.append(
            {
                "label": "Report card builder",
                "url": f"{out_base}?pane=builder",
                "keywords": "report card builder grades term annual",
            }
        )
    except NoReverseMatch:
        pass
    _add(
        "Configuration Control Center",
        "siteconfig:console_domains_hub",
        keywords="config center configuration domains hub operator",
    )
    _add(
        "Workflows & approvals",
        "studio_os:automation",
        keywords="workflow automation approval",
    )
    _add("Launch & setup", "studio_os:launch", keywords="launch setup onboarding")
    try:
        launch_base = reverse("studio_os:launch")
        entries.append(
            {
                "label": "Launch Studio: migration & import",
                "url": f"{launch_base}?pane=migration",
                "keywords": "migration import wizard data launch studio",
            }
        )
        entries.append(
            {
                "label": "Launch Studio: preview by role",
                "url": f"{launch_base}?pane=role_preview",
                "keywords": "preview role portal parent teacher launch",
            }
        )
        entries.append(
            {
                "label": "Launch Studio: school infrastructure",
                "url": f"{launch_base}?pane=infrastructure",
                "keywords": "school infrastructure blueprint template AWS studio launch catalog pack",
            }
        )
    except NoReverseMatch:
        pass
    _add(
        "Feature control & capabilities",
        "studio_os:control",
        keywords="feature control capabilities",
    )
    _add("Studio overview", "studio_os:shell", keywords="studio home")
    _add(
        "Go to district analytics",
        "super:analytics_overview",
        keywords="district analytics overview",
    )
    _add(
        "Donors and gifts (advancement)",
        "accounts:advancement_donor_list",
        keywords="donor gift fundraising advancement CRM",
    )
    _add(
        "Operations hub (library, transport, inventory)",
        "accounts:ops_hub",
        keywords="library transport inventory canteen clinic timetable ops wave4",
    )
    _add(
        "Facilities / maintenance requests",
        "accounts:ops_facilities",
        keywords="facilities maintenance work order CMMS repair building",
    )
    _add(
        "POS till quick sale (stub)",
        "accounts:ops_pos",
        keywords="pos point of sale till cash register canteen retail",
    )
    _add(
        "Rollback metadata packages",
        "siteconfig:installed_packages_rollback",
        keywords="rollback package theme workflow dashboard policy N20",
    )
    _add(
        "Bulk capture (attendance)",
        "portal:teacher_bulk_capture_hub",
        keywords="bulk capture mobile roll call class attendance wave6",
    )
    _add(
        "Tenant activity log",
        "accounts:tenant_activity_log",
        keywords="events observability audit N24 platform log",
    )
    _add(
        "District LMS interop hub",
        "accounts:district_lms_interop",
        keywords="district clever oneroster roster interop",
    )
    _add(
        "Publish term grades",
        "reports:publish_term_results",
        keywords="publish grades term report card",
    )
    _add(
        "Parent pay invoice",
        "portal:parent_dashboard",
        keywords="parent pay invoice fees",
    )
    return entries


def get_studio_global_search(
    request: Any, q: str, limit: int = 20
) -> list[dict[str, Any]]:
    """
    §4.1 global search: search across Studio entities (modes, actions, commands).
    Returns list of {label, url, kind}. Uses command palette entries; extend with
    metadata/search backend for full entity search.
    """
    if not (q and q.strip()):
        return []
    q_lower = q.strip().lower()
    entries = get_studio_command_palette_entries(request)
    results = []
    for e in entries:
        if (
            q_lower in (e.get("label") or "").lower()
            or q_lower in (e.get("keywords") or "").lower()
        ):
            results.append(
                {
                    "label": e.get("label", ""),
                    "url": e.get("url", ""),
                    "kind": "command",
                }
            )
        if len(results) >= limit:
            break
    return results


def studio_publish_validate(mode: str, payload: dict[str, Any]) -> list[str]:
    """Validate before publish. Returns list of error messages (empty if valid)."""
    errors = []
    if mode == "experience":
        if not payload.get("preview_confirmed") and payload.get("governed_changes"):
            errors.append("Preview and confirm required for high-impact theme changes.")
    return errors


def studio_rollback_available(mode: str, request) -> bool:
    """Whether rollback is available for this mode in current context."""
    if mode == "control":
        return bool(request.session.get("feature_control_previous_state"))
    if mode == "experience":
        return bool(request.session.get("theme_previous_state"))
    return False


# ---- Shared publish/rollback service (one model for all modes) ----


def studio_save_draft(mode: str, request, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Save draft state for the given mode. Experience: stash theme payload in session for preview.
    Returns {"ok": True} or {"ok": False, "errors": [...]}.
    """
    errors = studio_publish_validate(mode, payload)
    if errors:
        return {"ok": False, "errors": errors}
    if mode == "experience":
        request.session["site_preview_settings"] = {
            k: payload.get(k)
            for k in (
                "primary_color",
                "accent_color",
                "header_bg_color",
                "footer_bg_color",
                "success_color",
                "warning_color",
                "danger_color",
                "theme_pack",
                "admin_theme_pack",
            )
            if payload.get(k) is not None
        }
        request.session["preview_mode_enabled"] = True
        request.session.modified = True
    return {"ok": True}


def studio_publish(mode: str, request, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and perform publish for the mode. Experience/Control actual persist is done by
    the existing theme_colors / feature_control_panel forms; this validates and returns redirect/success.
    Returns {"ok": True, "redirect_url": "..."} or {"ok": False, "errors": [...]}.
    """
    errors = studio_publish_validate(mode, payload)
    if errors:
        return {"ok": False, "errors": errors}
    try:
        from django.urls import reverse

        if mode == "experience":
            return {"ok": True, "redirect_url": reverse("studio_os:experience")}
        if mode == "control":
            return {"ok": True, "redirect_url": reverse("studio_os:control")}
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("studio_publish redirect: %s", e)
    return {"ok": True}


def get_studio_publish_audit(
    request, mode: str | None, limit: int = 20
) -> list[dict[str, Any]]:
    """Recent publish/rollback events for the mode (or all). Uses activity feed + feature control audit."""
    feed = get_studio_activity_feed(request, limit=limit)
    return feed


def get_studio_version_history(
    request, mode: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Version history for the mode. Stub: returns last session-backed state or empty."""
    history = []
    if mode == "experience" and request.session.get("theme_recent_change_meta"):
        meta = request.session["theme_recent_change_meta"]
        history.append(
            {
                "version": "current",
                "timestamp": meta.get("timestamp", ""),
                "actor": meta.get("actor", ""),
                "label": "Last published",
            }
        )
    return history[:limit]


# §4.2 compare (optional) / §5.6 before/after: theme compare context for Experience Studio.
_EXPERIENCE_COMPARE_THEME_KEYS = [
    ("primary_color", "Primary"),
    ("accent_color", "Accent"),
    ("header_bg_color", "Header background"),
    ("footer_bg_color", "Footer background"),
    ("success_color", "Success"),
    ("warning_color", "Warning"),
    ("danger_color", "Danger"),
]


def _theme_snapshot_to_entries(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Convert theme dict to list of {name, label, value} for compare view."""
    if not snapshot:
        return []
    return [
        {"name": name, "label": label, "value": (snapshot.get(name) or "")[:64]}
        for name, label in _EXPERIENCE_COMPARE_THEME_KEYS
    ]


def get_studio_compare_context(request: Any, mode: str) -> dict[str, Any]:
    """
    Before/after context for Studio compare view. Experience: before = session theme_previous_state,
    after = current effective theme (or session preview). Other modes: empty has_before, stubs.
    Returns: before_entries, after_entries, has_before.
    """
    result: dict[str, Any] = {
        "before_entries": [],
        "after_entries": [],
        "has_before": False,
    }
    if mode != "experience":
        return result
    try:
        from apps.siteconfig.config_service import get_effective_site_settings

        # After: current saved theme, or session preview if set
        preview = request.session.get("site_preview_settings") or {}
        # config-resolver-allow: theme keys read dynamically (variable-key getattr over _EXPERIENCE_COMPARE_THEME_KEYS)
        site = get_effective_site_settings(request=request)
        after_snapshot: dict[str, Any] = {}
        for name, _ in _EXPERIENCE_COMPARE_THEME_KEYS:
            after_snapshot[name] = (
                preview.get(name) if preview else getattr(site, name, None)
            )
            if after_snapshot[name] is None:
                after_snapshot[name] = getattr(site, name, None)
        result["after_entries"] = _theme_snapshot_to_entries(after_snapshot)
        # Before: session theme_previous_state (set on theme save before overwrite)
        before_snapshot = request.session.get("theme_previous_state") or {}
        result["before_entries"] = _theme_snapshot_to_entries(before_snapshot)
        result["has_before"] = bool(before_snapshot)
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_studio_compare_context: %s", e)
    return result


# §4.4 Output Studio dependency graph (optional): report pack dependencies for Output hub.
def get_output_dependency_graph() -> list[dict[str, Any]]:
    """
    Build dependency graph for Output Studio: each active ReportPack with its
    normalized dependencies (from dependency_schema). Used by output_dependency_graph view.
    """
    try:
        from apps.reports.report_packs import (
            list_active_report_packs,
            normalize_report_pack_dependencies,
        )

        packs = list_active_report_packs()
        return [
            {
                "pack_code": getattr(p, "code", "") or "",
                "pack_name": getattr(p, "name", "") or getattr(p, "code", "") or "—",
                "dependencies": normalize_report_pack_dependencies(p),
            }
            for p in packs
        ]
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_output_dependency_graph: %s", e)
        return []


def get_output_report_pack_preview_cards(*, out_base: str) -> list[dict[str, Any]]:
    """
    Sample-data preview cards for each active ReportPack (§4.4 / §5.3 in-Studio depth).
    `out_base` is absolute path to studio_os:output (no query); graph links add pane + pack.
    """
    try:
        from apps.reports.report_packs import (
            build_report_pack_preview,
            list_active_report_packs,
        )

        base = (out_base or "").rstrip("/") or "/studio/output/"
        cards: list[dict[str, Any]] = []
        for pack in list_active_report_packs():
            code = (getattr(pack, "code", None) or "").strip()
            name = (getattr(pack, "name", None) or code or "—").strip()
            preview = build_report_pack_preview(pack)
            q = "pane=dependency"
            if code:
                q = f"{q}&pack={code}"
            join = "&" if "?" in base else "?"
            cards.append(
                {
                    "pack_code": code,
                    "pack_name": name,
                    "preview": preview,
                    "graph_url": f"{base}{join}{q}",
                }
            )
        return cards
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_output_report_pack_preview_cards: %s", e)
        return []


# §4.3 Automation Studio dependency graph (optional): workflow packs and their templates.
def get_automation_dependency_graph() -> list[dict[str, Any]]:
    """
    Build dependency graph for Automation Studio: each active WorkflowPack with its
    WorkflowTemplates (pack → templates). Used by automation_dependency_graph view.
    """
    try:
        from apps.runtime_blueprints.models import WorkflowPack

        packs = (
            WorkflowPack.objects.filter(is_active=True)
            .prefetch_related("templates")
            .order_by("family", "name")
        )
        out: list[dict[str, Any]] = []
        for p in packs:
            rel = getattr(p, "templates", None)
            templates = list(rel.all()[:50]) if rel is not None else []
            out.append(
                {
                    "pack_code": getattr(p, "code", "") or "",
                    "pack_name": getattr(p, "name", "")
                    or getattr(p, "code", "")
                    or "—",
                    "templates": [
                        {
                            "code": getattr(t, "code", "") or "",
                            "name": getattr(t, "name", "")
                            or getattr(t, "code", "")
                            or "—",
                        }
                        for t in templates
                    ],
                }
            )
        return out
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_automation_dependency_graph: %s", e)
        return []


def get_automation_workflow_health_summary(
    request: Any | None = None,
) -> dict[str, Any]:
    """
    §4.3 Automation Studio optional: high-level workflow health metrics.

    Returns a lightweight summary for the Automation rail card:
    - pack_count: number of WorkflowPack records (tenant: assigned packs)
    - template_count: number of WorkflowTemplate records
    - paused_count: inactive packs (tenant: assigned inactive packs)
    - failing_count: ProcessRun rows in failed terminal state (tenant-scoped when school set)
    - service_online: True when at least one metric source resolved (False = unknown, not zero)
    """
    empty: dict[str, Any] = {
        "pack_count": 0,
        "template_count": 0,
        "paused_count": 0,
        "failing_count": 0,
        "service_online": False,
    }
    school = getattr(request, "school", None) if request is not None else None
    try:
        from apps.runtime_blueprints.models import (
            WorkflowPack,
            WorkflowPackAssignment,
            WorkflowTemplate,
        )

        if school is not None:
            assignments = WorkflowPackAssignment.objects.filter(school=school)
            # The FK is ``workflow_pack`` (id accessor ``workflow_pack_id``);
            # there is no ``pack_id`` field, so the old literal raised FieldError
            # and 500'd every /studio/automation/ load.
            pack_ids = list(assignments.values_list("workflow_pack_id", flat=True))
            pack_count = len(pack_ids)
            paused_count = int(
                WorkflowPack.objects.filter(id__in=pack_ids, is_active=False).count()
            )
            template_count = int(WorkflowTemplate.objects.all().count())
            failing_count = 0
            try:
                from apps.orchestration.models import OrchestrationRun

                failing_count = int(
                    OrchestrationRun.objects.filter(
                        school=school, status__iexact="failed"
                    ).count()
                )
            except _STUDIO_SOFT_FAILURES:
                failing_count = 0
            return {
                "pack_count": pack_count,
                "template_count": template_count,
                "paused_count": paused_count,
                "failing_count": failing_count,
                "service_online": True,
            }

        pack_count = int(WorkflowPack.objects.all().count())
        template_count = int(WorkflowTemplate.objects.all().count())
        paused_count = 0
        try:
            paused_count = int(
                WorkflowPack.objects.filter(is_active=False).count()
            )
        except _STUDIO_SOFT_FAILURES:
            paused_count = 0
        failing_count = 0
        try:
            from apps.orchestration.models import OrchestrationRun

            failing_count = int(
                OrchestrationRun.objects.filter(status__iexact="failed").count()  # tenant-isolation-allow: studio-platform-wide-orchestration-failure-count
            )
        except _STUDIO_SOFT_FAILURES:
            failing_count = 0
        return {
            "pack_count": pack_count,
            "template_count": template_count,
            "paused_count": paused_count,
            "failing_count": failing_count,
            "service_online": True,
        }
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_automation_workflow_health_summary: %s", e)
        return empty


# ---------------------------------------------------------------------------
# v3.54.0 (2026-05-21): Next-realm cockpit helpers.
# Backfill the 4 deferred services flagged by the 6-agent fan-out:
#   - get_overview_signals       — 5-key cockpit signal strip data
#   - get_output_readiness_summary — Output cockpit readiness panels
#   - get_launch_readiness_summary — Launch cockpit timeline + approvals + risk
# Each helper is best-effort: defensive try/except, honest None / 0 fallback,
# never raises. Templates render `data-state="unknown"` placeholder for None.
# ---------------------------------------------------------------------------


def get_overview_signals(request: Any) -> dict[str, Any]:
    """v3.54.0: Mission cockpit signal-strip data for Overview mode.

    Returns a 5-key dict consumed by:
      - templates/studio_os/partials/cockpit_signal_strip.html
      - templates/studio_os/partials/overview_command_cockpit.html

    Each value is either an int (real count) or None (honest "unknown" state).
    Templates render `data-state="unknown"` placeholder when value is None.

    Keys:
      - pending_launches: schools / tenants with incomplete onboarding
      - draft_experiences: theme/experience drafts pending publish
      - active_automations: enabled WorkflowPack count
      - output_readiness_pct: 0..100 percentage of report packs with all deps green
      - open_blockers: count of currently-open critical issues
    """
    signals: dict[str, Any] = {
        "pending_launches": None,
        "draft_experiences": None,
        "active_automations": None,
        "output_readiness_pct": None,
        "open_blockers": None,
    }
    # Pending launches: setup_studio payload + per-tenant launch_ready=False.
    try:
        from apps.schools.models import School  # type: ignore[import-not-found]
        from apps.setup_studio.services import get_setup_studio_payload

        pending = 0
        # Best-effort: walk a small sample (max 50) to avoid heavy queries.
        # tenant-isolation-allow: overview-aggregate-readonly-count-only
        for sch in School.objects.all()[:50]:
            try:
                payload = get_setup_studio_payload(sch)
                if not bool(payload.get("launch_ready", False)):
                    pending += 1
            except _STUDIO_SOFT_FAILURES:
                continue
        signals["pending_launches"] = pending
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_overview_signals.pending_launches: %s", e)
    # Active automations: WorkflowPack count where is_active=True (best-effort).
    try:
        from apps.runtime_blueprints.models import WorkflowPack  # type: ignore[import-not-found]

        try:
            signals["active_automations"] = int(
                WorkflowPack.objects.filter(is_active=True).count()
            )
        except _STUDIO_SOFT_FAILURES:
            # Schema doesn't carry is_active — fall back to total count.
            signals["active_automations"] = int(WorkflowPack.objects.all().count())
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_overview_signals.active_automations: %s", e)
    # Output readiness pct: derived from dependency graph.
    try:
        graph = get_output_dependency_graph()
        if graph:
            ready = sum(1 for node in graph if not node.get("missing_deps"))
            signals["output_readiness_pct"] = int(round(100.0 * ready / len(graph)))
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_overview_signals.output_readiness_pct: %s", e)
    # Draft experiences: tenants with preview mode still enabled (unpublished theme work).
    try:
        from apps.platform_runtime.config_resolver import get_effective_config  # type: ignore[import-not-found]
        from apps.schools.models import School  # type: ignore[import-not-found]

        school = getattr(request, "school", None) if request is not None else None
        if school is not None:
            signals["draft_experiences"] = int(
                bool(
                    get_effective_config(
                        key="preview_mode_enabled", school=school, default=False
                    )
                )
            )
        else:
            draft_count = 0
            # tenant-isolation-allow: overview-aggregate-readonly-preview-count
            for sch in School.objects.all()[:50]:
                try:
                    if bool(
                        get_effective_config(
                            key="preview_mode_enabled", school=sch, default=False
                        )
                    ):
                        draft_count += 1
                except _STUDIO_SOFT_FAILURES:
                    continue
            signals["draft_experiences"] = draft_count
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_overview_signals.draft_experiences: %s", e)
    # Open blockers: unresolved platform incidents (operator overview aggregate).
    try:
        from apps.observability.monitoring import PlatformIncident  # type: ignore[import-not-found]

        open_statuses = (
            PlatformIncident.Status.OPEN,
            PlatformIncident.Status.ACKNOWLEDGED,
            PlatformIncident.Status.MITIGATED,
        )
        incident_qs = PlatformIncident.objects.filter(status__in=open_statuses)
        school = getattr(request, "school", None) if request is not None else None
        if school is not None:
            # tenant-isolation-allow: overview-signal-tenant-scoped-incident-count
            incident_qs = incident_qs.filter(affected_school=school)
        signals["open_blockers"] = int(incident_qs.count())
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_overview_signals.open_blockers: %s", e)
    return signals


def get_output_readiness_summary() -> dict[str, Any]:
    """v3.54.0: Output cockpit readiness summary.

    Consumed by templates/studio_os/partials/output_readiness_preview_pane.html
    + workspace/output_canvas.html. Coordinator task #7 from the 6-agent wave.

    Returns:
      - packs_total: int — total report packs
      - packs_with_deps: int — packs whose dependencies are all available
      - packs_missing_deps: int — packs with at least one missing dep
      - documents_total: int — total documents in library (best-effort)
      - documents_published: int — published documents (best-effort)
      - service_online: bool — true if at least one count resolved successfully
    """
    summary: dict[str, Any] = {
        "packs_total": 0,
        "packs_with_deps": 0,
        "packs_missing_deps": 0,
        "documents_total": 0,
        "documents_published": 0,
        "service_online": False,
    }
    try:
        graph = get_output_dependency_graph()
        summary["packs_total"] = len(graph)
        summary["packs_with_deps"] = sum(
            1 for node in graph if not node.get("missing_deps")
        )
        summary["packs_missing_deps"] = summary["packs_total"] - summary[
            "packs_with_deps"
        ]
        summary["service_online"] = True
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_output_readiness_summary.graph: %s", e)
    # Documents: best-effort. Different document apps across waves —
    # try a couple of common names.
    for module_path, model_name in (
        ("apps.reports.models", "Report"),
        ("apps.reports.models", "ReportPack"),
    ):
        try:
            mod = __import__(module_path, fromlist=[model_name])
            model = getattr(mod, model_name)
            summary["documents_total"] = int(model.objects.all().count())
            try:
                field_names = {f.name for f in model._meta.fields}
                if "is_published" in field_names:
                    summary["documents_published"] = int(
                        model.objects.filter(is_published=True).count()
                    )
                elif "is_active" in field_names:
                    summary["documents_published"] = int(
                        model.objects.filter(is_active=True).count()
                    )
            except _STUDIO_SOFT_FAILURES:
                pass
            summary["service_online"] = True
            break
        except _STUDIO_SOFT_FAILURES:
            continue
    return summary


def get_launch_readiness_summary(request: Any) -> dict[str, Any]:
    """v3.54.0: Launch cockpit readiness summary.

    Consumed by templates/studio_os/partials/launch_readiness_preview_pane.html
    + the Launch mode canvas. Coordinator task #12 from the 6-agent wave.

    Returns:
      - timeline: list of dicts (label/status/due_at)  — empty when service absent
      - approvals_pending: int — count of approval-queue items awaiting action
      - risk_summary: str — one-line risk summary or empty string
      - service_online: bool — true if any field resolved
    """
    summary: dict[str, Any] = {
        "timeline": [],
        "approvals_pending": 0,
        "risk_summary": "",
        "service_online": False,
    }
    school = getattr(request, "school", None) if request is not None else None
    # Pending tenant onboarding approvals (manager launch cockpit).
    try:
        from apps.schools.models import School

        qs = School.objects.filter(is_active=False, is_approved=False)
        if school is not None:
            # tenant-isolation-allow: launch-cockpit-tenant-scoped-approval-count
            qs = qs.filter(pk=school.pk)
        summary["approvals_pending"] = int(qs.count())
        summary["service_online"] = True
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_launch_readiness_summary.approvals_pending: %s", e)
    if school is not None:
        try:
            from apps.setup_studio.services import get_setup_studio_payload

            payload = get_setup_studio_payload(school)
            step_state = payload.get("step_state") or {}
            timeline: list[dict[str, Any]] = []
            for key, state in step_state.items():
                if not isinstance(state, dict):
                    continue
                timeline.append(
                    {
                        "label": str(
                            state.get("label")
                            or state.get("title")
                            or key.replace("_", " ").title()
                        ),
                        "status": "done" if state.get("done") else "pending",
                        "due_at": "",
                    }
                )
            summary["timeline"] = timeline
            blockers = payload.get("launch_blockers") or []
            if blockers:
                first = blockers[0]
                if isinstance(first, dict):
                    summary["risk_summary"] = str(
                        first.get("label") or first.get("detail") or first.get("message") or ""
                    )[:240]
                else:
                    summary["risk_summary"] = str(first)[:240]
            elif payload.get("health_summary"):
                summary["risk_summary"] = str(payload.get("health_summary"))[:240]
            summary["service_online"] = True
        except _STUDIO_SOFT_FAILURES as e:
            logger.warning("get_launch_readiness_summary.timeline: %s", e)
    return summary


def get_automation_simulation_preview(request: Any) -> dict[str, Any] | None:
    """Latest dry-run workflow simulation for the automation cockpit preview pane."""
    school = getattr(request, "school", None) if request is not None else None
    if school is None:
        return None
    try:
        from apps.automation.workflow_graph_models import WorkflowRunLog  # type: ignore[import-not-found]

        run = (
            WorkflowRunLog.objects.filter(workflow__school=school, dry_run=True)
            .select_related("workflow")
            .order_by("-created_at")
            .first()
        )
        if run is None:
            return None
        actions = run.actions_run if isinstance(run.actions_run, list) else []
        payload = run.payload_snapshot if isinstance(run.payload_snapshot, dict) else {}
        affected = payload.get("affected_record_count")
        if affected is None:
            affected = payload.get("affected_records")
        try:
            affected_count = int(affected or 0)
        except (TypeError, ValueError):
            affected_count = 0
        risks: list[dict[str, str]] = []
        if run.status == WorkflowRunLog.Status.FAILED and run.error_message:
            risks.append(
                {
                    "label": "Simulation failed",
                    "detail": str(run.error_message)[:180],
                }
            )
        ran_at = getattr(run, "created_at", None)
        return {
            "trigger_label": str(run.trigger_event or run.workflow.name or "workflow"),
            "projected_actions": len(actions),
            "affected_record_count": affected_count,
            "risks": risks,
            "ran_at_iso": ran_at.isoformat() if ran_at is not None else "",
        }
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_automation_simulation_preview: %s", e)
        return None
