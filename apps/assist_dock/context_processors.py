"""v4.00.91 — assist dock context processor.

Resolves the request's surface + role, filters the registry, and exposes
``assist_dock`` to every template:

    {
        "assist_dock": {
            "surface": "portal",
            "role": "TEACHER",
            "slots": [<jsonable slot dict>, ...],
            "expand_label": "More assistants",
            "collapse_label": "Fewer assistants",
            "toolbar_label": "Page assistants",
            "version": "v4.00.91",
        }
    }

Pages render the JSON island ``rmc_assist_dock_slots.html`` from this
context; the JS hydrates the rail from the island. The processor is
defensive — any failure logs a debug message and returns an empty payload
so a misconfigured slot never breaks page rendering.
"""

from __future__ import annotations

import json
import logging

from django.utils.translation import gettext_lazy as _

from .client_urls import resolve_assist_dock_client_urls
from .registry import (
    SURFACE_ADMIN,
    SURFACE_ANY,
    SURFACE_MANAGER,
    SURFACE_PORTAL,
    get_slots_for,
    slots_as_jsonable,
)

logger = logging.getLogger(__name__)

DOCK_PAYLOAD_VERSION = "v4.00.91"


def _resolve_surface(request) -> str:
    """Map a request to one of the canonical surface identifiers.

    Resolution order:
      1. ``request.public_host_kind`` (set by ReservedPublicHostAccessMiddleware /
         the manager-host stack) — preferred, no ambiguity.
      2. URL prefix sniff: ``/admin/`` → admin, ``/super/`` → manager.
      3. ``request.tenant`` presence — tenant subdomain implies portal.
      4. Fallback: SURFACE_ANY.
    """
    host_kind = getattr(request, "public_host_kind", "") or ""
    if host_kind == "manager":
        return SURFACE_MANAGER
    if host_kind == "tenant":
        # Could be portal OR admin; check path prefix to disambiguate.
        path = getattr(request, "path", "") or ""
        if path.startswith("/admin/"):
            return SURFACE_ADMIN
        return SURFACE_PORTAL

    path = getattr(request, "path", "") or ""
    if path.startswith("/admin/"):
        return SURFACE_ADMIN
    if path.startswith("/super/") or path.startswith("/manager/"):
        return SURFACE_MANAGER

    if getattr(request, "tenant", None) is not None:
        return SURFACE_PORTAL

    return SURFACE_ANY


def _resolve_role(request) -> str:
    """Return the user's primary role string for slot filtering.

    Anonymous returns ``"anonymous"``; superuser returns ``"SUPERADMIN"``.
    Otherwise prefer ``user.active_role`` / ``user.primary_role`` / ``user.role``
    in that order — the same precedence used by ``_resolve_user_role`` in
    the RLS-JWT middleware (v4.00.7).
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return "anonymous"
    if getattr(user, "is_superuser", False):
        return "SUPERADMIN"
    for attr in ("active_role", "primary_role", "role"):
        value = getattr(user, attr, None)
        if value:
            return str(value)
    if getattr(user, "is_staff", False):
        return "STAFF"
    return "USER"


def _effective_feature_flags(request) -> dict:
    """Tenant flags without forcing a DB read when ``school.settings`` is populated."""
    try:
        school = getattr(request, "school", None)
        if school is not None:
            raw = getattr(school, "settings", None) or {}
            if isinstance(raw, dict):
                nested = raw.get("backend_feature_flags") or {}
                if isinstance(nested, dict) and nested:
                    return dict(nested)
        from apps.portal.ai_chrome_config import _effective_flags

        return dict(_effective_flags(request) or {})
    except (AttributeError, ImportError, LookupError, TypeError, ValueError):
        return {}


def _dock_labels(flags: dict) -> tuple[str, str, str]:
    ui = flags.get("assist_dock_ui") if isinstance(flags.get("assist_dock_ui"), dict) else {}
    expand = str(ui.get("expand_label") or "").strip() or _("More assistants")
    collapse = str(ui.get("collapse_label") or "").strip() or _("Fewer assistants")
    toolbar = str(ui.get("toolbar_label") or "").strip() or _("Page assistants")
    return expand, collapse, toolbar


def assist_dock_context(request) -> dict:
    try:
        surface = _resolve_surface(request)
        role = _resolve_role(request)
        flags = _effective_feature_flags(request)
        slots = get_slots_for(surface=surface, role=role, include_hidden=True)
        from apps.siteconfig.platform_surface_config import filter_assist_dock_slots

        slots = filter_assist_dock_slots(slots, flags)
        # Wave C: apply per-user preferences (hide / reorder / density / side).
        prefs = _safe_get_prefs(request)
        slots = _safe_apply_prefs(slots, prefs)
        expand_label, collapse_label, toolbar_label = _dock_labels(flags)
        payload = {
            "surface": surface,
            "role": role,
            "slots": slots_as_jsonable(slots),
            "expand_label": expand_label,
            "collapse_label": collapse_label,
            "toolbar_label": toolbar_label,
            "version": DOCK_PAYLOAD_VERSION,
            "prefs": prefs,
            "urls": resolve_assist_dock_client_urls(request),
        }
        urls = payload.get("urls") or {}
        return {
            "assist_dock": payload,
            "ASSIST_DOCK_URLS_JSON": json.dumps(urls, separators=(",", ":")),
        }
    except (AttributeError, RuntimeError, ValueError) as exc:
        logger.debug("assist_dock context processor failed: %s", exc)
        return {"assist_dock": {
            "surface": SURFACE_ANY,
            "role": "anonymous",
            "slots": [],
            "expand_label": _("More assistants"),
            "collapse_label": _("Fewer assistants"),
            "toolbar_label": _("Page assistants"),
            "version": DOCK_PAYLOAD_VERSION,
            "prefs": {},
            "urls": {},
        }, "ASSIST_DOCK_URLS_JSON": "{}"}


def _safe_get_prefs(request) -> dict:
    """Defensive prefs lookup — never raises into the context processor."""
    try:
        from .models import get_or_default_prefs

        user = getattr(request, "user", None)
        return get_or_default_prefs(user)
    except (ImportError, RuntimeError, ValueError) as exc:
        logger.debug("assist_dock prefs lookup failed: %s", exc)
        try:
            from .models import default_prefs_payload as _default
            return _default()
        except (ImportError, RuntimeError):
            return {}


def _safe_apply_prefs(slots, payload):
    """Defensive prefs application — falls back to the raw slot list."""
    try:
        from .models import apply_prefs_to_slots

        return apply_prefs_to_slots(slots, payload or {})
    except (ImportError, RuntimeError, ValueError) as exc:
        logger.debug("assist_dock prefs apply failed: %s", exc)
        return list(slots)
