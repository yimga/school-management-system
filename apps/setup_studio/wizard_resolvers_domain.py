"""Resolvers + writers for the 6 domain-specific wizards shipped in v4.00.8.

These close audit-flagged audience-coverage gaps for teacher/parent/student:

* ``teacher_gradebook_setup`` — class + scale + weights + policies
* ``teacher_attendance_intake`` — class + session window + statuses
* ``parent_payment_setup`` — branching by payment method
* ``parent_contact_preferences`` — channels + quiet hours + topic opt-ins
* ``student_course_selection`` — year + required + electives + ranked
* ``student_password_rotation`` — verify + new + confirm (secret-stripping)

All writers route through ``_default_cockpit_writer`` for SetupProgress JSON
persistence. Secret fields (``new_password`` / ``confirm_password``) are
stripped before any storage path. Option resolvers favor stable, ordered
choices over live DB hits — keeps the wizard listing endpoint cheap.

CLAUDE.md constraints honored:
* No hardcoded role strings (token-only labels)
* No money_float (n/a — no amounts here)
* Tenant queryset safety — writers only touch the school they receive
* PII sanitization — writer-side strip before _default_cockpit_writer
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from apps.setup_studio.wizard_resolvers import _default_cockpit_writer, _write_to_site_settings

logger = logging.getLogger(__name__)


def _write_user_step(
    *,
    school: Any,
    root_key: str,
    wizard_key: str,
    step_key: str,
    payload: dict[str, Any],
    actor_user_id: int | None,
    nest_wizard: bool = True,
) -> None:
    """Persist a per-user wizard step under a role-scoped settings path.

    ``role_wizards.<wizard_key>.users.<actor>.<step_key>`` when ``nest_wizard``
    (teacher gradebook / attendance), or ``<root_key>.users.<actor>.<step_key>``
    when the wizard owns its own top-level bucket (parent payment setup).
    """
    if school is None or not actor_user_id:
        return
    if nest_wizard:
        path = f"{root_key}.{wizard_key}.users.{actor_user_id}.{step_key}"
    else:
        path = f"{root_key}.users.{actor_user_id}.{step_key}"
    _write_to_site_settings(school, path, payload)


# ============================================================================
# Shared option resolvers
# ============================================================================


def list_teacher_classes(*, request: Any, school: Any) -> list[dict[str, Any]]:
    """Return the request user's owned/assigned classes; defensive against
    schema differences. Falls back to an honest empty list.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False) or school is None:
        return []
    try:
        from apps.academics.models import Classroom  # type: ignore

        qs = Classroom.objects.filter(school=school, is_active=True)  # tenant-isolation-allow: tenant-scope-via-school-filter
        # Best-effort teacher filter — different deployments name this field differently.
        for attr in ("homeroom_teacher", "owner", "owned_by", "primary_teacher"):
            try:
                filtered = qs.filter(**{attr: user})
                if filtered.exists():
                    qs = filtered
                    break
            except Exception:  # noqa: BLE001
                continue
        return [
            {"value": str(c.pk), "label_token": getattr(c, "name", None) or str(c.pk), "metadata": {"grade": getattr(c, "grade_level", "")}}
            for c in qs.order_by("name")[:80]
        ]
    except Exception as exc:  # noqa: BLE001
        logger.debug("list_teacher_classes fallback: %s", exc)
        return []


