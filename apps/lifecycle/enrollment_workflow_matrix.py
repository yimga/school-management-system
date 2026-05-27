"""
Tenant lifecycle workflow matrices — registration, enrollment, onboarding, offboarding.

Single source for School Studio command center + operator Tenant 360 panels.
"""

from __future__ import annotations

from typing import Any, Optional

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

REGISTRATION_TRACK: tuple[dict[str, Any], ...] = (
    {
        "key": "signup_profile",
        "label": _("Region & school type"),
        "description": _("Country, calendar, language, and sector on public signup."),
        "url_name": "",
        "external": "marketing_signup",
        "state": "signup_profile",
    },
    {
        "key": "signup_plan",
        "label": _("Plan & brand"),
        "description": _("Trial plan, palette, and subdomain reservation."),
        "url_name": "",
        "external": "marketing_signup",
        "state": "signup_plan",
    },
    {
        "key": "signup_migration",
        "label": _("Migration intent"),
        "description": _("Prior SIS vendor and data domains to import."),
        "url_name": "",
        "external": "marketing_signup",
        "state": "signup_migration",
    },
    {
        "key": "email_verify",
        "label": _("Email verification"),
        "description": _("Admin verifies inbox before tenant activates."),
        "url_name": "tenant_provisioning_status",
        "state": "signup_verified",
    },
    {
        "key": "provision",
        "label": _("Provision workspace"),
        "description": _("Schema, defaults, and provisioning events complete."),
        "url_name": "tenant_provisioning_status",
    },
)

ENROLLMENT_TRACK: tuple[dict[str, Any], ...] = (
    {
        "key": "admissions_pipeline",
        "label": _("Admissions pipeline"),
        "description": _("At least one applicant past the lead stage."),
        "url_name": "accounts:backend_applicant_list",
        "state": "admissions_active",
    },
    {
        "key": "applicant_convert",
        "label": _("Applicant → student"),
        "description": _("Accepted or enrolled applicant linked to a student profile."),
        "url_name": "accounts:backend_applicant_create",
        "state": "applicant_enrolled",
    },
    {
        "key": "student_roster",
        "label": _("Student roster"),
        "description": _("Active students with classrooms assigned."),
        "url_name": "accounts:backend_student_list",
    },
    {
        "key": "guardian_invites",
        "label": _("Guardian invites"),
        "description": _("Issue and claim parent portal invites."),
        "url_name": "accounts:backend_guardian_list",
        "state": "guardian_invite_claimed",
    },
    {
        "key": "guardian_access",
        "label": _("Guardian portal access"),
        "description": _("Guardians linked to students with active portal users."),
        "url_name": "accounts:backend_guardian_list",
        "state": "guardian_portal_active",
    },
    {
        "key": "class_structure",
        "label": _("Classes & sections"),
        "description": _("Classrooms and teaching assignments ready."),
        "url_name": "accounts:backend_classroom_list",
    },
    {
        "key": "fee_readiness",
        "label": _("Fee catalog"),
        "description": _("Invoices or fee structures configured for enrolled learners."),
        "url_name": "finance:invoices",
    },
)

TENANT_OFFBOARDING_TRACK: tuple[dict[str, Any], ...] = (
    {
        "key": "self_request",
        "label": _("Closure requested"),
        "description": _("School admin requested account closure."),
        "url_name": "tenant_offboarding",
        "settings_key": "self_service_status",
        "expect_values": ("closure_requested", "scheduled"),
    },
    {
        "key": "export_pack",
        "label": _("Portability export"),
        "description": _("Download full tenant export ZIP."),
        "url_name": "tenant_offboarding",
    },
    {
        "key": "wind_down",
        "label": _("Wind-down mode"),
        "description": _("Commerce and enrollments paused."),
        "settings_key": "wind_down_mode",
    },
    {
        "key": "purge_scheduled",
        "label": _("Purge scheduled"),
        "description": _("Operator or self-service scheduled purge date on file."),
        "state": "purge_scheduled",
    },
    {
        "key": "cancel_closure",
        "label": _("Cancel closure"),
        "description": _("Reactivate before purge date."),
        "url_name": "tenant_offboarding",
        "optional": True,
    },
)


def _tenant_reverse(name: str, kwargs: Optional[dict] = None) -> str:
    if not name:
        return ""
    try:
        return reverse(name, kwargs=kwargs or {}, urlconf="config.tenant_urls")
    except NoReverseMatch:
        try:
            return reverse(name, kwargs=kwargs or {})
        except NoReverseMatch:
            return ""


