# -*- coding: utf-8 -*-
"""
Studio OS shared services: preview, publish/rollback, activity, recommendations.
One model for all modes.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_studio_activity_feed(request, limit: int = 15) -> list[dict[str, Any]]:
    """
    Recent Studio-relevant actions: theme publishes, feature control changes, workflow runs, etc.
    Reuses FeatureControlAudit and theme_recent_change_meta; can be extended.
    """
    from django.urls import reverse

    feed = []
    school = getattr(request, "school", None)
    if not school:
        return feed

    # Theme recent change (session)
    theme_meta = request.session.get("theme_recent_change_meta")
    if theme_meta and theme_meta.get("status") == "saved":
        feed.append({
            "kind": "theme_publish",
            "label": "Theme & experience published",
            "timestamp": theme_meta.get("timestamp", ""),
            "actor": theme_meta.get("actor", ""),
            "detail": f"{theme_meta.get('changed_count', 0)} fields",
            "url": reverse("studio_os:experience"),
        })

    # Feature control audit (last N)
    try:
        from apps.siteconfig.models_dashboard import FeatureControlAudit
        for entry in FeatureControlAudit.objects.select_related("user").order_by("-created_at")[:limit]:
            feed.append({
                "kind": "feature_control",
                "label": "Feature control" + (" reverted" if entry.action == "revert" else " saved"),
                "timestamp": entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else "",
                "actor": entry.user.get_username() if entry.user else "system",
                "detail": entry.action or "save",
                "url": reverse("studio_os:control"),
            })
    except Exception as e:
        logger.debug("Studio activity: feature control audit unavailable: %s", e)

    # Sort by timestamp desc (simplified: theme first then audit entries)
    return feed[:limit]


def get_studio_recommendations(request, mode: str | None) -> list[dict[str, Any]]:
    """
    Next-best-action recommendations for the shell. Mode-specific when current_mode is set.
    """
    from django.urls import reverse

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
                    recs.append({
                        "label": rec.get("label", "Launch"),
                        "detail": rec.get("detail", ""),
                        "url": reverse("studio_os:launch"),
                        "tone": rec.get("tone", "neutral"),
                    })
                else:
                    recs.append({"label": "Launch", "detail": str(rec), "url": reverse("studio_os:launch"), "tone": "neutral"})
            if payload.get("launch_blockers"):
                recs.append({
                    "label": "Resolve launch blockers",
                    "detail": f"{len(payload['launch_blockers'])} blocker(s)",
                    "url": reverse("studio_os:launch"),
                    "tone": "risk",
                })
        except Exception as e:
            logger.debug("Studio recommendations: launch payload unavailable: %s", e)

    if mode == "experience":
        recs.append({
            "label": "Check contrast",
            "detail": "Use Live preview and confirm accessibility before publishing.",
            "url": reverse("studio_os:experience"),
            "tone": "neutral",
        })

    if mode == "control":
        recs.append({
            "label": "Review audit",
            "detail": "Check feature control audit before rolling back.",
            "url": reverse("siteconfig:feature_control_audit"),
            "tone": "neutral",
        })

    if not mode or mode == "overview":
        recs.append({
            "label": "Open Studio",
            "detail": "Choose a mode to shape experience, automate, publish, launch, or govern.",
            "url": reverse("studio_os:shell"),
            "tone": "neutral",
        })

    return recs[:5]


def get_studio_command_palette_entries(request) -> list[dict[str, Any]]:
    """Commands for global search / command palette. Resolves to Studio modes or actions."""
    from django.urls import reverse

    entries = [
        {"label": "Change school branding", "url": reverse("studio_os:experience"), "keywords": "brand theme colors experience"},
        {"label": "Set up grade reports", "url": reverse("studio_os:output"), "keywords": "reports output"},
        {"label": "Preview parent portal", "url": reverse("portal:parent_dashboard"), "keywords": "preview parent portal"},
        {"label": "Workflows & approvals", "url": reverse("studio_os:automation"), "keywords": "workflow automation approval"},
        {"label": "Launch & setup", "url": reverse("studio_os:launch"), "keywords": "launch setup onboarding"},
        {"label": "Feature control & capabilities", "url": reverse("studio_os:control"), "keywords": "feature control capabilities"},
        {"label": "Studio overview", "url": reverse("studio_os:shell"), "keywords": "studio home"},
    ]
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
        return bool(request.session.get("theme_recent_change_meta"))
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
