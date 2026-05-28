"""
Lightweight ReBAC: Postgres tuples + check() with RBAC dual-run.

Devices receive signed read-only snapshots (see ``iam_snapshot.py``); they never
write tuples offline.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

SUBJECT_USER = "user"
OBJECT_SCHOOL = "school"
OBJECT_STUDENT = "student"
OBJECT_PERMISSION = "permission"
OBJECT_SUBJECT_ASSIGNMENT = "subject_assignment"
OBJECT_CLASSROOM = "classroom"

REL_MEMBER = "member"
REL_PARENT_OF = "parent_of"
REL_TEACHER_OF = "teacher_of"
REL_CAN = "can"


def rebac_enabled() -> bool:
    return bool(getattr(settings, "RMC_REBAC_ENABLED", True))


def rebac_dual_run_log() -> bool:
    return bool(getattr(settings, "RMC_REBAC_DUAL_RUN_LOG_MISMATCH", True))


def _subject_user_id(user) -> str:
    return str(getattr(user, "pk", "") or "")


def write_tuple(
    *,
    school,
    subject_type: str,
    subject_id: str,
    relation: str,
    object_type: str,
    object_id: str,
    source: str,
    source_key: str = "",
) -> tuple[Any, bool]:
    from apps.accounts.models_rebac import RelationshipTuple

    if school is None or not subject_id or not object_id:
        return None, False
    obj, created = RelationshipTuple.objects.update_or_create(
        school=school,
        subject_type=subject_type,
        subject_id=subject_id,
        relation=relation,
        object_type=object_type,
        object_id=object_id,
        defaults={
            "source": source,
            "source_key": (source_key or "")[:128],
        },
    )
    return obj, created


def delete_tuples_for_source(*, school, source: str, source_key: str) -> int:
    from apps.accounts.models_rebac import RelationshipTuple

    if school is None:
        return 0
    qs = RelationshipTuple.objects.filter(
        school=school,
        source=source,
        source_key=source_key,
    )
    count, _ = qs.delete()
    return count


def check(
    user,
    relation: str,
    object_type: str,
    object_id: str,
    *,
    school=None,
) -> bool:
    """
    Evaluate whether ``user`` has ``relation`` on ``object_type:object_id`` in ``school``.
    """
    if not rebac_enabled():
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if school is None:
        return False
    from apps.accounts.models_rebac import RelationshipTuple

    sid = _subject_user_id(user)
    if not sid:
        return False
    oid = str(object_id or "")
    if not oid:
        return False
    return RelationshipTuple.objects.filter(
        school=school,
        subject_type=SUBJECT_USER,
        subject_id=sid,
        relation=relation,
        object_type=object_type,
        object_id=oid,
    ).exists()


def check_permission_token(user, code: str, *, school=None) -> bool:
    """``can`` on ``permission:<code>``."""
    return check(
        user,
        REL_CAN,
        OBJECT_PERMISSION,
        (code or "").strip(),
        school=school,
    )


def feature_permission_allowed(user, code: str, *, school=None) -> bool:
    """
    Dual-run: colon RBAC remains authoritative; ReBAC mismatch is logged only.
    """
    rbac_ok = user.has_feature_permission(code, school=school)
    if not rebac_enabled() or not rebac_dual_run_log():
        return rbac_ok
    try:
        rebac_ok = check_permission_token(user, code, school=school)
    except Exception:
        logger.exception("rebac_check_failed code=%s", code)
        return rbac_ok
    if rbac_ok != rebac_ok:
        logger.warning(
            "rebac_rbac_mismatch user_id=%s school_id=%s code=%s rbac=%s rebac=%s",
            getattr(user, "pk", None),
            getattr(school, "pk", None),
            code,
            rbac_ok,
            rebac_ok,
        )
    return rbac_ok


def enforce_permission_token(user, code: str, *, school=None) -> bool:
    """When ``RMC_REBAC_ENFORCE_SENSITIVE`` is on, both RBAC and ReBAC must pass."""
    rbac_ok = user.has_feature_permission(code, school=school)
    if not rbac_ok:
        return False
    if not bool(getattr(settings, "RMC_REBAC_ENFORCE_SENSITIVE", False)):
        return True
    return check_permission_token(user, code, school=school)


def tuples_for_user(*, school, user) -> list[dict[str, str]]:
    from apps.accounts.models_rebac import RelationshipTuple

    sid = _subject_user_id(user)
    if not sid or school is None:
        return []
    rows = RelationshipTuple.objects.filter(
        school=school,
        subject_type=SUBJECT_USER,
        subject_id=sid,
    ).values("relation", "object_type", "object_id")
    return [
        {
            "relation": r["relation"],
            "object_type": r["object_type"],
            "object_id": r["object_id"],
        }
        for r in rows
    ]


def flatten_capabilities(user, *, school) -> list[str]:
    """Colon tokens this user may exercise in ``school`` (from ``can`` tuples)."""
    from apps.accounts.models_rebac import RelationshipTuple

    sid = _subject_user_id(user)
    if not sid or school is None:
        return []
    codes = (
        RelationshipTuple.objects.filter(
            school=school,
            subject_type=SUBJECT_USER,
            subject_id=sid,
            relation=REL_CAN,
            object_type=OBJECT_PERMISSION,
        )
        .values_list("object_id", flat=True)
        .distinct()
    )
    return sorted(c for c in codes if c)


@transaction.atomic
def rebuild_user_permission_tuples(user, *, school) -> int:
    """Rewrite ``can`` tuples from roles + direct grants for one school."""
    from apps.accounts.models import TemporaryRoleGrant
    from apps.accounts.models_rebac import RelationshipTuple

    if school is None or user is None:
        return 0
    sid = _subject_user_id(user)
    deleted, _ = RelationshipTuple.objects.filter(
        school=school,
        subject_type=SUBJECT_USER,
        subject_id=sid,
        relation=REL_CAN,
        object_type=OBJECT_PERMISSION,
        source__in=(
            RelationshipTuple.Source.ACCESS_ROLE,
            RelationshipTuple.Source.TEMPORARY_GRANT,
            RelationshipTuple.Source.DIRECT_PERMISSION,
        ),
    ).delete()
    written = 0
    for perm in user.feature_permissions.all():
        write_tuple(
            school=school,
            subject_type=SUBJECT_USER,
            subject_id=sid,
            relation=REL_CAN,
            object_type=OBJECT_PERMISSION,
            object_id=perm.code,
            source=RelationshipTuple.Source.DIRECT_PERMISSION,
            source_key=f"direct:{user.pk}:{perm.code}",
        )
        written += 1
    roles = user.roles.filter(
        models_q_school_scope(school),
    ).prefetch_related("permissions")
    for role in roles:
        for perm in role.permissions.all():
            write_tuple(
                school=school,
                subject_type=SUBJECT_USER,
                subject_id=sid,
                relation=REL_CAN,
                object_type=OBJECT_PERMISSION,
                object_id=perm.code,
                source=RelationshipTuple.Source.ACCESS_ROLE,
                source_key=f"role:{user.pk}:{role.pk}:{perm.code}",
            )
            written += 1
    now = timezone.now()
    grants = TemporaryRoleGrant.objects.filter(
        user=user,
        expires_at__gt=now,
    ).filter(
        models_q_grant_school(school),
    ).select_related("role").prefetch_related("role__permissions")
    for grant in grants:
        if grant.valid_from and grant.valid_from > now:
            continue
        role = grant.role
        for perm in role.permissions.all():
            write_tuple(
                school=school,
                subject_type=SUBJECT_USER,
                subject_id=sid,
                relation=REL_CAN,
                object_type=OBJECT_PERMISSION,
                object_id=perm.code,
                source=RelationshipTuple.Source.TEMPORARY_GRANT,
                source_key=f"grant:{grant.pk}:{perm.code}",
            )
            written += 1
    return written


def models_q_school_scope(school):
    from django.db.models import Q

    return Q(school__isnull=True) | Q(school_id=school.pk)


def models_q_grant_school(school):
    from django.db.models import Q

    return Q(role__school__isnull=True) | Q(role__school_id=school.pk)


def snapshot_integrity_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
