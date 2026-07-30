"""Per-user MFA-enrollment deferral — "skip MFA setup for a period".

A required user who was just handed a temporary password (or who simply is not
ready to enroll) may defer MFA setup for a bounded window instead of being
hard-walled on the very next navigation. The deferral is honored by
``RequireMFAMiddleware`` and the post-login redirect, which downgrade the
"enforce" wall to a pass-through nudge while the window is open — UNLESS the
principal must always be strict (platform superuser / platform admin / active
school owner), who can never defer (see
``apps.accounts.mfa_defaults.principal_requires_strict_mfa``).

The window is stored on ``User.mfa_setup_deferred_until``. It is cleared the
moment MFA is enrolled or reset, so it never lingers past its purpose.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

#: Hard ceiling on how long enrollment may be deferred. A user can never buy an
#: unbounded MFA holiday; an operator can lower this via settings but the option
#: list below is the offered menu.
MFA_SETUP_DEFERRAL_MAX_DAYS = 30

#: Offered "skip for" choices surfaced on the enrollment page.
MFA_SETUP_DEFERRAL_ALLOWED_DAYS: tuple[int, ...] = (7, 14, 30)

#: Fallback when the posted value is missing/garbage.
MFA_SETUP_DEFERRAL_DEFAULT_DAYS = 7


def _max_days() -> int:
    # settings-key-allow: optional operator lever, read with a default
    raw = getattr(settings, "MFA_SETUP_DEFERRAL_MAX_DAYS", MFA_SETUP_DEFERRAL_MAX_DAYS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return MFA_SETUP_DEFERRAL_MAX_DAYS
    return value if value >= 1 else MFA_SETUP_DEFERRAL_MAX_DAYS


def normalize_deferral_days(raw: object) -> int:
    """Clamp a requested deferral length to ``[1, max]`` with a safe default."""
    try:
        days = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        days = MFA_SETUP_DEFERRAL_DEFAULT_DAYS
    if days < 1:
        days = MFA_SETUP_DEFERRAL_DEFAULT_DAYS
    return min(days, _max_days())


def mfa_setup_deferral_active(user) -> bool:
    """True when ``user`` currently holds an unexpired MFA-setup deferral."""
    until = getattr(user, "mfa_setup_deferred_until", None)
    return bool(until) and until > timezone.now()


def mfa_setup_deferral_days_remaining(user) -> int:
    """Whole days left on the deferral window (0 when none/expired)."""
    until = getattr(user, "mfa_setup_deferred_until", None)
    if not until:
        return 0
    delta = until - timezone.now()
    return max(delta.days, 0)


def defer_mfa_setup(user, *, days, save: bool = True):
    """Grant/renew an MFA-setup deferral of ``days`` (clamped). Returns the deadline."""
    normalized = normalize_deferral_days(days)
    until = timezone.now() + timedelta(days=normalized)
    user.mfa_setup_deferred_until = until
    if save:
        user.save(update_fields=["mfa_setup_deferred_until"])
    return until


def clear_mfa_setup_deferral(user, *, save: bool = True) -> None:
    """Drop any deferral (called once MFA is enrolled or reset)."""
    if getattr(user, "mfa_setup_deferred_until", None) is not None:
        user.mfa_setup_deferred_until = None
        if save:
            user.save(update_fields=["mfa_setup_deferred_until"])
