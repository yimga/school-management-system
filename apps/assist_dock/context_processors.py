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

import logging

from django.utils.translation import gettext_lazy as _

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


def assist_dock_context(request) -> dict:
    try:
        surface = _resolve_surface(request)
        role = _resolve_role(request)
        slots = get_slots_for(surface=surface, role=role)
        # Wave C: apply per-user preferences (hide / reorder / density / side).
        prefs = _safe_get_prefs(request)
        slots = _safe_apply_prefs(slots, prefs)
        payload = {
            "surface": surface,
            "role": role,
            "slots": slots_as_jsonable(slots),
            "expand_label": _("More assistants"),
            "collapse_label": _("Fewer assistants"),
            "toolbar_label": _("Page assistants"),
            "version": DOCK_PAYLOAD_VERSION,
            "prefs": prefs,
        }
        return {"assist_dock": payload}
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
        }}


def _safe_get_prefs(request) -> dict:
    """Defensive prefs lookup — never raises into the context processor."""
    try:
        from .models import default_prefs_payload, get_or_default_prefs

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
