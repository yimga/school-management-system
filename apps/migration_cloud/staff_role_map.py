"""Map a migration-workbook staff ``role`` cell onto a live ``User.Role``.

Staff rosters (and OneRoster ``users.csv`` files classified as staff) carry a
role/position column. The staff lander used to provision every row as TEACHER
and only stash the source string on DynamicFieldValue — so a bursar, HOD, or
principal never received the dashboard that column asked for.

Contract:
* Known staff roles from ``User.Role`` are assigned on User + SchoolMembership.
* SUPERADMIN / PARENT / STUDENT / EMPLOYER are never granted from a staff sheet.
* A label we cannot map is NOT quietly granted a role. TEACHER is not an
  inert token -- the ``post_save`` in ``apps.accounts.signals`` attaches the
  TEACHER ``AccessRole``, whose migration-seeded codes include
  ``attendance.manage`` and ``grades.enter`` -- so collapsing an unreadable
  privilege onto it is privilege inflation. ``unresolvable_staff_role`` names
  the problem and the staff lander HOLDS the row for review instead.
* ``resolve_staff_role`` keeps its collapse-to-``default`` behaviour for the
  backfill callers that depend on it (the source string is still preserved).
* Activated accounts (usable password) keep their live role on re-import.
"""

from __future__ import annotations

import re
from typing import Final

from apps.platform_runtime.role_registry import ROLE_TEACHER, normalize_role

_SPLIT_RE = re.compile(r"[\s_\-/|,;.]+")

# Labels seen on African / TVET / OneRoster staff sheets. Values are User.Role
# member NAMES so this module stays importable without the ORM at module level.
_ALIAS_TO_ROLE_NAME: dict[str, str] = {
    "teacher": "TEACHER",
    "enseignant": "TEACHER",
    "instructeur": "TEACHER",
    "instructor": "TEACHER",
    "faculty": "TEACHER",
    "aide": "TEACHER",
    "proctor": "TEACHER",
    "tutor": "TEACHER",
    "lecturer": "TEACHER",
    "admin": "ADMIN",
    "administrator": "ADMIN",
    "administrateur": "ADMIN",
    "schooladmin": "ADMIN",
    "principal": "PRINCIPAL",
    "proviseur": "PRINCIPAL",
    "headteacher": "PRINCIPAL",
    "headmaster": "PRINCIPAL",
    "headmistress": "PRINCIPAL",
    "headofschool": "PRINCIPAL",
    "viceprincipal": "VICE_PRINCIPAL",
    "deputyprincipal": "VICE_PRINCIPAL",
    "viceproviseur": "VICE_PRINCIPAL",
    "dean": "DEAN",
    "doyen": "DEAN",
    "censor": "CENSOR",
    "censeur": "CENSOR",
    "bursar": "BURSAR",
    "intendant": "BURSAR",
    "econome": "BURSAR",
    "accountant": "ACCOUNTANT",
    "comptable": "ACCOUNTANT",
    "hod": "HOD",
    "headofdepartment": "HOD",
    "chefdedepartement": "HOD",
    "deptlead": "DEPT_LEAD",
    "departmentlead": "DEPT_LEAD",
    "leadership": "LEADERSHIP",
    "director": "LEADERSHIP",
    "it": "IT_ADMIN",
    "itadmin": "IT_ADMIN",
    "informaticien": "IT_ADMIN",
    "dpo": "DPO",
    "secretary": "SECRETARY",
    "secretaire": "SECRETARY",
    "registrar": "ACADEMICS_STAFF",
    "academicstaff": "ACADEMICS_STAFF",
    "academicsstaff": "ACADEMICS_STAFF",
    "financestaff": "FINANCE_STAFF",
    "finance": "FINANCE_STAFF",
    "comms": "COMMS_STAFF",
    "communications": "COMMS_STAFF",
    "boarding": "BOARDING_MANAGER",
    "boardingmanager": "BOARDING_MANAGER",
    "discipline": "DISCIPLINE_MASTER",
    "disciplinemaster": "DISCIPLINE_MASTER",
    "surveillantgeneral": "DISCIPLINE_MASTER",
    "proprietor": "PROPRIETOR",
    "owner": "PROPRIETOR",
    "promoteur": "PROPRIETOR",
    "executiveassistant": "EXECUTIVE_ASSISTANT",
    "virtualassistant": "VIRTUAL_ASSISTANT",
    # Anglophone-system compound titles measured on a real staff directory
    # (2026-09-02): every one of these compacted to a string this map had no
    # entry for, so a principal's cabinet imported as held-for-review rows.
    "deanofstudies": "DEAN",
    "deanofstudy": "DEAN",
    "seniordisciplinemaster": "DISCIPLINE_MASTER",
    "systemadministrator": "IT_ADMIN",
    "schoolsystemadministrator": "IT_ADMIN",
    "sysadmin": "IT_ADMIN",
    "administrativeassistant": "SECRETARY",
    "adminassistant": "SECRETARY",
}


