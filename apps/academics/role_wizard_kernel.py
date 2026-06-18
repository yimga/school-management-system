"""Teacher/student role wizards → tenant-scoped preferences (school.settings)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _role_bucket(school: Any | None, wizard_key: str) -> dict[str, Any]:
    if school is None:
        return {}
    settings = getattr(school, "settings", None) or {}
    root = dict(settings.get("role_wizards") or {})
    return dict(root.get(wizard_key) or {})


def _save_role_user_slice(
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
    root = dict(settings.get("role_wizards") or {})
    wiz = dict(root.get(wizard_key) or {})
    users = dict(wiz.get("users") or {})
    user_row = dict(users.get(str(actor_user_id)) or {})
    user_row[step_key] = {**data, "updated_at": _utc_now()}
    users[str(actor_user_id)] = user_row
    wiz["users"] = users
    root[wizard_key] = wiz
    settings["role_wizards"] = root
    school.settings = settings
    school.save(update_fields=["settings"])


def apply_teacher_gradebook_step(
    *,
    school: Any | None,
    actor_user_id: int | None,
    step_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    _save_role_user_slice(
        school=school,
        wizard_key="teacher_gradebook_setup",
        actor_user_id=actor_user_id,
        step_key=step_key,
        data=dict(payload or {}),
    )
    if step_key == "policies" and school is not None and actor_user_id:
        classroom_id = (
            _role_bucket(school, "teacher_gradebook_setup")
            .get("users", {})
            .get(str(actor_user_id), {})
            .get("select_class", {})
            .get("value")
        )
        if classroom_id:
            settings = dict(getattr(school, "settings", None) or {})
            gb = dict(settings.get("teacher_gradebook") or {})
            gb[str(classroom_id)] = {
                "policies": payload,
                "teacher_user_id": actor_user_id,
                "updated_at": _utc_now(),
            }
            settings["teacher_gradebook"] = gb
            school.settings = settings
            school.save(update_fields=["settings"])
    return {"ok": True, "step_key": step_key}


def apply_teacher_attendance_step(
    *,
    school: Any | None,
    actor_user_id: int | None,
    step_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    _save_role_user_slice(
        school=school,
        wizard_key="teacher_attendance_intake",
        actor_user_id=actor_user_id,
        step_key=step_key,
        data=dict(payload or {}),
    )
    return {"ok": True, "step_key": step_key}


def apply_student_course_selection_step(
    *,
    school: Any | None,
    actor_user_id: int | None,
    step_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    _save_role_user_slice(
        school=school,
        wizard_key="student_course_selection",
        actor_user_id=actor_user_id,
        step_key=step_key,
        data=dict(payload or {}),
    )
    if step_key == "confirm" and school is not None and actor_user_id:
        users = (
            _role_bucket(school, "student_course_selection").get("users") or {}
        ).get(str(actor_user_id), {})
        selections = {
            k: users.get(k)
            for k in (
                "academic_year",
                "required_courses",
                "electives",
                "preferences_ranked",
            )
            if k in users
        }
        settings = dict(getattr(school, "settings", None) or {})
        pending = dict(settings.get("student_course_requests") or {})
        pending[str(actor_user_id)] = {
            **selections,
            "confirmed_at": _utc_now(),
        }
        settings["student_course_requests"] = pending
        school.settings = settings
        school.save(update_fields=["settings"])
    return {"ok": True, "step_key": step_key}
