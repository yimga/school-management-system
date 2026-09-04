"""Bulk staff-role assignment for the backend teacher/staff list.

This is the other half of the import change made on 2026-09-04. An import now
lands a person it cannot classify on SUPPORT_STAFF, which holds nothing, instead
of refusing the row -- so a real directory arrives complete, with some number of
people sitting on the base role carrying their source job title as a note. The
operator then has to be able to say "these four are drivers" without opening four
profiles, or the import change just moved the manual work somewhere else.

Safety is the same rule the importer follows, enforced here again rather than
assumed: SUPERADMIN / PARENT / STUDENT / EMPLOYER can never be assigned from this
surface. It is reached with people.change_teacherprofile, which is not the same
permission as "may grant platform administration", and a bulk endpoint that
accepts an arbitrary role string is a privilege-escalation primitive.

Writing ``User.role`` is what actually grants: the post_save in
apps.accounts.signals materialises the matching AccessRole onto ``user.roles``,
so the capabilities follow from the assignment without this module touching the
permission tables at all.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.people.models import TeacherProfile

MAX_BULK_IDS = 200

#: Roles a staff list may never grant. Same four the import refuses, for the same
#: reason -- these are not job titles, they are other kinds of account.
FORBIDDEN_ROLES = frozenset(
    {
        User.Role.SUPERADMIN,
        User.Role.PARENT,
        User.Role.STUDENT,
        User.Role.EMPLOYER,
    }
)

ALLOWED_STAFF_ROLES = frozenset(
    choice[0] for choice in User.Role.choices if choice[0] not in FORBIDDEN_ROLES
)


def parse_staff_id_list(raw_ids: Any) -> list[int]:
    """Ids of the TeacherProfile rows the operator ticked."""
    if not raw_ids or not isinstance(raw_ids, (list, tuple)):
        return []
    out: list[int] = []
    for item in raw_ids:
        if isinstance(item, int) and item > 0:
            out.append(item)
        else:
            text = str(item or "").strip()
            if text.isdigit():
                out.append(int(text))
        if len(out) >= MAX_BULK_IDS:
            break
    return out


def bulk_set_staff_role(*, staff_ids: list[int], role: str, school) -> dict[str, Any]:
    """Assign one role to many staff, refusing what a staff surface may not grant."""
    role = str(role or "").strip().upper()
    if role in FORBIDDEN_ROLES:
        raise ValueError(
            "%s cannot be granted from the staff list. It is not a job title." % role
        )
    if role not in ALLOWED_STAFF_ROLES:
        raise ValueError("Unsupported role: %s" % role)
    if not staff_ids:
        raise ValueError("Select at least one staff member.")
    if school is None:
        raise ValueError("Tenant context required for a bulk staff mutation.")

    # school= is the tenant bound and is not optional: ids arrive from a request
    # body, so without it this endpoint would edit any school's staff by number.
    profiles = list(
        TeacherProfile.objects.filter(pk__in=staff_ids, school=school)
        .select_related("user")
        .order_by("pk")
    )
    found = {p.pk for p in profiles}
    results: list[dict[str, Any]] = []

    for profile in profiles:
        user = profile.user
        if user is None:
            results.append(
                {"id": profile.pk, "ok": False, "error": "No account on this record."}
            )
            continue
        if user.role in FORBIDDEN_ROLES:
            # Refusing to CHANGE these is a different guarantee from refusing to
            # assign them: a platform superadmin must not be demoted by someone
            # ticking a box on a tenant staff list.
            results.append(
                {
                    "id": profile.pk,
                    "ok": False,
                    "error": "This account's role cannot be changed here.",
                }
            )
            continue
        if user.role == role:
            results.append({"id": profile.pk, "ok": True, "message": "Already set."})
            continue
        with transaction.atomic():
            user.role = role
            # save() and not update(): the post_save signal is what materialises
            # the AccessRole, and a queryset update does not fire it -- the role
            # would change on screen while the capabilities did not.
            user.save(update_fields=["role"])
        results.append(
            {"id": profile.pk, "ok": True, "message": "Role set to %s." % role}
        )

    for missing in [sid for sid in staff_ids if sid not in found]:
        results.append({"id": missing, "ok": False, "error": "Staff member not found."})

    succeeded = sum(1 for row in results if row.get("ok"))
    return {
        "ok": succeeded > 0,
        "role": role,
        "processed": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }
