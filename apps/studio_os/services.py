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

        base = studio_resolve_url(name)
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

                url = studio_resolve_url(url_name) or ""
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
    from django.utils.translation import gettext as _

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
            "primary_cta_url": legacy_urls.get("workflow_hub") or "",
            "primary_cta_label": _("Workflow center"),
            "secondary_cta_url": legacy_urls.get("workflow_flow_gallery") or "",
            "secondary_cta_label": _("Flow gallery"),
        }
        if needs_tenant:
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
            "secondary_cta_url": legacy_urls.get("document_library") or "",
            "secondary_cta_label": _("Document library"),
        }
        if needs_tenant:
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
            u = studio_resolve_url(name)
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
            return studio_resolve_url(name) or None

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


def get_automation_workflow_health_summary() -> dict[str, int]:
    """
    §4.3 Automation Studio optional: high-level workflow health metrics.

    Returns a lightweight summary for the Automation rail card:
    - pack_count: number of WorkflowPack records
    - template_count: number of WorkflowTemplate records
    """
    try:
        from apps.runtime_blueprints.models import WorkflowPack, WorkflowTemplate

        pack_count = int(WorkflowPack.objects.all().count())
        template_count = int(WorkflowTemplate.objects.all().count())
        return {
            "pack_count": pack_count,
            "template_count": template_count,
        }
    except _STUDIO_SOFT_FAILURES as e:
        logger.warning("get_automation_workflow_health_summary: %s", e)
        return {
            "pack_count": 0,
            "template_count": 0,
        }