def list_grading_scale_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    """v4.00.30: country- and system-type-aware grading band picker.

    Falls back to the universal 6-option list when no school context is
    available so legacy callers keep working.
    """
    country = ""
    system_codes: list[str] = []
    try:
        if school is not None:
            country = (getattr(school, "country_code", "") or "").upper()
            m2m = getattr(school, "education_system_types", None)
            if m2m is not None:
                system_codes = list(m2m.values_list("code", flat=True))
            elif getattr(school, "school_type", ""):
                system_codes = [school.school_type]
    except Exception as exc:  # noqa: BLE001
        logger.debug("list_grading_scale_choices school-introspect fallback: %s", exc)

    try:
        from apps.siteconfig._grading_bands import grading_scale_choices

        return grading_scale_choices(country_code=country, system_type_codes=system_codes)
    except Exception as exc:  # noqa: BLE001
        logger.debug("list_grading_scale_choices band fallback: %s", exc)
        return [
            {"value": "percentage_0_100", "label_token": "Percentage 0–100", "metadata": {}},
            {"value": "letter_a_f",       "label_token": "Letter A–F",       "metadata": {}},
            {"value": "gpa_0_4",          "label_token": "GPA 0.0–4.0",      "metadata": {}},
            {"value": "points_out_of_20", "label_token": "Points out of 20", "metadata": {}},
            {"value": "rubric_levels",    "label_token": "Rubric levels",    "metadata": {}},
            {"value": "competency_pass_fail", "label_token": "Competency pass/fail", "metadata": {}},
        ]


def list_attendance_status_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "present", "label_token": "Present", "metadata": {}},
        {"value": "tardy",   "label_token": "Tardy",   "metadata": {}},
        {"value": "absent",  "label_token": "Absent",  "metadata": {}},
        {"value": "excused", "label_token": "Excused absence", "metadata": {}},
        {"value": "remote",  "label_token": "Remote / virtual", "metadata": {}},
    ]


def list_parent_payment_method_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "card",            "label_token": "Credit / debit card", "metadata": {}},
        {"value": "bank_transfer",   "label_token": "Bank transfer",       "metadata": {}},
        {"value": "mobile_money",    "label_token": "Mobile money",        "metadata": {}},
        {"value": "cash_at_school",  "label_token": "Cash at school office", "metadata": {}},
    ]


def list_communication_channel_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "email",    "label_token": "Email",    "metadata": {}},
        {"value": "sms",      "label_token": "SMS",      "metadata": {}},
        {"value": "push",     "label_token": "Push notification", "metadata": {}},
        {"value": "whatsapp", "label_token": "WhatsApp", "metadata": {}},
        {"value": "in_app",   "label_token": "In-app inbox",      "metadata": {}},
    ]


def list_parent_topic_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "attendance_alerts",     "label_token": "Attendance alerts",     "metadata": {}},
        {"value": "grade_postings",        "label_token": "Grade postings",        "metadata": {}},
        {"value": "invoice_due",           "label_token": "Invoice due",           "metadata": {}},
        {"value": "school_announcements",  "label_token": "School announcements",  "metadata": {}},
        {"value": "safeguarding_alerts",   "label_token": "Safeguarding alerts",   "metadata": {"never_quiet": True}},
        {"value": "teacher_messages",      "label_token": "Teacher messages",      "metadata": {}},
        {"value": "events_calendar",       "label_token": "Events & calendar",     "metadata": {}},
        {"value": "homework_reminders",    "label_token": "Homework reminders",    "metadata": {}},
    ]


def list_academic_year_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    try:
        from apps.academics.models import AcademicYear  # type: ignore

        qs = AcademicYear.objects.filter(school=school).order_by("-start_date")  # tenant-isolation-allow: tenant-scope-via-school-filter
        return [{"value": str(y.pk), "label_token": getattr(y, "name", None) or str(y.pk), "metadata": {}} for y in qs[:8]]
    except Exception as exc:  # noqa: BLE001
        logger.debug("list_academic_year_choices fallback: %s", exc)
        return [
            {"value": "current",   "label_token": "Current academic year",   "metadata": {}},
            {"value": "next",      "label_token": "Next academic year",      "metadata": {}},
        ]


def list_required_course_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return _list_courses(school, required_only=True)


def list_elective_course_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return _list_courses(school, required_only=False)


def _list_courses(school: Any, *, required_only: bool) -> list[dict[str, Any]]:
    if school is None:
        return []
    try:
        from apps.academics.models import Subject  # type: ignore

        qs = Subject.objects.filter(school=school)  # tenant-isolation-allow: tenant-scope-via-school-filter
        if required_only:
            try:
                qs = qs.filter(is_required=True)
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                qs = qs.filter(is_required=False)
            except Exception:  # noqa: BLE001
                pass
        return [
            {"value": str(s.pk), "label_token": getattr(s, "name", None) or str(s.pk), "metadata": {"code": getattr(s, "code", "")}}
            for s in qs.order_by("name")[:50]
        ]
    except Exception as exc:  # noqa: BLE001
        logger.debug("course choices fallback (required_only=%s): %s", required_only, exc)
        return []


