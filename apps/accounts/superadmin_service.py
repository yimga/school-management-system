"""Shared platform-superadmin promotion service.

Single source of truth for making — or un-making — a platform super-admin. A
promotion sets the THREE authority signals TOGETHER (``is_staff`` + ``is_superuser``
+ ``is_active`` + ``role=SUPERADMIN``) so a user is never half-provisioned: the RBAC
role alone never sets the Django flags that operator surfaces gate on, which is the
"assigned SUPERADMIN but still locked out" bug this closes.

Used by both the ``promote_superadmin`` management command and the operator
promotion console. Because the save touches authority fields, the User post_save
signal in ``apps.accounts.signals_access`` invalidates derived caches and pushes an
``access_changed`` event, so the change propagates in real time (the target's open
session refreshes without re-login).
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model

logger = logging.getLogger("security.superadmin_promotion")

User = get_user_model()

_ROLE = getattr(User, "Role", None)
SUPERADMIN_ROLE_VALUE = (
    getattr(_ROLE, "SUPERADMIN", None) if _ROLE is not None else None
)


def _target_state(user: Any, demote: bool) -> dict[str, Any]:
    """The authority fields + values a promote (or demote) intends to write."""
    if demote:
        # Remove god-mode only. Leave is_active + role alone — never lock a user
        # out of their own account, never guess a replacement role.
        return {"is_superuser": False, "is_staff": False}
    state: dict[str, Any] = {"is_staff": True, "is_superuser": True, "is_active": True}
    if SUPERADMIN_ROLE_VALUE is not None and hasattr(user, "role"):
        state["role"] = SUPERADMIN_ROLE_VALUE
    return state


def compute_superadmin_changes(user: Any, *, demote: bool = False) -> list[str]:
    """Human-readable list of field changes a promote/demote WOULD apply.

    Empty when the user is already in the target state (idempotent no-op) — used
    for dry-run previews and success messaging.
    """
    return [
        f"{field} -> {value}"
        for field, value in _target_state(user, demote).items()
        if getattr(user, field, None) != value
    ]


def apply_superadmin_change(
    user: Any, *, actor: Any = None, demote: bool = False
) -> list[str]:
    """Promote (or demote) ``user`` to/from platform super-admin, idempotently.

    Returns the applied changes (empty if already in the target state). Writes only
    the authority fields via ``update_fields`` so the access-realtime signal fires.
    Security-audit-logs the actor + target.
    """
    changes = compute_superadmin_changes(user, demote=demote)
    if not changes:
        return []
    target = _target_state(user, demote)
    for field, value in target.items():
        setattr(user, field, value)
    user.save(update_fields=list(target.keys()))
    _audit(user, actor=actor, demote=demote, changes=changes)
    return changes


def _audit(user: Any, *, actor: Any, demote: bool, changes: list[str]) -> None:
    """Record the privilege change to the security log (best-effort)."""
    try:
        logger.warning(
            "platform-superadmin %s: actor_pk=%s target_pk=%s target=%s changes=%s",
            "demote" if demote else "promote",
            getattr(actor, "pk", None),
            getattr(user, "pk", None),
            user.get_username(),
            changes,
        )
    except Exception:  # noqa: BLE001 — audit logging must never break the write
        pass
