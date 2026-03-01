"""
Provisioning task: after School row is created, create admin user, school_members, seed terms/subjects, logo path.
Can be run as Celery task or synchronously.
When USE_DJANGO_TENANTS is True, ensures Client and Domain exist and runs tenant-scoped creation in tenant_context.
"""
import logging
import secrets
from contextlib import contextmanager
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.schools.domain_sync import ensure_tenant_client_for_school, sync_school_domains_to_runtime

logger = logging.getLogger(__name__)

User = get_user_model()


def _use_django_tenants():
    return bool(getattr(settings, "USE_DJANGO_TENANTS", False))


def _ensure_tenant_client(school):
    """
    When USE_DJANGO_TENANTS: get or create Client and Domain for this school (public schema).
    Returns the Client or None if not using django-tenants.
    """
    if not _use_django_tenants():
        return None
    client = ensure_tenant_client_for_school(school)
    if client:
        try:
            sync_school_domains_to_runtime(school)
        except Exception:
            logger.exception("Failed syncing domains for school %s", school.id)
    return client


@contextmanager
def _optional_tenant_context(client):
    """If client is set, run inside django_tenants.utils.tenant_context(client); else no-op."""
    if client is None:
        yield
        return
    try:
        from django_tenants.utils import tenant_context
        with tenant_context(client):
            yield
    except ImportError:
        yield


def _record_school_event(
    school,
    *,
    event_type: str,
    status: str = "INFO",
    message: str = "",
    payload: dict | None = None,
):
    if school is None:
        return
    try:
        from .models import SchoolProvisioningEvent

        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=event_type,
            status=status,
            message=message,
            payload=payload or {},
        )
    except Exception:
        logger.exception("Failed to record provisioning event %s for school %s", event_type, getattr(school, "id", None))


def _record_school_event_by_id(
    school_id: str,
    *,
    event_type: str,
    status: str = "ERROR",
    message: str = "",
    payload: dict | None = None,
):
    try:
        from .models import School, SchoolProvisioningEvent

        school = School.objects.filter(id=school_id).first()
        if not school:
            return
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=event_type,
            status=status,
            message=message,
            payload=payload or {},
        )
    except Exception:
        logger.exception("Failed to record provisioning event %s for school %s", event_type, school_id)


def provision_school_sync(school_id: str, contact_email: str = "", **kwargs):
    """Run provisioning synchronously (no Celery)."""
    try:
        with transaction.atomic():
            _do_provision(school_id, contact_email=contact_email, **kwargs)
    except Exception as exc:
        _record_school_event_by_id(
            school_id,
            event_type="FAILED",
            status="ERROR",
            message="Provisioning failed",
            payload={"error": str(exc)},
        )
        raise