def _forbidden_roles() -> frozenset[str]:
    from apps.accounts.models import User

    return frozenset(
        {
            User.Role.SUPERADMIN,
            User.Role.PARENT,
            User.Role.STUDENT,
            User.Role.EMPLOYER,
        }
    )


def _role_values() -> set[str]:
    from apps.accounts.models import User

    return {choice[0] for choice in User.Role.choices}


def _compact(raw: str) -> str:
    return "".join(_SPLIT_RE.split((raw or "").strip().lower()))


#: A non-empty label that matches no role and no alias. The sheet claimed a
#: privilege this system cannot name, so nothing may be granted for it.
ROLE_UNMAPPED: Final = "unmapped"

#: A label naming a role a staff sheet may never grant (SUPERADMIN / PARENT /
#: STUDENT / EMPLOYER). The claim is legible, and refused.
ROLE_FORBIDDEN: Final = "forbidden"


def _match_staff_role(raw: object) -> tuple[str | None, str | None]:
    """Resolve a source role cell to ``(role, problem)``.

    ``(None, None)``     the cell is blank. No privilege was claimed, so the
                         caller's own ``default`` decides -- a payroll sheet
                         with no role column is not a security event.
    ``(role, None)``     the label names, or aliases onto, a grantable role.
    ``(None, problem)``  the label cannot be honoured; ``problem`` is
                         :data:`ROLE_FORBIDDEN` or :data:`ROLE_UNMAPPED`.

    The single place the alias/allow/forbid decision is made, so
    :func:`resolve_staff_role` and :func:`unresolvable_staff_role` can never
    disagree about whether a label was understood.
    """
    token = normalize_role(raw)
    if not token:
        return None, None
    forbidden = _forbidden_roles()
    if token in forbidden:
        return None, ROLE_FORBIDDEN
    allowed = _role_values()
    if token in allowed:
        return token, None
    alias = _ALIAS_TO_ROLE_NAME.get(_compact(token))
    if alias and alias in allowed and alias not in forbidden:
        return alias, None
    # Compound cells -- "BURSAR/ PARTNER", "TEACHER /DRIVER" -- resolve ONLY when
    # every segment that names a role names the SAME role. Two different roles in
    # one cell ("ADMINISTRATIVE ASSISTANT / IT") is a claim this map must not
    # arbitrate: picking either would grant a privilege the sheet did not clearly
    # state, so the row stays held for a person. A forbidden segment forbids the
    # whole cell. Split on strong delimiters only, never spaces.
    raw_text = str(raw or "")
    if any(d in raw_text for d in "/|,;"):
        seen: set[str] = set()
        for seg in re.split(r"[/|,;]+", raw_text):
            seg_token = normalize_role(seg)
            if not seg_token:
                continue
            if seg_token in forbidden:
                return None, ROLE_FORBIDDEN
            if seg_token in allowed:
                seen.add(seg_token)
                continue
            seg_alias = _ALIAS_TO_ROLE_NAME.get(_compact(seg_token))
            if seg_alias and seg_alias in forbidden:
                return None, ROLE_FORBIDDEN
            if seg_alias and seg_alias in allowed:
                seen.add(seg_alias)
        if len(seen) == 1:
            return next(iter(seen)), None
    return None, ROLE_UNMAPPED


def unresolvable_staff_role(raw: object) -> str | None:
    """Why this source role cell cannot be honoured, or ``None`` if it can.

    Ask this BEFORE :func:`resolve_staff_role` anywhere a role decides what a
    provisioned account can reach. ``resolve_staff_role`` answers "what do I
    write?" and always has an answer; this answers "did I understand the
    source at all?", and a ``None`` here is the only thing that makes the
    former's answer safe to act on.
    """
    return _match_staff_role(raw)[1]


def resolve_staff_role(raw: object, *, default: str | None = None) -> str:
    """Return a safe ``User.Role`` token for a workbook/SIS role cell.

    Unchanged, deliberately: an unmapped or forbidden label still collapses to
    ``default`` (TEACHER when the caller names none). The backfill callers in
    this module rely on that -- ``promote_imported_staff_roles`` reads the
    collapse as "nothing to promote" and leaves the account alone. A caller
    that PROVISIONS access must not act on this answer without first asking
    :func:`unresolvable_staff_role`.
    """
    role, _problem = _match_staff_role(raw)
    if role is not None:
        return role
    return default if default is not None else ROLE_TEACHER


def is_staff_setup_role(raw: object) -> bool:
    """True when this user may complete the migrated-staff set-password page."""
    token = normalize_role(raw)
    if not token or token in _forbidden_roles():
        return False
    return token in _role_values()