def _marketing_signup_url() -> str:
    try:
        return reverse("schools:signup_school")
    except NoReverseMatch:
        return "/signup/"


def _public_onboarding(school) -> dict:
    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        return {}
    block = raw.get("rmc_public_onboarding")
    return block if isinstance(block, dict) else {}


def _settings_flag(school, key: str) -> bool:
    raw = getattr(school, "settings", None) or {}
    if not isinstance(raw, dict):
        return False
    if key == "signup_verified":
        off = raw.get("rmc_public_onboarding") or {}
        if isinstance(off, dict) and off.get("email_verified"):
            return True
        return bool(raw.get("signup_email_verified"))
    if key == "wind_down_mode":
        off = raw.get("offboarding") or {}
        if isinstance(off, dict):
            return bool(off.get("wind_down_mode"))
    if key == "self_service_status":
        off = raw.get("offboarding") or {}
        if isinstance(off, dict):
            return bool((off.get("self_service_status") or "").strip())
    return bool(raw.get(key))


def _registration_done(school, step: dict[str, Any]) -> bool:
    key = step["key"]
    state = step.get("state")
    if state == "signup_profile":
        onboarding = _public_onboarding(school)
        return bool(
            (getattr(school, "country_code", None) or "").strip()
            or onboarding.get("country_code")
            or onboarding.get("school_type")
        )
    if state == "signup_plan":
        onboarding = _public_onboarding(school)
        return bool(
            onboarding.get("plan_slug")
            or onboarding.get("template_slug")
            or (getattr(school, "slug", None) and school.is_active)
        )
    if state == "signup_migration":
        onboarding = _public_onboarding(school)
        mig = onboarding.get("migration") if isinstance(onboarding.get("migration"), dict) else {}
        return bool(mig.get("vendor_slug")) or bool(onboarding.get("skip_migration"))
    if state == "signup_verified":
        try:
            from apps.schools.models import SignupVerification

            if SignupVerification.objects.filter(
                school=school, verified_at__isnull=False
            ).exists():
                return True
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            pass
        return bool(getattr(school, "is_active", False)) or _settings_flag(school, "signup_verified")
    if key == "provision":
        from apps.lifecycle.unified_lifecycle import (
            SchoolProvisioningEvent_completed,
            resolve_unified_lifecycle,
        )

        unified = resolve_unified_lifecycle(school)
        return unified.get("state") in ("live", "activating") or SchoolProvisioningEvent_completed(
            school
        )
    if step.get("settings_key"):
        return _settings_flag(school, step["settings_key"])
    if step.get("external") == "marketing_signup":
        from apps.lifecycle.unified_lifecycle import get_creation_path, CREATION_PATH_SELF_SERVE

        return get_creation_path(school) == CREATION_PATH_SELF_SERVE
    return False


def _enrollment_done(school, step: dict[str, Any]) -> bool:
    state = step.get("state") or step.get("key")
    try:
        if state == "admissions_active":
            from apps.people.models import Applicant

            return Applicant.objects.filter(school=school).exclude(
                stage=Applicant.Stage.LEAD
            ).exists()
        if state == "applicant_enrolled":
            from apps.people.models import Applicant, StudentProfile

            if Applicant.objects.filter(
                school=school, stage=Applicant.Stage.ENROLLED
            ).exists():
                return True
            return StudentProfile.objects.filter(school=school).exists()
        if state == "student_roster" or step.get("key") == "student_roster":
            from apps.people.models import StudentProfile

            return StudentProfile.objects.filter(school=school).exists()
        if state == "guardian_invite_claimed":
            from apps.people.models import StudentGuardian, StudentProfile
            from apps.portal.models import PendingGuardianInvite

            student_ids = StudentProfile.objects.filter(school=school).values_list(
                "id", flat=True
            )
            if PendingGuardianInvite.objects.filter(
                student_id__in=student_ids, claimed_at__isnull=False
            ).exists():
                return True
            return StudentGuardian.objects.filter(
                student__school=school, guardian_user__isnull=False
            ).exists()
        if state == "guardian_portal_active":
            from apps.people.models import StudentGuardian

            return StudentGuardian.objects.filter(
                student__school=school, guardian_user__isnull=False, guardian_user__is_active=True
            ).exists()
        if step.get("key") == "class_structure":
            from apps.academics.models import Classroom

            return Classroom.objects.filter(school=school).exists()
        if step.get("key") == "fee_readiness":
            from apps.finance.models import Invoice

            return Invoice.objects.filter(school=school).exists()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return False
    return False