def _do_provision(school_id: str, contact_email: str = "", **kwargs):
    from .models import School, SchoolMembership
    from apps.academics.models import AcademicYear, Term, Subject
    from apps.siteconfig.education_profile_engine import resolve_profile_for_school
    from django.utils import timezone
    from datetime import date, timedelta

    school = School.objects.filter(id=school_id).first()
    if not school:
        logger.warning("School %s not found for provisioning", school_id)
        return
    if school.is_active:
        try:
            sync_school_domains_to_runtime(school)
        except Exception:
            logger.exception("Failed syncing domains for already active school %s", school_id)
        logger.info("School %s already active, skip provisioning", school_id)
        return
    _record_school_event(
        school,
        event_type="STARTED",
        status="INFO",
        message="Provisioning job started.",
    )

    # Create default admin user if contact_email provided and no user exists
    admin_user = None
    if contact_email:
        admin_user = User.objects.filter(email=contact_email).first()
        if not admin_user:
            username = contact_email.split("@")[0][:150] or f"admin_{school.slug}"
            if User.objects.filter(username=username).exists():
                username = f"{username}_{school.slug}"[:150]
            admin_user = User.objects.create_user(
                username=username,
                email=contact_email,
                # Keep a strong random value even though we disable password login.
                password=secrets.token_urlsafe(32),
                role=User.Role.ADMIN,
            )
            admin_user.set_unusable_password()
            admin_user.save()
            logger.info("Created admin user %s for school %s", admin_user.username, school_id)
        SchoolMembership.objects.get_or_create(
            user=admin_user,
            school=school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )

    # Seed academic year and terms from education profile + region defaults.
    # W1-9: When no education_profile_code is set, resolve_profile_for_school uses school.default_region_id
    # (from country_code at create) and returns one approved profile per country via for_school() + ensure_country_profile().
    region = school.default_region
    requested_profile_code = str((school.settings or {}).get("education_profile_code") or "").strip()
    profile = resolve_profile_for_school(
        school,
        requested_profile_code=requested_profile_code,
        auto_create=True,
    )
    term_count = 3
    term_labels = []
    if region:
        term_count = getattr(region, "term_count_per_year", 3) or 3
    start_month = 9
    if region:
        start_month = getattr(region, "academic_year_start_month", 9) or 9
    if profile:
        term_count = int(getattr(profile, "term_count_per_year", term_count) or term_count)
        start_month = int(getattr(profile, "academic_year_start_month", start_month) or start_month)
        term_labels = profile.normalized_term_labels()
        profile_config = {
            "education_profile_code": profile.code,
            "grading_scale": profile.grading_scale,
            "default_language": profile.default_language,
            "default_currency": profile.default_currency,
            "term_labels": term_labels,
        }
        if isinstance(getattr(profile, "config", None), dict) and profile.config.get("report_template_family"):
            profile_config["report_template_family"] = profile.config.get("report_template_family")
        merged_settings = dict(school.settings or {})
        # Respect explicit tenant-entered values while applying profile defaults.
        for key, value in profile_config.items():
            if not value:
                continue
            existing = merged_settings.get(key)
            if existing in (None, "", [], {}):
                merged_settings[key] = value
        if getattr(profile, "config", None):
            profile_settings = dict(merged_settings.get("education_profile", {}))
            profile_settings.update(profile.config or {})
            merged_settings["education_profile"] = profile_settings
        school.settings = merged_settings
        _record_school_event(
            school,
            event_type="PROFILE_APPLIED",
            status="SUCCESS",
            message=f"Applied education profile {profile.code}.",
            payload={
                "profile_code": profile.code,
                "profile_version": getattr(profile, "version", ""),
                "sub_system": school.sub_system,
            },
        )
        # Phase Global: deep hydration (modality, terminology from profile)
        try:
            from apps.siteconfig.system_morph import hydrate_school_from_profile
            applied = hydrate_school_from_profile(school)
            if applied:
                _record_school_event(
                    school,
                    event_type="PROFILE_APPLIED",
                    status="INFO",
                    message="Deep hydration applied (modality/terminology).",
                    payload=applied,
                )
        except Exception:
            logger.debug("SystemMorphService hydrate skipped", exc_info=True)
    else:
        _record_school_event(
            school,
            event_type="PROFILE_APPLIED",
            status="WARNING",
            message="No approved education profile resolved; using fallback defaults.",
            payload={"sub_system": school.sub_system},
        )

    # Schema-per-tenant: ensure Client and Domain exist so tenant schema is available
    tenant_client = _ensure_tenant_client(school)
    if tenant_client is None:
        try:
            sync_school_domains_to_runtime(school)
        except Exception:
            logger.exception("Failed syncing domains for school %s", school.id)

    # Tenant-scoped creation: run inside tenant_context when using schema-per-tenant
    with _optional_tenant_context(tenant_client):
        # Phase B: Tenant Provisioning Engine — create TenantSystem rows from wizard selection (multi-system)
        provisioning = (school.settings or {}).get("provisioning") or {}
        education_system_ids = provisioning.get("education_system_ids") or []
        if not isinstance(education_system_ids, list):
            education_system_ids = []
        profile_codes = [str(c).strip() for c in education_system_ids if c]
        if not profile_codes and profile and getattr(profile, "code", None):
            profile_codes = [profile.code]
        if profile_codes:
            from apps.siteconfig.models import EducationSystemProfile, TenantSystem
            approved = EducationSystemProfile.objects.filter(
                code__in=profile_codes,
                is_active=True,
                approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
            )
            for prof in approved:
                TenantSystem.objects.get_or_create(school=school, system=prof, defaults={})
            try:
                from apps.siteconfig.tenant_config import sync_tenant_modules_to_school_features
                sync_tenant_modules_to_school_features(school)
            except Exception as e:
                logger.debug("Optional sync_tenant_modules_to_school_features: %s", e)

        # Compile and persist tenant config snapshot (region pack + locks + effective config).
        try:
            from apps.siteconfig.tenant_config import persist_compiled_tenant_config

            compiled = persist_compiled_tenant_config(school, persist=True)
            _record_school_event(
                school,
                event_type="PROFILE_APPLIED",
                status="INFO",
                message="Tenant config compiled from region/profile/overrides.",
                payload={
                    "policy_pack": compiled.get("pack") or {},
                    "layers": compiled.get("layers") or [],
                },
            )
        except Exception:
            logger.exception("Failed to compile tenant config snapshot for school %s", school_id)

        now = timezone.now().date()
        year_start = date(now.year, start_month, 1)
        if now.month < start_month:
            year_start = date(now.year - 1, start_month, 1)
        year_end = date(year_start.year + 1, start_month, 1)
        year_end = year_end - timedelta(days=1)

        ay, created = AcademicYear.objects.get_or_create(
            school=school,
            name=f"{year_start.year}/{year_end.year}",
            defaults={
                "start_date": year_start,
                "end_date": year_end,
                "is_active": True,
            },
        )
        if created:
            # Create terms
            def _month_start_add(base_date: date, months: int) -> date:
                year = base_date.year + ((base_date.month - 1 + months) // 12)
                month = ((base_date.month - 1 + months) % 12) + 1
                return date(year, month, 1)

            months_per_term = 12 // term_count
            for i in range(term_count):
                t_start = _month_start_add(year_start, i * months_per_term)
                if i == term_count - 1:
                    t_end = year_end
                else:
                    next_term_start = _month_start_add(year_start, (i + 1) * months_per_term)
                    t_end = next_term_start - timedelta(days=1)
                term_name = (
                    term_labels[i]
                    if i < len(term_labels) and str(term_labels[i]).strip()
                    else f"Term {i + 1}"
                )
                Term.objects.get_or_create(
                    school=school,
                    academic_year=ay,
                    name=term_name,
                    defaults={
                        "position": i + 1,
                        "start_date": t_start,
                        "end_date": t_end,
                        "is_active": i == 0,
                    },
                )
        logger.info("Seeded academic year and %s terms for school %s", term_count, school_id)
        _record_school_event(
            school,
            event_type="ACADEMIC_YEAR_READY",
            status="SUCCESS",
            message="Academic year and terms prepared.",
            payload={
                "academic_year": ay.name,
                "created": bool(created),
                "term_count": int(term_count),
            },
        )

        # Optional: seed default subjects. Subject name is unique per school (school_id, name).
        subject_created = 0
        if not Subject.objects.filter(school=school).exists():
            subject_seed = []
            if profile:
                subject_seed = profile.normalized_subject_seed()
            if not subject_seed:
                subject_seed = [
                    {"name": "Mathematics", "category": Subject.Category.GENERAL},
                    {"name": "English", "category": Subject.Category.GENERAL},
                    {"name": "French", "category": Subject.Category.GENERAL},
                    {"name": "Science", "category": Subject.Category.GENERAL},
                ]
            valid_categories = {choice[0] for choice in Subject.Category.choices}
            for item in subject_seed:
                name = str(item.get("name") if isinstance(item, dict) else "").strip()
                if not name:
                    continue
                raw_category = str(item.get("category", Subject.Category.GENERAL) if isinstance(item, dict) else Subject.Category.GENERAL).upper()
                category = raw_category if raw_category in valid_categories else Subject.Category.GENERAL
                _, created_subject = Subject.objects.get_or_create(
                    school=school,
                    name=name,
                    defaults={"category": category},
                )
                if created_subject:
                    subject_created += 1
            logger.info("Seeded default subjects for school %s", school_id)
        _record_school_event(
            school,
            event_type="SUBJECTS_READY",
            status="SUCCESS",
            message="Default subjects prepared.",
            payload={"subjects_created": int(subject_created)},
        )

        # W1-5: Seed 1–3 default classrooms from profile (or generic names).
        from apps.academics.models import Classroom, Department

        classroom_seed_names = []
        seed_fn = getattr(profile, "normalized_classroom_seed", None) if profile else None
        if callable(seed_fn):
            try:
                classroom_seed_names = list(seed_fn())[:3]
            except Exception:
                pass
        if not classroom_seed_names:
            classroom_seed_names = ["Class 1", "Class 2", "Class 3"]
        dept_code = f"{school.slug}-GEN" if school.slug else f"{school.id.hex[:8]}-GEN"
        department, _ = Department.objects.get_or_create(
            code=dept_code,
            defaults={"school": school, "name": "General"},
        )
        if department.school_id != school.id:
            department.school = school
            department.save(update_fields=["school"])
        classroom_created = 0
        for i, label in enumerate(classroom_seed_names[:3]):
            name = str(label).strip() or f"Class {i + 1}"
            code = f"{dept_code}-C{i + 1}"
            if Classroom.objects.filter(code=code).exists():
                continue
            Classroom.objects.get_or_create(
                code=code,
                defaults={
                    "school": school,
                    "academic_year": ay,
                    "department": department,
                    "name": name,
                },
            )
            classroom_created += 1
        if classroom_created:
            logger.info("Seeded %s default classrooms for school %s", classroom_created, school_id)
            _record_school_event(
                school,
                event_type="CLASSROOMS_READY",
                status="SUCCESS",
                message="Default classrooms prepared.",
                payload={"classrooms_created": classroom_created},
            )

        school.is_active = True
        school.save(update_fields=["is_active", "settings", "updated_at"])
        _record_school_event(
            school,
            event_type="COMPLETED",
            status="SUCCESS",
            message="Provisioning completed successfully.",
        )
    logger.info("School %s provisioning complete", school_id)

    # Phase Welcome: send welcome email (async if Celery available)
    if (contact_email or "").strip():
        try:
            from apps.schools.welcome_email import send_welcome_email_task
            send_welcome_email_task.delay(str(school.id), contact_email=contact_email)
        except Exception:
            from apps.schools.welcome_email import send_welcome_email
            send_welcome_email(str(school.id), contact_email)


# Celery task (optional)
try:
    from celery import shared_task

    @shared_task(bind=True, max_retries=3)
    def provision_school_task(self, school_id: str, contact_email: str = "", **kwargs):
        try:
            with transaction.atomic():
                _do_provision(school_id, contact_email=contact_email, **kwargs)
        except Exception as exc:
            logger.exception("Provisioning failed for %s", school_id)
            _record_school_event_by_id(
                school_id,
                event_type="FAILED",
                status="ERROR",
                message="Provisioning failed",
                payload={"error": str(exc)},
            )
            raise self.retry(exc=exc)
except ImportError:
    def provision_school_task(*args, **kwargs):
        provision_school_sync(*args, **kwargs)
