"""Map a migration-workbook staff ``role`` cell onto a live ``User.Role``.

Staff rosters (and OneRoster ``users.csv`` files classified as staff) carry a
role/position column. The staff lander used to provision every row as TEACHER
and only stash the source string on DynamicFieldValue — so a bursar, HOD, or
principal never received the dashboard that column asked for.

Contract:
* Known staff roles from ``User.Role`` are assigned on User + SchoolMembership.
* SUPERADMIN / PARENT / STUDENT / EMPLOYER are never granted from a staff sheet.
* Unknown labels fall back to TEACHER (the source string is still preserved).
* Activated accounts (usable password) keep their live role on re-import.
"""

from __future__ import annotations

import re

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
    "partner": "BURSAR",
    "bursarpartner": "BURSAR",
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


def resolve_staff_role(raw: object, *, default: str | None = None) -> str:
    """Return a safe ``User.Role`` token for a workbook/SIS role cell."""
    fallback = default if default is not None else ROLE_TEACHER
    token = normalize_role(raw)
    if not token:
        return fallback
    allowed = _role_values()
    forbidden = _forbidden_roles()
    if token in forbidden:
        return fallback
    if token in allowed:
        return token
    alias = _ALIAS_TO_ROLE_NAME.get(_compact(token))
    if alias and alias in allowed and alias not in forbidden:
        return alias
    return fallback


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