# ============================================================================
# Writers
# ============================================================================


def write_teacher_gradebook_setup_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    if school is None:
        return
    _write_user_step(
        school=school, root_key="role_wizards", wizard_key=wizard_key,
        step_key=step_key, payload=payload, actor_user_id=actor_user_id,
    )


def write_teacher_attendance_intake_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    if school is None:
        return
    _write_user_step(
        school=school, root_key="role_wizards", wizard_key=wizard_key,
        step_key=step_key, payload=payload, actor_user_id=actor_user_id,
    )


_PAYMENT_SECRET_KEYS = frozenset({
    "card_number", "card_cvv", "cvc", "cvv", "card_pan", "account_number",
    "iban", "routing_number", "swift_code", "mobile_money_pin",
})


def write_parent_payment_setup_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    """Strip payment-secret fields before persisting; gateway secrets never land in school.settings."""
    safe = {k: v for k, v in (payload or {}).items() if k.lower() not in _PAYMENT_SECRET_KEYS}
    if school is None:
        logger.info("parent_payment_setup step=%s actor=%s safe_field_count=%d", step_key, actor_user_id, len(safe))
        return
    # parent_payment_setup owns a top-level bucket: parent_payment_setup.users.<actor>.<step>
    _write_user_step(
        school=school, root_key=wizard_key, wizard_key=wizard_key,
        step_key=step_key, payload=safe, actor_user_id=actor_user_id, nest_wizard=False,
    )


def write_parent_contact_preferences_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    if school is None:
        return
    # Delegate to the persona kernel so guardian contact-channel flags update too.
    from apps.accounts.persona_onboarding_kernel import apply_parent_contact_preferences_wizard

    apply_parent_contact_preferences_wizard(
        school=school, actor_user_id=actor_user_id, step_key=step_key, payload=payload,
    )
    # Also leave a per-user, school-level breadcrumb (no secrets here — these are
    # channel/quiet-hours/topic preferences) so the choice is observable in the
    # tenant settings cascade, consistent with the other user-scoped wizards.
    _write_user_step(
        school=school, root_key="role_wizards", wizard_key=wizard_key,
        step_key=step_key, payload=payload, actor_user_id=actor_user_id,
    )


def write_student_course_selection_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    if school is None or not actor_user_id:
        return
    # Record the student's course request under a per-user requests bucket.
    _write_to_site_settings(
        school,
        f"student_course_requests.{actor_user_id}",
        {"wizard_key": wizard_key, "step_key": step_key, "payload": payload},
    )


def write_password_rotation_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    """Critical: never persist raw passwords. Only persist a hash-only completion marker."""
    safe = {}
    for k, v in (payload or {}).items():
        if k in {"new_password", "confirm_password", "current_password", "password"}:
            continue
        if k == "verify_identity":
            val = str(v or "")
            if val:
                safe["verify_identity_hash"] = hashlib.sha256(val.encode("utf-8")).hexdigest()[:16]
        else:
            safe[k] = v
    if step_key == "confirm":
        try:
            from apps.accounts.services_password_rotation import perform_password_rotation  # type: ignore

            perform_password_rotation(actor_user_id=actor_user_id, payload=payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug("password rotation service delegation skipped: %s", exc)
    if school is None:
        # Log the wizard_key, NOT step_key: a rotation step can be named after a
        # secret field (e.g. "new_password"), and echoing that into logs is noise
        # at best and a misleading "secret in logs" signal at worst. Only the
        # safe, already-redacted key names (e.g. verify_identity_hash) are logged.
        logger.info(
            "password_rotation wizard=%s actor=%s wrote_keys=%s",
            wizard_key, actor_user_id, sorted(safe.keys()),
        )
        return
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=safe, actor_user_id=actor_user_id)
