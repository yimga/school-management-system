"""First-login owner confirmation card (Owner Console — slice 1).

The very first time a school **creator** lands on their backend dashboard, we show
a one-time "you're the owner" card: confirm they'll run it, hand a superadmin the
keys, or decide later. The card only *reflects* authority the owner already holds
(``SchoolMembership.is_school_owner``) — it never grants ``is_staff`` and never
routes to the operator plane.

Design (mirrors ``apps/dashboard/first_run_zero_state.py``):
* ``build_owner_first_login_card`` is the request-aware entry — it gates on
  (authenticated) + (on the backend-dashboard landing) + (is an owner of the
  resolved school) + (has NOT yet acknowledged), then returns a render-ready dict
  or ``None``. Everything is fail-soft: any error yields ``None`` so the dashboard
  never breaks and a confirmed owner never re-sees the card.
* Acknowledgement is persisted in ``DashboardUserPreference.dashboard_layout``
  under a per-school key, so no migration is needed and multiple owners each
  acknowledge independently.

The context processor in ``apps/accounts/context_processors.py`` wires this;
``templates/accounts/backend_dashboard.html`` renders it.
"""

from __future__ import annotations

import logging
from typing import Any

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# The owner's home landing — the only view where the first-login card may appear.
_OWNER_LANDING_VIEW_NAME = "accounts:backend_dashboard"

# Acknowledgement values persisted in DashboardUserPreference.dashboard_layout.
ACK_CONFIRMED = "confirmed"
ACK_DEFERRED = "deferred"
_ACK_VALUES = frozenset({ACK_CONFIRMED, ACK_DEFERRED})


def owner_ack_key(school) -> str | None:
    """The per-school acknowledgement key (single source of truth so the reader and
    the writer never drift). ``None`` when the school has no usable pk."""
    pk = getattr(school, "pk", None)
    if pk is None:
        return None
    # School pk may be an int or a UUID; str() is stable either way.
    return f"owner_role_ack_{pk}"


def _resolve_school(request) -> Any:
    """Best-effort school resolution (request.school / request.tenant / user.school)."""
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


def owner_role_acknowledged(user, school) -> bool:
    """True when this user has already confirmed/deferred ownership for this school."""
    key = owner_ack_key(school)
    if key is None or user is None or not getattr(user, "pk", None):
        return False
    try:
        from apps.runtime_blueprints.models import DashboardUserPreference

        pref = DashboardUserPreference.objects.filter(user=user).only(
            "dashboard_layout"
        ).first()
        if not pref:
            return False
        return (pref.dashboard_layout or {}).get(key) in _ACK_VALUES
    except Exception as exc:  # noqa: BLE001 — a prefs read must never break rendering
        logger.debug("owner_role_acknowledged read failed: %s", exc)
        return False


def _owner_membership(user, school):
    """The user's owner membership on this school, or ``None``."""
    try:
        from apps.schools.models import SchoolMembership

        return SchoolMembership.objects.filter(
            school=school,
            user_id=getattr(user, "pk", None),
            is_school_owner=True,
            suspended_at__isnull=True,
        ).select_related(None).first()
    except Exception as exc:  # noqa: BLE001 — fail to "not an owner"
        logger.debug("owner membership lookup failed: %s", exc)
        return None


def _role_label(user, membership) -> str:
    """A human ownership label, e.g. "Owner · Superadmin" / "Owner · Admin"."""
    role = (getattr(membership, "role", "") or getattr(user, "role", "") or "").strip().upper()
    # Present the second badge from the effective role; owners are admin-like.
    second = {
        "SUPERADMIN": _("Superadmin"),
        "ADMIN": _("Admin"),
        "PRINCIPAL": _("Principal"),
        "LEADERSHIP": _("Leadership"),
    }.get(role, _("Admin"))
    # Translators: {second} is the owner's effective backend role.
    return _("Owner · %(role)s") % {"role": second}


def _safe_reverse(name: str) -> str | None:
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def build_owner_first_login_card(request) -> dict[str, Any] | None:
    """Request-aware entry: a render-ready first-login owner card, or ``None``.

    Returns ``None`` unless the user is authenticated, is on the backend-dashboard
    landing, is an owner of the resolved school, and has NOT yet acknowledged.
    Fail-soft — a landing card must never break the page.
    """
    try:
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return None
        match = getattr(request, "resolver_match", None)
        if getattr(match, "view_name", None) != _OWNER_LANDING_VIEW_NAME:
            return None
        school = _resolve_school(request)
        if school is None:
            return None
        membership = _owner_membership(user, school)
        if membership is None:
            return None
        if owner_role_acknowledged(user, school):
            return None

        confirm_url = _safe_reverse("accounts:owner_confirm_role")
        if not confirm_url:
            # Without the confirm endpoint the card can't be dismissed — don't show it.
            return None

        owner_name = (
            (getattr(user, "get_full_name", lambda: "")() or "").strip()
            or getattr(user, "first_name", "")
            or getattr(user, "get_username", lambda: "")()
            or _("there")
        )
        return {
            "school_name": (getattr(school, "name", "") or _("your school")).strip(),
            "owner_name": owner_name,
            "role_label": _role_label(user, membership),
            "confirm_url": confirm_url,
            "assign_url": _safe_reverse("accounts:tenant_identity_invite"),
            "roster_url": _safe_reverse("accounts:tenant_identity_roster"),
        }
    except Exception as exc:  # noqa: BLE001 — a landing card must never break the page
        logger.debug("build_owner_first_login_card failed: %s", exc)
        return None
