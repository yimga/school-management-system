# -*- coding: utf-8 -*-
"""
Studio OS shared services: preview, publish/rollback, activity, recommendations.
One model for all modes. Unified preview URL is the single entry point for embed/preview per mode.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Mode -> (reverse_name, query_param). Single source for Studio embed/preview URLs.
STUDIO_MODE_EMBED_TARGETS = {
    "experience": ("siteconfig:theme_colors", "embed=1"),
    "automation": ("siteconfig:workflow_hub", "embed=1"),
    "output": ("siteconfig:report_library", "embed=1"),
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
        return f"{base}?{qs}" if qs else base
    except NoReverseMatch:
        return ""


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
        feed.append({
            "kind": "theme_publish",
            "label": "Theme & experience published",
            "timestamp": theme_meta.get("timestamp", ""),
            "actor": theme_meta.get("actor", ""),
            "detail": f"{theme_meta.get('changed_count', 0)} fields",
            "url": url,
        })

    # Feature control audit (last N)
    try:
        from apps.siteconfig.models_dashboard import FeatureControlAudit
        control_url = _safe("studio_os:control")
        for entry in FeatureControlAudit.objects.select_related("user").order_by("-created_at")[:limit]:
            if not control_url:
                break
            feed.append({
                "kind": "feature_control",
                "label": "Feature control" + (" reverted" if entry.action == "revert" else " saved"),
                "timestamp": entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else "",
                "actor": entry.user.get_username() if entry.user else "system",
                "detail": entry.action or "save",
                "url": control_url,
            })
    except Exception as e:
        logger.debug("Studio activity: feature control audit unavailable: %s", e)

    # Sort by timestamp desc (simplified: theme first then audit entries)
    return feed[:limit]


def get_studio_recommendations(request, mode: str | None) -> list[dict[str, Any]]:
    """
    Next-best-action recommendations for the shell. Mode-specific when current_mode is set.
    """
    from django.urls import NoReverseMatch, reverse

    def _safe(name: str) -> str | None:
        try:
            return reverse(name)
        except NoReverseMatch:
            return None

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
                    url = _safe("studio_os:launch")
                    if url:
                        recs.append({
                            "label": rec.get("label", "Launch"),
                            "detail": rec.get("detail", ""),
                            "url": url,
                            "tone": rec.get("tone", "neutral"),
                        })
                else:
                    url = _safe("studio_os:launch")
                    if url:
                        recs.append({"label": "Launch", "detail": str(rec), "url": url, "tone": "neutral"})
            if payload.get("launch_blockers"):
                url = _safe("studio_os:launch")
                if url:
                    recs.append({
                        "label": "Resolve launch blockers",
                        "detail": f"{len(payload['launch_blockers'])} blocker(s)",
                        "url": url,
                        "tone": "risk",
                    })
        except Exception as e:
            logger.debug("Studio recommendations: launch payload unavailable: %s", e)

    if mode == "experience":
        url = _safe("studio_os:experience")
        if url:
            recs.append({
                "label": "Check contrast",
                "detail": "Use Live preview and confirm accessibility before publishing.",
                "url": url,
                "tone": "neutral",
            })

    if mode == "control":
        url = _safe("siteconfig:feature_control_audit")
        if url:
            recs.append({
                "label": "Review audit",
                "detail": "Check feature control audit before rolling back.",
                "url": url,
                "tone": "neutral",
            })

    if not mode or mode == "overview":
        url = _safe("studio_os:shell")
        if url:
            recs.append({
                "label": "Open Studio",
                "detail": "Choose a mode to shape experience, automate, publish, launch, or govern.",
                "url": url,
                "tone": "neutral",
            })

    return recs[:5]


def get_studio_command_palette_entries(request) -> list[dict[str, Any]]:
    """Commands for global search / command palette. Resolves to Studio modes or actions."""
    from django.urls import NoReverseMatch, reverse

    def _safe(name: str) -> str | None:
        try:
            return reverse(name)
        except NoReverseMatch:
            return None

    entries = []

    def _add(label: str, url_name: str, *, keywords: str) -> None:
        url = _safe(url_name)
        if not url:
            return
        entries.append({
            "label": label,
            "url": url,
            "keywords": keywords,
        })

    _add("Change school branding", "studio_os:experience", keywords="brand theme colors experience")
    _add("Set up grade reports", "studio_os:output", keywords="reports output")
    _add("Preview parent portal", "portal:parent_dashboard", keywords="preview parent portal")
    _add("Workflows & approvals", "studio_os:automation", keywords="workflow automation approval")
    _add("Launch & setup", "studio_os:launch", keywords="launch setup onboarding")
    _add("Feature control & capabilities", "studio_os:control", keywords="feature control capabilities")
    _add("Studio overview", "studio_os:shell", keywords="studio home")
    return entries


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
            k: payload.get(k) for k in (
                "primary_color", "accent_color", "header_bg_color", "footer_bg_color",
                "success_color", "warning_color", "danger_color", "theme_pack", "admin_theme_pack",
            ) if payload.get(k) is not None
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
    except Exception as e:
        logger.warning("studio_publish redirect: %s", e)
    return {"ok": True}


def get_studio_publish_audit(request, mode: str | None, limit: int = 20) -> list[dict[str, Any]]:
    """Recent publish/rollback events for the mode (or all). Uses activity feed + feature control audit."""
    feed = get_studio_activity_feed(request, limit=limit)
    return feed


def get_studio_version_history(request, mode: str, limit: int = 10) -> list[dict[str, Any]]:
    """Version history for the mode. Stub: returns last session-backed state or empty."""
    history = []
    if mode == "experience" and request.session.get("theme_recent_change_meta"):
        meta = request.session["theme_recent_change_meta"]
        history.append({
            "version": "current",
            "timestamp": meta.get("timestamp", ""),
            "actor": meta.get("actor", ""),
            "label": "Last published",
        })
    return history[:limit]