def _offboarding_tenant_done(school, step: dict[str, Any]) -> bool:
    if step.get("state") == "purge_scheduled":
        off = (getattr(school, "settings", None) or {}).get("offboarding") or {}
        return bool((off.get("scheduled_purge_at") or "").strip()) if isinstance(off, dict) else False
    if step.get("settings_key") == "self_service_status":
        off = (getattr(school, "settings", None) or {}).get("offboarding") or {}
        if not isinstance(off, dict):
            return False
        status = (off.get("self_service_status") or "").strip()
        expect = step.get("expect_values") or ()
        return status in expect
    if step.get("settings_key") == "wind_down_mode":
        return _settings_flag(school, "wind_down_mode")
    if step["key"] == "export_pack":
        off = (getattr(school, "settings", None) or {}).get("offboarding") or {}
        if isinstance(off, dict) and (off.get("last_export_zip_path") or "").strip():
            return True
        from apps.schools.tenant_offboarding import get_offboarding_snapshot

        try:
            snap = get_offboarding_snapshot(school)
            return bool((snap.get("last_export_path") or "").strip())
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            return False
    return False


def _rows(
    school,
    track: tuple[dict[str, Any], ...],
    done_fn,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in track:
        url = ""
        if step.get("external") == "marketing_signup":
            url = _marketing_signup_url()
        elif step.get("url_name"):
            url = _tenant_reverse(step["url_name"])
        done = done_fn(school, step)
        rows.append(
            {
                "key": step["key"],
                "label": str(step["label"]),
                "description": str(step.get("description") or ""),
                "url": url,
                "done": done,
                "optional": bool(step.get("optional")),
            }
        )
    return rows


def build_registration_track(school) -> dict[str, Any]:
    rows = _rows(school, REGISTRATION_TRACK, _registration_done)
    done = sum(1 for r in rows if r["done"])
    total = len(rows)
    return {
        "steps": rows,
        "done": done,
        "total": total,
        "percent": int(100 * done / max(total, 1)),
        "next": next((r for r in rows if not r["done"]), None),
    }


def build_enrollment_track(school) -> dict[str, Any]:
    rows = _rows(school, ENROLLMENT_TRACK, _enrollment_done)
    done = sum(1 for r in rows if r["done"])
    total = len(rows)
    return {
        "steps": rows,
        "done": done,
        "total": total,
        "percent": int(100 * done / max(total, 1)),
        "next": next((r for r in rows if not r["done"]), None),
    }


def build_tenant_offboarding_track(school) -> dict[str, Any]:
    rows = _rows(school, TENANT_OFFBOARDING_TRACK, _offboarding_tenant_done)
    done = sum(1 for r in rows if r["done"] and not r.get("optional"))
    required = [r for r in rows if not r.get("optional")]
    total = len(required)
    return {
        "steps": rows,
        "done": done,
        "total": total,
        "percent": int(100 * done / max(total, 1)),
        "next": next((r for r in required if not r["done"]), None),
    }


def build_lifecycle_workflow_hub_payload(school, user=None) -> dict[str, Any]:
    """Aggregated registration + enrollment + onboarding + offboarding for command center."""
    from apps.lifecycle.launch_rail import build_launch_rail_payload
    from apps.lifecycle.unified_lifecycle import build_offboarding_checklist, resolve_unified_lifecycle

    unified = resolve_unified_lifecycle(school)
    rail = build_launch_rail_payload(school, user=user)
    registration = build_registration_track(school)
    enrollment = build_enrollment_track(school)
    tenant_offboarding = build_tenant_offboarding_track(school)
    operator_offboarding = build_offboarding_checklist(school)
    op_done = sum(1 for s in operator_offboarding if s.get("done"))

    return {
        "unified": unified,
        "launch_rail": rail,
        "registration": registration,
        "enrollment": enrollment,
        "tenant_offboarding": tenant_offboarding,
        "operator_offboarding": {
            "steps": operator_offboarding,
            "done": op_done,
            "total": len(operator_offboarding),
            "percent": int(100 * op_done / max(len(operator_offboarding), 1)),
        },
        "summary": {
            "registration_percent": registration["percent"],
            "enrollment_percent": enrollment["percent"],
            "onboarding_percent": rail.get("onboarding_percent", 0),
            "fast_path_percent": rail.get("fast_path_percent", 0),
            "offboarding_percent": tenant_offboarding["percent"],
        },
    }
