"""
Conversion lock: explicit first-value completion in school.settings (no URL heuristics).

``record_conversion_first_action`` is the only supported way to set completion; call from
model signals (attendance, marks, reports, payments) and domain services.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.schools.activation_gate import clear_activation_gate

logger = logging.getLogger(__name__)

RMC_CONVERSION = "rmc_conversion"

#: Roles the conversion lock must never wall, because no first-value action is
#: reachable to them in the first place. ``record_conversion_first_action`` is
#: only ever called from attendance, marks, report and payment paths — every one
#: a staff or guardian surface. A learner therefore cannot clear this lock no
#: matter what they do, so locking them buys the funnel nothing and instead
#: leaves them on /activation/first-action/ with a portal where the only
#: reachable link is /help/ (measured: 1 of 7 advertised actions).
#:
#: This is the same reasoning that opened "/portal/parent/" in
#: ``conversion_lock_paths`` — "the lock exists to make the SCHOOL record its
#: first value, and a <user> cannot clear it" — applied to the one role that
#: precedent missed. Parents stay locked here because they CAN clear it: a
#: payment counts, and they pay from an allowlisted path.
CONVERSION_LOCK_EXEMPT_ROLES: frozenset[str] = frozenset({"STUDENT"})


def deployment_is_edge_replica() -> bool:
    """True on a sovereign box — conversion is a cloud SaaS funnel, not an ops gate.

    An edge replica already exists as a live school in the cloud. Walling every
    tenant page behind Activation First Action (including Sync Center) prevents
    the box from converging even when the WAN is up. Cloud SaaS keeps the lock.
    """
    if bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False)):
        return True
    profile = str(getattr(settings, "RMC_DEPLOYMENT_PROFILE", "") or "").strip().lower()
    return profile in {"edge", "offline"}


def user_is_conversion_lock_exempt(user) -> bool:
    """Is ``user`` in a role the lock cannot meaningfully apply to?

    Staff and superusers are never exempt regardless of the ``role`` column —
    an elevated account carries operator surfaces the funnel is aimed at.
    """
    if user is None:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return False
    role = str(getattr(user, "role", "") or "").upper()
    return role in CONVERSION_LOCK_EXEMPT_ROLES


def _conv(school) -> dict[str, Any]:
    st: dict[str, Any] = dict(getattr(school, "settings", None) or {})
    return dict(st.get(RMC_CONVERSION) or {})


def school_first_action_completed(school) -> bool:
    if not school:
        return True
    return bool(_conv(school).get("first_action_completed"))


def school_conversion_is_locked(school, *, user) -> bool:
    """
    When CONVERSION_LOCK_STRICT is on, tenant users stay locked until first action.

    Modes:
    - CONVERSION_LOCK_ALL_SCHOOLS: every tenant without first_action is locked.
    - else: only schools with activation gate pending (post-provision path).

    Roles in ``CONVERSION_LOCK_EXEMPT_ROLES`` are never locked — see that
    constant for why. Both production callers (the middleware and the tenant
    experience strip's ``_conversion_lock_active``) route through here, so the
    exemption keeps enforcement and the advertised CTAs in agreement.
    """
    if not getattr(settings, "CONVERSION_LOCK_STRICT", False):
        return False
    if not school or not user or not getattr(user, "is_authenticated", False):
        return False
    if user_is_conversion_lock_exempt(user):
        return False
    if school_first_action_completed(school):
        return False
    if deployment_is_edge_replica():
        return False
    if getattr(settings, "CONVERSION_LOCK_ALL_SCHOOLS", False):
        return True
    from apps.schools.activation_gate import school_activation_gate_pending

    return school_activation_gate_pending(school)


def record_conversion_first_action(
    school,
    *,
    source: str,
    request=None,
    user=None,
) -> bool:
    """
    Mark first value action complete (idempotent). Clears activation gate, emits funnel first_action once.
    """
    if not school:
        return False
    if school_first_action_completed(school):
        return False
    from django.db import transaction

    with transaction.atomic():
        from apps.schools.models import School

        school = School.objects.select_for_update().get(pk=school.pk)
        st = dict(school.settings or {})
        conv = dict(st.get(RMC_CONVERSION) or {})
        if conv.get("first_action_completed"):
            return False
        conv["first_action_completed"] = True
        conv["source"] = (source or "")[:200]
        conv["completed_at"] = timezone.now().isoformat()
        st[RMC_CONVERSION] = conv
        school.settings = st
        school.save(update_fields=["settings", "updated_at"])
    try:
        clear_activation_gate(school)
    except Exception:
        logger.debug("clear_activation_gate after conversion", exc_info=True)
    u = user or (getattr(request, "user", None) if request is not None else None)
    try:
        if request is not None:
            from apps.schools.funnel_events import record_school_funnel_once

            record_school_funnel_once(
                "first_action", school, request, user=u, metadata={"source": source}
            )
        else:
            from apps.schools.funnel_events import record_first_action_signal

            record_first_action_signal(
                school, user=u, metadata={"source": source}
            )
    except Exception:
        logger.debug("funnel first_action after conversion", exc_info=True)
    try:
        from apps.platform_runtime.event_bus import publish_event

        tid = str(school.pk)
        publish_event(
            "conversion_first_action",
            {"school_id": tid, "source": (source or "")[:200]},
            tenant_id=tid,
            school_id=school.pk,
            idempotency_key=f"conversion_first_action:{school.pk}",
        )
    except Exception:
        logger.debug("conversion_first_action platform event skipped", exc_info=True)
    return True