def apply_imported_staff_role(*, user, school, role: str) -> None:
    """Write workbook role onto an unactivated user + school membership.

    Live accounts (usable password) keep their current role so a delta re-upload
    cannot silently demote a bursar who already signed in. SUPERADMIN is never
    written. Best-effort; never raises.
    """
    if user is None or not getattr(user, "pk", None):
        return
    role = resolve_staff_role(role)
    try:
        from apps.accounts.models import User

        if getattr(user, "role", None) == User.Role.SUPERADMIN:
            return
    except Exception:  # noqa: BLE001
        return
    try:
        live = bool(user.has_usable_password())
    except Exception:  # noqa: BLE001
        live = True
    if live:
        role_for_membership = getattr(user, "role", None) or role
        _attach_membership(user, school, role_for_membership, update_role=False)
        return
    current = getattr(user, "role", None) or ""
    if current != role:
        try:
            user.role = role
            user.save(update_fields=["role"])
        except Exception:  # noqa: BLE001
            return
    _attach_membership(user, school, role, update_role=True)


def _attach_membership(user, school, role: str, *, update_role: bool) -> None:
    if school is None:
        return
    try:
        from apps.migration_cloud.guardian_directory import ensure_school_membership

        ensure_school_membership(
            user=user, school=school, role=role, update_role=update_role
        )
    except Exception:  # noqa: BLE001 — membership is additive
        return


def _dfv_source_role_text(value_json) -> str:
    if isinstance(value_json, dict):
        raw = value_json.get("v", "")
    else:
        raw = value_json
    return str(raw or "").strip()


def _imported_role_label(profile, source_role_json) -> str:
    """Workbook role stored on DFV / position_title before User.role was written."""
    from_dfv = _dfv_source_role_text(source_role_json)
    if from_dfv:
        return from_dfv
    title = (getattr(profile, "position_title", None) or "").strip()
    if title:
        return title
    attrs = getattr(profile, "custom_attributes", None) or {}
    if isinstance(attrs, dict):
        for key in ("role", "fonction", "poste", "title", "job_title", "designation"):
            text = str(attrs.get(key) or "").strip()
            if text:
                return text
    return ""


def promote_imported_staff_roles(*, school, dry_run: bool = False) -> dict[str, int]:
    """Lift stored workbook roles onto users still sitting on TEACHER.

    Staff imported before ``apply_imported_staff_role`` kept the bursar/HOD
    string on ``position_title`` / DFV ``source_role`` while ``User.role`` stayed
    TEACHER. Opening the review page or a later apply runs this so those
    accounts get the dashboard the workbook asked for — no Repair required.
    Live passwords and SUPERADMIN are never rewritten.
    """
    empty = {"updated": 0, "skipped_live": 0, "skipped_none": 0}
    if school is None:
        return empty
    try:
        from apps.accounts.models import User
        from apps.metadata.models import DynamicFieldValue
        from apps.people.models import TeacherProfile
    except Exception:  # noqa: BLE001
        return empty

    profiles = list(
        TeacherProfile.objects.filter(  # tenant-isolation-allow: school-scoped staff-role backfill after import
            school=school,
            user__isnull=False,
        ).select_related("user")
    )
    if not profiles:
        return empty
    dfv_by_entity: dict[str, object] = {}
    try:
        pks = [str(p.pk) for p in profiles]
        for row in DynamicFieldValue.objects.filter(  # tenant-isolation-allow: school-scoped imported source_role
            school=school,
            entity_type="staff",
            entity_id__in=pks,
            field_key="source_role",
        ):
            dfv_by_entity[str(row.entity_id)] = row.value_json
    except Exception:  # noqa: BLE001 — DFV is additive; position_title still works
        dfv_by_entity = {}

    teacher_token = User.Role.TEACHER if hasattr(User, "Role") else ROLE_TEACHER
    updated = skipped_live = skipped_none = 0
    for profile in profiles:
        user = profile.user
        if user is None:
            skipped_none += 1
            continue
        if getattr(user, "role", None) == User.Role.SUPERADMIN:
            skipped_live += 1
            continue
        try:
            live = bool(user.has_usable_password())
        except Exception:  # noqa: BLE001
            live = True
        if live:
            skipped_live += 1
            continue
        current = getattr(user, "role", None) or ""
        if current and current != teacher_token:
            skipped_none += 1
            continue
        raw = _imported_role_label(profile, dfv_by_entity.get(str(profile.pk)))
        resolved = resolve_staff_role(raw)
        if resolved == teacher_token or resolved == current:
            skipped_none += 1
            continue
        if not dry_run:
            apply_imported_staff_role(user=user, school=school, role=resolved)
        updated += 1
    return {
        "updated": updated,
        "skipped_live": skipped_live,
        "skipped_none": skipped_none,
    }
