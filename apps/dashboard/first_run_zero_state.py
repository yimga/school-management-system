"""Per-role first-run zero-state.

A brand-new tenant's teacher / parent / student / admin / finance users used to
land on a blank shell — no data, no direction. This module produces a single
welcoming "here's your next step" card per persona, shown ONLY on that role's
landing page while the tenant is still being set up (not yet launched). Once the
school has data, the card disappears and the real dashboard takes over.

Design:
* ``zero_state_for_role`` is a PURE function (role -> static payload | None),
  fully unit-testable with no request/DB.
* ``build_first_run_zero_state`` is the request-aware entry: it gates on
  (authenticated) + (on a known role-home landing) + (tenant still in first-run),
  resolves the CTA URL safely, and returns a render-ready dict or ``None``.
* Everything is fail-soft — any error yields ``None`` so a populated tenant or a
  transient failure never shows a stale "get started" card.

The context processor in ``apps/dashboard/context_processors.py`` wires this
globally; ``portal_base.html`` renders it (every role landing inherits that base).
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)
User = get_user_model()

# Landing view-names (``namespace:name``) where a first-run card may appear.
# Anything else -> no card (the card is a LANDING affordance, not site-wide).
LANDING_VIEW_NAMES = frozenset({
    "accounts:backend_dashboard",
    "portal:parent_dashboard",
    "portal:teacher_dashboard_alias",
    "portal:student_portal_grades",
    "finance:dashboard",
})

# Persona key -> static card payload. The CTA points each persona at their true
# first action; admin + finance land on the bespoke Setup wizards (the lifecycle
# index) so first-run flows straight into provisioning.
_HOME_ZERO_STATE: dict[str, dict[str, Any]] = {
    "admin": {
        "headline": _("Welcome — let's set up your school"),
        "message": _("Your dashboard fills in as you add staff, students, and fees. Start with the guided setup wizards."),
        "primary_url_name": "setup_studio:tenant_wizard_index",
        "primary_label": _("Open setup wizards"),
        "primary_icon": "bi-magic",
    },
    "teacher": {
        "headline": _("Welcome to your workspace"),
        "message": _("Your classes, gradebook, and attendance appear here once your school assigns them to you."),
        "primary_url_name": "portal:teacher_workflow",
        "primary_label": _("Explore my workflow"),
        "primary_icon": "bi-diagram-3",
    },
    "parent": {
        "headline": _("Welcome! Let's link your child"),
        "message": _("Connect your child's account to follow grades, attendance, and fees all in one place."),
        "primary_url_name": "portal:link_child",
        "primary_label": _("Link a child"),
        "primary_icon": "bi-link-45deg",
    },
    "student": {
        "headline": _("Welcome to your portal"),
        "message": _("Your grades, assignments, and timetable show up here as your teachers add them."),
        "primary_url_name": "portal:student_workflow",
        "primary_label": _("Explore my portal"),
        "primary_icon": "bi-compass",
    },
    "finance": {
        "headline": _("Welcome — let's set up billing"),
        "message": _("Create your fee structure to start invoicing families and tracking payments."),
        "primary_url_name": "setup_studio:tenant_wizard_index",
        "primary_label": _("Open setup wizards"),
        "primary_icon": "bi-cash-coin",
    },
}

# Role code -> persona home. ADMIN/TEACHER/PARENT/STUDENT are canonical User.Role;
# the rest are extended tenant roles (not in User.Role TextChoices).
_ROLE_TO_HOME: dict[str, str] = {
    User.Role.ADMIN.value: "admin",
    "PRINCIPAL": "admin",  # role-string-allow: first-run-zero-state-persona-map-extended-roles
    "IT_ADMIN": "admin",  # role-string-allow: first-run-zero-state-persona-map-extended-roles
    User.Role.TEACHER.value: "teacher",
    User.Role.PARENT.value: "parent",
    User.Role.STUDENT.value: "student",
    "BURSAR": "finance",  # role-string-allow: first-run-zero-state-persona-map-extended-roles
    "ACCOUNTANT": "finance",  # role-string-allow: first-run-zero-state-persona-map-extended-roles
    "FINANCE_STAFF": "finance",  # role-string-allow: first-run-zero-state-persona-map-extended-roles
}

_FIRST_RUN_CACHE_TTL_SECONDS = 300  # magic-number-allow: first-run-state-cache-window-seconds


def zero_state_for_role(role_code: str | None) -> dict[str, Any] | None:
    """Pure: return the static zero-state payload for a role, or ``None``.

    No request, no DB, no reverse — just maps a role code to its persona card.
    """
    home = _ROLE_TO_HOME.get((role_code or "").upper())
    if not home:
        return None
    payload = _HOME_ZERO_STATE.get(home)
    return dict(payload) if payload else None


def _resolve_school(request) -> Any:
    """Best-effort school resolution (request.school / request.tenant)."""
    for attr in ("school", "tenant"):
        candidate = getattr(request, attr, None)
        if candidate is not None and getattr(candidate, "pk", None) is not None:
            return candidate
    user = getattr(request, "user", None)
    if user is not None:
        candidate = getattr(user, "school", None)
        if candidate is not None and getattr(candidate, "pk", None) is not None:
            return candidate
    return None


def _tenant_is_first_run(request) -> bool:
    """True when the tenant is still being set up (not launch-ready).

    Cached + fail-soft: on any error returns False so an established tenant never
    sees the card. Reuses setup_studio's launch-readiness SOT.
    """
    school = _resolve_school(request)
    if school is None:
        return False
    cache_key = f"rmc:first_run_zero_state:{getattr(school, 'pk', '')}"
    cached = cache.get(cache_key)
    if cached is not None:
        return bool(cached)
    first_run = False
    try:
        from apps.setup_studio.zero_friction import get_zero_friction_payload

        payload = get_zero_friction_payload(school) or {}
        first_run = not bool(payload.get("launch_ready", True))
    except Exception as exc:  # noqa: BLE001 — readiness is best-effort; fail to "not first-run"
        logger.debug("first-run readiness check failed: %s", exc)
        first_run = False
    cache.set(cache_key, first_run, _FIRST_RUN_CACHE_TTL_SECONDS)
    return first_run


def build_first_run_zero_state(request) -> dict[str, Any] | None:
    """Request-aware entry: a render-ready first-run card, or ``None``.

    Returns ``None`` unless the user is authenticated, is on a known role-home
    landing, has a supported role, AND the tenant is still in first-run. Fail-soft.
    """
    try:
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return None
        match = getattr(request, "resolver_match", None)
        view_name = getattr(match, "view_name", None)
        if view_name not in LANDING_VIEW_NAMES:
            return None
        payload = zero_state_for_role(getattr(user, "role", ""))
        if payload is None:
            return None
        if not _tenant_is_first_run(request):
            return None
        url = None
        try:
            url = reverse(payload["primary_url_name"])
        except (NoReverseMatch, KeyError):
            url = None
        return {
            "headline": payload["headline"],
            "message": payload["message"],
            "primary_url": url,
            "primary_label": payload["primary_label"] if url else None,
            "primary_icon": payload["primary_icon"],
            "illustration": "first_run",
        }
    except Exception as exc:  # noqa: BLE001 — a landing card must never break the page
        logger.debug("build_first_run_zero_state failed: %s", exc)
        return None
