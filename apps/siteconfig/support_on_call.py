"""v4.00.43 — On-call rotation selectors.

Single source of truth for "who is on call right now?". Used by:
  - ``_pick_support_owner`` (portal) to prefer the on-call user over the
    role-based fallback chain when creating a new ticket.
  - ``support_sla_breach_sweep`` (Celery beat) to escalate to the backup
    on-call user when a primary doesn't respond inside the SLA window.

Implementation is deliberately tiny and time-window-driven: a shift covers
the half-open window ``[starts_at, ends_at)``. Helpers return the live
``User`` instance or ``None`` when no one is on call.
"""

from __future__ import annotations

from typing import Iterable

from django.utils import timezone


def _active_shifts_qs(role_tag: str = ""):
    """Return active SupportOnCallShift queryset (ordered, freshest first)."""
    from apps.siteconfig.models_feature_controls import SupportOnCallShift

    now = timezone.now()
    qs = SupportOnCallShift.objects.select_related("user").filter(
        starts_at__lte=now, ends_at__gt=now
    )
    if role_tag:
        qs = qs.filter(role_tag=role_tag)
    return qs.order_by("-is_primary", "-starts_at", "-id")


def get_active_on_call_user(role_tag: str = ""):
    """Return the User currently on the *primary* shift (or None)."""
    shift = _active_shifts_qs(role_tag).filter(is_primary=True).first()
    if shift is None:
        # Honor any active shift if no primary is set.
        shift = _active_shifts_qs(role_tag).first()
    return shift.user if shift else None


def get_active_backup_users(role_tag: str = "") -> list:
    """Return all secondary on-call Users currently active (excluding the primary)."""
    primary = get_active_on_call_user(role_tag=role_tag)
    primary_id = getattr(primary, "id", None)
    backups = []
    for shift in _active_shifts_qs(role_tag).filter(is_primary=False):
        if shift.user and getattr(shift.user, "id", None) != primary_id:
            backups.append(shift.user)
    return backups


def iter_escalation_chain(role_tag: str = "") -> Iterable:
    """Yield primary then backups in escalation order (no duplicates)."""
    seen: set = set()
    primary = get_active_on_call_user(role_tag=role_tag)
    if primary is not None and primary.id not in seen:
        seen.add(primary.id)
        yield primary
    for user in get_active_backup_users(role_tag=role_tag):
        if user.id not in seen:
            seen.add(user.id)
            yield user


def get_first_backup(role_tag: str = ""):
    """Return the first backup user (None when there isn't one)."""
    backups = get_active_backup_users(role_tag=role_tag)
    return backups[0] if backups else None


def prefer_on_call(default_user, role_tag: str = ""):
    """Pick the on-call user when available; otherwise fall through to default."""
    on_call = get_active_on_call_user(role_tag=role_tag)
    return on_call or default_user
