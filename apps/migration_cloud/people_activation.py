"""Post-import activation of parents and teachers landed by Migration Cloud.

Imported people get an unusable password on purpose (no credential is minted
during apply). This module is the operator surface that then:

* emails a one-time set-password link when a real mailbox exists, or
* issues a one-time temporary password for an admin to hand over in person.

Both paths force password change + profile setup on first login. Passwords are
returned to the caller for a one-shot CSV and are never logged.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any, Iterable

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.utils import timezone

from apps.accounts.credential_reset import set_temporary_password
from apps.accounts.email_delivery_policy import is_deliverable_email

logger = logging.getLogger(__name__)

_HANDOVER_CAP = 5000  # magic-number-allow: one-time-handover-sheet-row-ceiling
_INVITE_CAP = 5000  # magic-number-allow: bulk-invite-recipient-ceiling


def activation_snapshot(school) -> dict[str, Any] | None:
    """Counts of imported people still waiting to sign in. ``None`` if nothing to do."""
    if school is None:
        return None
    try:
        from apps.migration_cloud.staff_role_map import promote_imported_staff_roles

        promote_imported_staff_roles(school=school)
    except Exception:  # noqa: BLE001 — backfill is additive; snapshot must still render
        logger.warning(
            "people_activation.staff_role_backfill_failed school=%s",
            getattr(school, "pk", None),
            exc_info=True,
        )
    parents = list(_unactivated_parents(school))
    staff = list(_unactivated_staff(school))
    if not parents and not staff:
        return None
    parent_inviteable = [u for u in parents if is_deliverable_email(getattr(u, "email", ""))]
    staff_inviteable = [u for u in staff if is_deliverable_email(getattr(u, "email", ""))]
    return {
        "parent_count": len(parents),
        "staff_count": len(staff),
        "parent_inviteable": len(parent_inviteable),
        "staff_inviteable": len(staff_inviteable),
        "parent_handover": len(parents) - len(parent_inviteable),
        "staff_handover": len(staff) - len(staff_inviteable),
    }


def invite_unactivated_parents(*, school, request=None) -> dict[str, Any]:
    from apps.accounts.guardian_invite import send_guardian_invite

    sent = skipped = failed = 0
    remainder: list = []
    for user in _unactivated_parents(school)[:_INVITE_CAP]:
        out = send_guardian_invite(user, request=request, school=school)
        if out.get("sent"):
            sent += 1
        else:
            remainder.append(user)
            if out.get("reason") in ("no_email", "undeliverable_email"):
                skipped += 1
            else:
                failed += 1
    logger.info(
        "people_activation.parent_invite school=%s sent=%s skipped=%s failed=%s",
        getattr(school, "pk", None),
        sent,
        skipped,
        failed,
    )
    return {"sent": sent, "skipped": skipped, "failed": failed, "remainder": remainder}


def invite_unactivated_staff(*, school, request=None) -> dict[str, Any]:
    from apps.accounts.guardian_invite import send_staff_setup_invite

    sent = skipped = failed = 0
    remainder: list = []
    for user in _unactivated_staff(school)[:_INVITE_CAP]:
        out = send_staff_setup_invite(user, request=request, school=school)
        if out.get("sent"):
            sent += 1
        else:
            remainder.append(user)
            if out.get("reason") in ("no_email", "undeliverable_email"):
                skipped += 1
            else:
                failed += 1
    logger.info(
        "people_activation.staff_invite school=%s sent=%s skipped=%s failed=%s",
        getattr(school, "pk", None),
        sent,
        skipped,
        failed,
    )
    return {"sent": sent, "skipped": skipped, "failed": failed, "remainder": remainder}


def activate_mail_then_handover(*, school, kind: str, request=None) -> HttpResponse | None:
    """Email who we can; return a password CSV for everyone mail did not reach.

    Successfully emailed users keep their unusable password (the invite link is
    the credential). Remainder — SMTP failure, no mailbox, undeliverable —
    get one-time passwords in the download. ``None`` means every invite sent.
    """
    kind = (kind or "").strip().lower()
    if kind == "parents":
        out = invite_unactivated_parents(school=school, request=request)
    else:
        out = invite_unactivated_staff(school=school, request=request)
    remainder = list(out.get("remainder") or [])
    if not remainder:
        return None
    return handover_csv_response(school=school, kind=kind, users=remainder)


def handover_csv_response(*, school, kind: str, users=None) -> HttpResponse:
    """One-shot CSV of temporary passwords. Never logs the secrets."""
    kind = (kind or "").strip().lower()
    if users is None:
        if kind == "parents":
            users = _unactivated_parents(school)[:_HANDOVER_CAP]
            filename = f"parent-first-login-{timezone.now().strftime('%Y%m%d-%H%M%S')}.csv"
        else:
            users = _unactivated_staff(school)[:_HANDOVER_CAP]
            filename = f"teacher-first-login-{timezone.now().strftime('%Y%m%d-%H%M%S')}.csv"
    else:
        users = list(users)[:_HANDOVER_CAP]
        prefix = "parent" if kind == "parents" else "teacher"
        filename = f"{prefix}-first-login-{timezone.now().strftime('%Y%m%d-%H%M%S')}.csv"
    rows = _issue_handover_rows(users)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["full_name", "username", "temporary_password", "role", "must_change_on_first_login"]
    )
    writer.writerows(rows)
    response = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    # The body is cleartext, single-use credentials for up to _HANDOVER_CAP
    # accounts. HtmlNoCacheMiddleware only stamps text/html, so without these a
    # text/csv download carries NO cache directives at all and can be written to
    # the browser/proxy disk cache of a shared school machine.
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    logger.info(
        "people_activation.handover school=%s kind=%s count=%s",
        getattr(school, "pk", None),
        kind,
        len(rows),
    )
    return response


def _issue_handover_rows(users: Iterable) -> list[list[str]]:
    rows: list[list[str]] = []
    for user in users:
        temp = _issue_first_login_temp_password(user)
        if not temp:
            continue
        rows.append(
            [
                (user.get_full_name() or "").strip() or user.username,
                user.username,
                temp,
                getattr(user, "role", "") or "",
                "yes",
            ]
        )
    return rows


def _issue_first_login_temp_password(user) -> str:
    try:
        temp, _reactivated = set_temporary_password(user)
    except Exception:  # noqa: BLE001 — one bad row must not abort the sheet
        logger.warning(
            "people_activation.temp_password_failed user_id=%s",
            getattr(user, "pk", None),
            exc_info=True,
        )
        return ""
    try:
        user.profile_setup_completed = False
        user.save(update_fields=["profile_setup_completed"])
    except Exception:  # noqa: BLE001
        logger.warning(
            "people_activation.profile_flag_failed user_id=%s",
            getattr(user, "pk", None),
            exc_info=True,
        )
    return temp


def _unactivated_parents(school) -> list:
    User = get_user_model()
    parent_role = User.Role.PARENT
    from apps.people.models import StudentGuardian

    user_ids = (
        StudentGuardian.objects.filter(  # tenant-isolation-allow: school-scoped guardian directory for activation
            student__school=school,
            guardian_user__isnull=False,
            is_active=True,
        )
        .values_list("guardian_user_id", flat=True)
        .distinct()
    )
    users = list(
        User.objects.filter(pk__in=user_ids, role=parent_role).order_by("last_name", "first_name")
    )
    return [u for u in users if not u.has_usable_password()]


def _unactivated_staff(school) -> list:
    User = get_user_model()
    from apps.people.models import TeacherProfile

    user_ids = TeacherProfile.objects.filter(  # tenant-isolation-allow: school-scoped staff directory for activation
        school=school,
        user__isnull=False,
    ).values_list("user_id", flat=True)
    excluded = (
        User.Role.PARENT,
        User.Role.STUDENT,
        User.Role.EMPLOYER,
        User.Role.SUPERADMIN,
    )
    users = list(
        User.objects.filter(pk__in=user_ids)
        .exclude(role__in=excluded)
        .order_by("last_name", "first_name")
    )
    return [u for u in users if not u.has_usable_password()]
