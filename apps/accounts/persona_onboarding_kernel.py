"""Parent/staff persona onboarding wizards → User, Guardian, Teacher, HR rows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persona_bucket(school: Any | None, wizard_key: str) -> dict[str, Any]:
    if school is None:
        return {}
    settings = getattr(school, "settings", None) or {}
    return dict((settings.get("persona_onboarding") or {}).get(wizard_key) or {})


def _save_persona_user_slice(
    *,
    school: Any | None,
    wizard_key: str,
    actor_user_id: int | None,
    step_key: str,
    data: dict[str, Any],
) -> None:
    if school is None or not actor_user_id:
        return
    settings = dict(getattr(school, "settings", None) or {})
    root = dict(settings.get("persona_onboarding") or {})
    wiz = dict(root.get(wizard_key) or {})
    users = dict(wiz.get("users") or {})
    user_row = dict(users.get(str(actor_user_id)) or {})
    user_row[step_key] = {**data, "updated_at": _utc_now()}
    users[str(actor_user_id)] = user_row
    wiz["users"] = users
    root[wizard_key] = wiz
    settings["persona_onboarding"] = root
    school.settings = settings
    school.save(update_fields=["settings"])


def _split_name(full_name: str) -> tuple[str, str]:
    parts = (full_name or "").strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _map_preferred_contact(raw: str | None) -> str:
    from apps.people.models import StudentGuardian

    val = (raw or "").strip().upper()
    aliases = {
        "EMAIL": StudentGuardian.PreferredContact.EMAIL,
        "SMS": StudentGuardian.PreferredContact.SMS,
        "WHATSAPP": StudentGuardian.PreferredContact.WHATSAPP,
        "PHONE": StudentGuardian.PreferredContact.PHONE,
        "APP_PUSH": StudentGuardian.PreferredContact.EMAIL,
        "PARENT_PORTAL_INBOX": StudentGuardian.PreferredContact.EMAIL,
    }
    return aliases.get(val, StudentGuardian.PreferredContact.EMAIL)


def apply_parent_profile(*, school: Any | None, actor_user_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
    if not actor_user_id:
        return {"ok": False, "error": "missing_actor"}

    from apps.accounts.models import User
    from apps.people.models import StudentGuardian

    try:
        user = User.objects.get(pk=actor_user_id)
    except User.DoesNotExist:
        return {"ok": False, "error": "user_not_found"}

    full_name = payload.get("full_name") or payload.get("value") or ""
    first, last = _split_name(str(full_name))
    update_fields: list[str] = []
    if first:
        user.first_name = first
        update_fields.append("first_name")
    if last:
        user.last_name = last
        update_fields.append("last_name")
    lang = payload.get("preferred_language")
    if lang:
        user.preferred_language = str(lang)[:16]
        update_fields.append("preferred_language")
    if update_fields:
        user.save(update_fields=update_fields)

    channel = _map_preferred_contact(payload.get("preferred_communication_channel"))
    links = StudentGuardian.objects.filter(guardian_user=user)
    if school is not None:
        links = links.filter(student__school=school)
    links.update(preferred_contact=channel)

    _save_persona_user_slice(
        school=school,
        wizard_key="parent_onboarding",
        actor_user_id=actor_user_id,
        step_key="profile_basics",
        data={
            "full_name": full_name,
            "preferred_language": lang,
            "preferred_communication_channel": payload.get("preferred_communication_channel"),
        },
    )
    return {"ok": True, "user_id": user.pk}


def apply_parent_linked_children(*, school: Any | None, actor_user_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None or not actor_user_id:
        return {"ok": False, "error": "missing_inputs"}

    from apps.accounts.services_link_child import link_guardian_to_student
    from apps.people.models import StudentGuardian, StudentProfile

    raw = payload.get("value") or payload.get("children") or []
    if not isinstance(raw, list):
        raw = [raw] if raw else []

    linked: list[int] = []
    for item in raw:
        if isinstance(item, dict):
            adm = item.get("admission_number") or item.get("value")
            rel = item.get("relationship")
            pref = item.get("preferred_contact")
            if adm:
                result = link_guardian_to_student(
                    school=school,
                    actor_user_id=actor_user_id,
                    admission_number=str(adm),
                    relationship=rel,
                    preferred_contact=pref,
                )
                if result.get("ok"):
                    sid = result.get("student_id")
                    if sid:
                        linked.append(int(sid))
            continue

        token = str(item).strip()
        if not token:
            continue
        if token.isdigit():
            student = StudentProfile.objects.filter(school=school, pk=int(token)).first()
            if student is None:
                continue
            StudentGuardian.objects.get_or_create(
                guardian_user_id=actor_user_id,
                student=student,
                defaults={"relationship": StudentGuardian.Relationship.GUARDIAN},
            )
            linked.append(student.pk)
            continue

        result = link_guardian_to_student(
            school=school,
            actor_user_id=actor_user_id,
            admission_number=token,
            relationship=payload.get("relationship"),
            preferred_contact=payload.get("preferred_contact"),
        )
        if result.get("ok") and result.get("student_id"):
            linked.append(int(result["student_id"]))

    _save_persona_user_slice(
        school=school,
        wizard_key="parent_onboarding",
        actor_user_id=actor_user_id,
        step_key="linked_children",
        data={"linked_student_ids": linked},
    )
    return {"ok": True, "linked_student_ids": linked}


def apply_parent_communication_preferences(
    *, school: Any | None, actor_user_id: int | None, payload: dict[str, Any]
) -> dict[str, Any]:
    _save_persona_user_slice(
        school=school,
        wizard_key="parent_onboarding",
        actor_user_id=actor_user_id,
        step_key="communication_preferences",
        data={
            "quiet_hours_start": payload.get("quiet_hours_start"),
            "quiet_hours_end": payload.get("quiet_hours_end"),
            "max_messages_per_day": payload.get("max_messages_per_day"),
        },
    )
    return {"ok": True}


def apply_parent_payment_preview(*, school: Any | None, actor_user_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
    preview = payload.get("value")
    if preview is None:
        preview = payload.get("enabled", True)
    _save_persona_user_slice(
        school=school,
        wizard_key="parent_onboarding",
        actor_user_id=actor_user_id,
        step_key="payment_method_preview",
        data={"preview_enabled": bool(preview)},
    )
    return {"ok": True, "preview_enabled": bool(preview)}


def apply_staff_profile(*, school: Any | None, actor_user_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
    if not actor_user_id:
        return {"ok": False, "error": "missing_actor"}

    from apps.accounts.models import User
    from apps.people.models import TeacherProfile
    from apps.payroll.models import PayrollEmployee

    try:
        user = User.objects.get(pk=actor_user_id)
    except User.DoesNotExist:
        return {"ok": False, "error": "user_not_found"}

    full_name = payload.get("full_name") or ""
    first, last = _split_name(str(full_name))
    update_fields: list[str] = []
    if first:
        user.first_name = first
        update_fields.append("first_name")
    if last:
        user.last_name = last
        update_fields.append("last_name")
    if update_fields:
        user.save(update_fields=update_fields)

    employee_id = (payload.get("employee_id") or "").strip()
    if school is not None and employee_id:
        profile, _ = TeacherProfile.objects.get_or_create(user=user, defaults={"school": school})
        if not profile.school_id:
            profile.school = school
            profile.save(update_fields=["school"])
        if employee_id and not profile.staff_id:
            profile.staff_id = employee_id[:50]
            profile.save(update_fields=["staff_id"])
        employee, _ = PayrollEmployee.objects.get_or_create(user=user)
        if not employee.employee_code:
            employee.employee_code = employee_id[:50]
            employee.save(update_fields=["employee_code"])

    _save_persona_user_slice(
        school=school,
        wizard_key="staff_onboarding",
        actor_user_id=actor_user_id,
        step_key="profile_basics",
        data={"full_name": full_name, "employee_id": employee_id},
    )
    return {"ok": True, "user_id": user.pk}


def apply_staff_role(*, school: Any | None, actor_user_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
    if not actor_user_id:
        return {"ok": False, "error": "missing_actor"}

    from apps.accounts.models import User

    role = payload.get("value") or payload.get("role")
    if not role:
        return {"ok": False, "error": "missing_role"}

    try:
        user = User.objects.get(pk=actor_user_id)
    except User.DoesNotExist:
        return {"ok": False, "error": "user_not_found"}

    valid = {c for c, _ in User.Role.choices}
    role_upper = str(role).strip().upper()
    if role_upper in valid:
        user.role = role_upper
        user.save(update_fields=["role"])

    _save_persona_user_slice(
        school=school,
        wizard_key="staff_onboarding",
        actor_user_id=actor_user_id,
        step_key="role_assignment",
        data={"role": role_upper},
    )
    return {"ok": True, "role": role_upper}


def apply_staff_background(*, school: Any | None, actor_user_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
    _save_persona_user_slice(
        school=school,
        wizard_key="staff_onboarding",
        actor_user_id=actor_user_id,
        step_key="background_check_status",
        data={
            "has_background_check": payload.get("has_background_check"),
            "background_check_file": bool(payload.get("background_check_file")),
        },
    )
    return {"ok": True}


def apply_staff_training(*, school: Any | None, actor_user_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
    modules = payload.get("value") or payload.get("modules") or []
    if not isinstance(modules, list):
        modules = [modules] if modules else []
    _save_persona_user_slice(
        school=school,
        wizard_key="staff_onboarding",
        actor_user_id=actor_user_id,
        step_key="training_module_assignment",
        data={"modules": modules},
    )
    return {"ok": True, "modules": modules}


def apply_parent_contact_preferences_wizard(
    *,
    school: Any | None,
    actor_user_id: int | None,
    step_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Dedicated parent_contact_preferences wizard (channels / quiet hours / topics)."""
    data = dict(payload or {})
    if step_key == "channels":
        raw = data.get("value") or data.get("channels") or []
        if not isinstance(raw, list):
            raw = [raw] if raw else []
        data = {"channels": [str(c) for c in raw]}
    elif step_key == "topic_opt_ins":
        raw = data.get("value") or data.get("topics") or []
        if not isinstance(raw, list):
            raw = [raw] if raw else []
        data = {"topic_opt_ins": [str(t) for t in raw]}

    _save_persona_user_slice(
        school=school,
        wizard_key="parent_contact_preferences",
        actor_user_id=actor_user_id,
        step_key=step_key,
        data=data,
    )

    if school is not None and actor_user_id and step_key == "channels":
        from apps.people.models import StudentGuardian

        channels = data.get("channels") or []
        StudentGuardian.objects.filter(
            guardian_user_id=actor_user_id,
            student__school=school,
        ).update(
            receives_email="email" in channels,
            receives_sms="sms" in channels,
            receives_whatsapp="whatsapp" in channels,
        )

    return {"ok": True, "step_key": step_key}
