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
from django.db.utils import DatabaseError, IntegrityError

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.schools.domain_sync import (
    ensure_tenant_client_for_school,
    sync_school_domains_to_runtime,
)
from apps.schools.rls_context import rls_school

logger = logging.getLogger(__name__)

try:
    from kombu.exceptions import OperationalError as KombuOperationalError
except ImportError:  # pragma: no cover - kombu is installed in production/test envs

    class KombuOperationalError(Exception):
        """Fallback exception type when kombu is unavailable."""


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
        except (
            OSError,
            ConnectionError,
            DatabaseError,
            AttributeError,
            TypeError,
            ValueError,
        ):
            log_exception_with_context(
                "schools.tasks._ensure_tenant_client: failed syncing domains for school",
                school_id=getattr(school, "id", None),
            )
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
    except (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError):
        log_exception_with_context(
            "schools.tasks._record_school_event: failed to record provisioning event",
            school_id=getattr(school, "id", None),
            extra={"event_type": event_type},
        )


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
    except (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError):
        log_exception_with_context(
            "schools.tasks._record_school_event_by_id: failed to record provisioning event",
            school_id=school_id,
            extra={"event_type": event_type},
        )


def _provision_dns_record(school):
    """
    Pass 7: auto-create the tenant subdomain DNS record through the configured
    provider (Cloudflare / Route53) and verify reachability via dnspython.

    No-op when DNS_PROVIDER is unset (self-hosted deployments manage DNS out of
    band). Always logs a provisioning event so operators can see what happened
    even when the provider call fails — DNS issues are eventually-consistent
    and should not block the rest of the provisioning pipeline.
    """
    if school is None:
        return
    try:
        from django.conf import settings as _settings

        from apps.schools.dns_providers import get_dns_provider
        from apps.schools.dns_verification import hostname_resolves
        from apps.schools.domain_sync import school_subdomain_fqdn
    except (ImportError, AttributeError):
        return

    fqdn = school_subdomain_fqdn(school)
    if not fqdn:
        return

    target = (getattr(_settings, "DNS_CNAME_TARGET", "") or "").strip()
    provider = get_dns_provider()
    if provider.name == "null":
        # Self-hosted / manual DNS; nothing to do but record the skip for audit.
        _record_school_event(
            school,
            event_type="DNS_RECORD_SKIPPED",
            status="INFO",
            message="DNS automation disabled (DNS_PROVIDER unset).",
            payload={"fqdn": fqdn},
        )
        return
    if not target:
        _record_school_event(
            school,
            event_type="DNS_RECORD_FAILED",
            status="WARNING",
            message="DNS_CNAME_TARGET not configured.",
            payload={"fqdn": fqdn, "provider": provider.name},
        )
        return

    result = provider.create_record(subdomain=fqdn, target=target)
    if result.ok:
        _record_school_event(
            school,
            event_type="DNS_RECORD_CREATED",
            status="SUCCESS",
            message=f"{provider.name} record created for {fqdn}.",
            payload={
                "fqdn": fqdn,
                "target": target,
                "provider": provider.name,
                "record_id": result.record_id,
            },
        )
    else:
        _record_school_event(
            school,
            event_type="DNS_RECORD_FAILED",
            status="ERROR",
            message=f"{provider.name} record creation failed for {fqdn}.",
            payload={
                "fqdn": fqdn,
                "target": target,
                "provider": provider.name,
                "error": result.error,
            },
        )
        # Don't run reachability if create failed — the negative result is misleading.
        return

    reachable = hostname_resolves(fqdn, timeout=4.0)
    _record_school_event(
        school,
        event_type="DNS_REACHABLE" if reachable else "DNS_NOT_REACHABLE",
        status="SUCCESS" if reachable else "WARNING",
        message=(
            f"{fqdn} resolves."
            if reachable
            else f"{fqdn} did not resolve yet (DNS propagation in progress)."
        ),
        payload={"fqdn": fqdn, "provider": provider.name},
    )


def _onboarding_settings(school) -> dict:
    """Pull the rmc_public_onboarding dict (recorded by signup_school) off the school."""
    settings_dict = getattr(school, "settings", None) or {}
    rmc = settings_dict.get("rmc_public_onboarding")
    return rmc if isinstance(rmc, dict) else {}


def _maybe_apply_onboarding_blueprint_pack(school, actor=None) -> None:
    """
    Pass 7: apply the BlueprintPack the user selected in the onboarding wizard.

    Runs once during provisioning; no-op when the user picked "No pack". A failed
    apply is recorded but does not abort provisioning — the user can re-apply
    from Studio later.
    """
    if school is None:
        return
    pack_slug = (_onboarding_settings(school).get("pack_slug") or "").strip()
    if not pack_slug:
        return
    try:
        from apps.policies.blueprint_registry import apply_blueprint_pack
        from apps.policies.models import BlueprintPack
    except (ImportError, ModuleNotFoundError):
        return
    try:
        pack = BlueprintPack.objects.filter(slug=pack_slug, is_active=True).first()
    except (DatabaseError, AttributeError, TypeError, ValueError):
        pack = None
    if pack is None:
        _record_school_event(
            school,
            event_type="BLUEPRINT_TEMPLATE_RECORDED",
            status="WARNING",
            message=f"Blueprint pack '{pack_slug}' not found or inactive; skipped.",
            payload={"pack_slug": pack_slug},
        )
        return
    try:
        apply_blueprint_pack(school, pack, applied_by=actor)
    except (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError):
        log_exception_with_context(
            "schools.tasks: apply_blueprint_pack failed",
            school_id=getattr(school, "id", None),
            extra={"pack_slug": pack_slug},
        )
        _record_school_event(
            school,
            event_type="BLUEPRINT_TEMPLATE_RECORDED",
            status="ERROR",
            message=f"Failed to apply blueprint pack '{pack_slug}'.",
            payload={"pack_slug": pack_slug},
        )
        return
    _record_school_event(
        school,
        event_type="BLUEPRINT_TEMPLATE_RECORDED",
        status="SUCCESS",
        message=f"Applied onboarding blueprint pack '{pack_slug}'.",
        payload={"pack_slug": pack_slug, "pack_name": pack.name, "version": pack.version},
    )


class _NullStyle:
    """Shim mimicking django.core.management.color_style for non-command callers."""

    def __getattr__(self, _name):
        return lambda message="": message


def _maybe_seed_onboarding_sample_data(school) -> None:
    """
    Pass 7: when the user toggled "Start with sample data", seed demo users
    (teachers, students, parents) so the admin lands on a populated tenant.
    No-op when the flag is false or the seeder is unavailable.
    """
    if school is None:
        return
    if not bool(_onboarding_settings(school).get("sample_data", False)):
        return
    try:
        import io

        from apps.schools.demo_user_seeding import seed_demo_users_for_school
    except (ImportError, ModuleNotFoundError):
        return
    try:
        seed_demo_users_for_school(
            school,
            password="Test1234",
            username_prefix="demo",
            stdout=io.StringIO(),
            style=_NullStyle(),
        )
    except (
        DatabaseError,
        IntegrityError,
        AttributeError,
        TypeError,
        ValueError,
        RuntimeError,
    ):
        log_exception_with_context(
            "schools.tasks: seed_demo_users_for_school failed",
            school_id=getattr(school, "id", None),
        )
        _record_school_event(
            school,
            event_type="SAMPLE_DATA_READY",
            status="ERROR",
            message="Sample data seeding failed.",
        )
        return
    _record_school_event(
        school,
        event_type="SAMPLE_DATA_READY",
        status="SUCCESS",
        message="Sample data seeded (demo.admin, demo.teacher, demo.parent).",
        payload={"username_prefix": "demo"},
    )


# Exception types that may be raised during provisioning (catch, log, re-raise or retry).
_PROVISIONING_FAILURES = (
    DatabaseError,
    IntegrityError,
    OSError,
    ConnectionError,
    ValueError,
    TypeError,
    AttributeError,
    ImportError,
    RuntimeError,
)


def provision_school_sync(school_id: str, contact_email: str = "", **kwargs):
    """Run provisioning synchronously (no Celery)."""
    try:
        with transaction.atomic():
            _do_provision(school_id, contact_email=contact_email, **kwargs)
    except _PROVISIONING_FAILURES as exc:
        _record_school_event_by_id(
            school_id,
            event_type="FAILED",
            status="ERROR",
            message="Provisioning failed",
            payload={"error": str(exc)},
        )
        raise


def dispatch_provision_school(
    school_id: str, contact_email: str = "", **kwargs
) -> dict:
    """
    Queue provisioning when Celery is available; otherwise fall back to synchronous provisioning.
    Returns a stable payload for request-layer audit logging.
    """
    try:
        result = provision_school_task.delay(
            str(school_id), contact_email=contact_email, **kwargs
        )
        return {
            "queued": True,
            "fallback": False,
            "job_id": getattr(result, "id", None),
            "message": "Provisioning queued.",
        }
    except (
        AttributeError,
        ConnectionError,
        ImportError,
        KombuOperationalError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        logger.warning(
            "Provisioning queue unavailable for school %s; falling back to sync: %s",
            school_id,
            exc,
        )
        provision_school_sync(str(school_id), contact_email=contact_email, **kwargs)
        return {
            "queued": False,
            "fallback": True,
            "job_id": None,
            "message": "Celery unavailable; provisioning started in synchronous fallback mode.",
            "reason": str(exc),
        }


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
        except (
            OSError,
            ConnectionError,
            DatabaseError,
            AttributeError,
            TypeError,
            ValueError,
        ):
            logger.exception(
                "Failed syncing domains for already active school %s", school_id
            )
        logger.info("School %s already active, skip provisioning", school_id)
        return
    _record_school_event(
        school,
        event_type="STARTED",
        status="INFO",
        message="Provisioning job started.",
    )
    try:
        from apps.platform_runtime.events import emit_platform_event

        emit_platform_event(
            "provisioning_started",
            {"school_id": str(school.id), "slug": getattr(school, "slug", "") or ""},
            tenant_id=str(getattr(school, "id", "") or ""),
            school_id=None,
            idempotency_key=f"provision-start:{school.id}",
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

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
            logger.info(
                "Created admin user %s for school %s", admin_user.username, school_id
            )
        SchoolMembership.objects.get_or_create(
            user=admin_user,
            school=school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        try:
            from apps.registries.services import (
                apply_wedge_14_22_sector_access_roles_to_user,
            )

            role_payload = apply_wedge_14_22_sector_access_roles_to_user(
                school, admin_user
            )
            if role_payload.get("applied") or role_payload.get(
                "admin_access_role_attached"
            ):
                _record_school_event(
                    school,
                    event_type="SECTOR_ROLES_APPLIED",
                    status="SUCCESS",
                    message="Wedge 14–22: sector AccessRoles attached to bootstrap user.",
                    payload={
                        "sector": role_payload.get("sector"),
                        "applied_access_roles": role_payload.get("applied"),
                        "admin_access_role_attached": role_payload.get(
                            "admin_access_role_attached"
                        ),
                    },
                )
        except (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError):
            log_exception_with_context(
                "schools.tasks: apply_wedge_14_22_sector_access_roles_to_user failed",
                school_id=getattr(school, "id", None),
            )

    # Seed academic year and terms from education profile + region defaults.
    # W1-9: When no education_profile_code is set, resolve_profile_for_school uses school.default_region_id
    # (from country_code at create) and returns one approved profile per country via for_school() + ensure_country_profile().
    region = school.default_region
    from apps.policies.policy_registry import get_effective_policy

    _policy = get_effective_policy(school)
    requested_profile_code = str(_policy.get("education_profile_code") or "").strip()
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
        term_count = int(
            getattr(profile, "term_count_per_year", term_count) or term_count
        )
        start_month = int(
            getattr(profile, "academic_year_start_month", start_month) or start_month
        )
        term_labels = profile.normalized_term_labels()
    # UK/British term preset at signup (RUNMYCAMPUS_ROADMAP_TASKS); override term labels for GB
    term_preset = (_policy.get("term_preset") or "").strip()
    if term_preset == "UK":
        start_month = 9
        term_count = 3
        term_labels = term_labels or ["Michaelmas", "Lent", "Trinity"]
    # Apply resolved profile to school.settings for all schools that have a profile (not only UK/GB)
    if profile:
        profile_config = {
            "education_profile_code": profile.code,
            "grading_scale": profile.grading_scale,
            "default_language": profile.default_language,
            "default_currency": profile.default_currency,
            "term_labels": term_labels,
        }
        if isinstance(getattr(profile, "config", None), dict) and profile.config.get(
            "report_template_family"
        ):
            profile_config["report_template_family"] = profile.config.get(
                "report_template_family"
            )
        # Read current settings for merge; profile defaults from policy/resolver flow
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
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
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
        except (
            OSError,
            ConnectionError,
            DatabaseError,
            AttributeError,
            TypeError,
            ValueError,
        ):
            logger.exception("Failed syncing domains for school %s", school.id)

    # Pass 7: auto-create the tenant subdomain via the configured DNS provider.
    # No-op when DNS_PROVIDER is unset; logs success/failure as a provisioning event.
    try:
        _provision_dns_record(school)
    except (
        OSError,
        ConnectionError,
        DatabaseError,
        AttributeError,
        TypeError,
        ValueError,
    ):
        logger.exception("DNS auto-provision raised for school %s", school.id)

    # Tenant-scoped creation: schema mode uses tenant_context(client); RLS mode pins
    # app.current_school_id to the new school so FORCE'd WITH CHECK clauses pass.
    with _optional_tenant_context(tenant_client), rls_school(school.id):
        # Phase B: Tenant Provisioning Engine — create TenantSystem rows from wizard selection (multi-system)
        # Use policy for provisioning config (no direct school.settings read per blueprint)
        provisioning = _policy.get("provisioning") or {}
        education_system_ids = provisioning.get("education_system_ids") or []
        if not isinstance(education_system_ids, list):
            education_system_ids = []
        profile_codes = [str(c).strip() for c in education_system_ids if c]
        if not profile_codes and profile and getattr(profile, "code", None):
            profile_codes = [profile.code]
        if profile_codes:
            from apps.global_registries.models import (
                EducationSystemProfile,
                TenantSystem,
            )

            approved = EducationSystemProfile.objects.filter(
                code__in=profile_codes,
                is_active=True,
                approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
            )
            for prof in approved:
                TenantSystem.objects.get_or_create(
                    school=school, system=prof, defaults={}
                )
            try:
                from apps.siteconfig.tenant_config import (
                    sync_tenant_modules_to_school_features,
                )

                sync_tenant_modules_to_school_features(school)
            except (
                ImportError,
                AttributeError,
                TypeError,
                ValueError,
                DatabaseError,
            ) as e:
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
        except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
            logger.exception(
                "Failed to compile tenant config snapshot for school %s", school_id
            )

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
                    next_term_start = _month_start_add(
                        year_start, (i + 1) * months_per_term
                    )
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
        logger.info(
            "Seeded academic year and %s terms for school %s", term_count, school_id
        )
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
                raw_category = str(
                    item.get("category", Subject.Category.GENERAL)
                    if isinstance(item, dict)
                    else Subject.Category.GENERAL
                ).upper()
                category = (
                    raw_category
                    if raw_category in valid_categories
                    else Subject.Category.GENERAL
                )
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
        seed_fn = (
            getattr(profile, "normalized_classroom_seed", None) if profile else None
        )
        if callable(seed_fn):
            try:
                classroom_seed_names = list(seed_fn())[:3]
            except (TypeError, AttributeError, ValueError):
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
            # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
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
            logger.info(
                "Seeded %s default classrooms for school %s",
                classroom_created,
                school_id,
            )
            _record_school_event(
                school,
                event_type="CLASSROOMS_READY",
                status="SUCCESS",
                message="Default classrooms prepared.",
                payload={"classrooms_created": classroom_created},
            )

        try:
            from apps.schools.provisioning_blueprint import (
                record_school_template_blueprint,
            )

            record_school_template_blueprint(school)
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            RuntimeError,
        ):
            logger.debug("record_school_template_blueprint skipped", exc_info=True)

        try:
            from apps.schools.provisioning_personas import (
                seed_sample_teacher_parent_student,
                should_seed_demo_personas,
            )

            if should_seed_demo_personas(**kwargs):
                seed_sample_teacher_parent_student(school)
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            DatabaseError,
            IntegrityError,
            RuntimeError,
        ):
            logger.warning(
                "seed_sample_teacher_parent_student failed school=%s",
                school_id,
                exc_info=True,
            )

        try:
            from apps.packages.tenant_pack_install import (
                sync_experience_pack_install_from_school,
            )

            sync_experience_pack_install_from_school(school)
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            DatabaseError,
            RuntimeError,
        ):
            logger.debug("sync_experience_pack_install_from_school skipped", exc_info=True)

        # Pass 7: apply the blueprint pack chosen in the onboarding wizard.
        _maybe_apply_onboarding_blueprint_pack(school, admin_user)

        # Pass 7: seed demo users + a populated sample class when the user opted in.
        _maybe_seed_onboarding_sample_data(school)

        school.is_active = True
        school.save(update_fields=["is_active", "settings", "updated_at"])
        try:
            from apps.finance.payment_provision import bind_tenant_payment_policy_safe

            bind_tenant_payment_policy_safe(school)
        except ImportError:
            pass
        try:
            from apps.platform_runtime.offline_mode_bundle import (
                maybe_apply_offline_bundle_on_provision,
            )

            maybe_apply_offline_bundle_on_provision(school)
        except ImportError:
            pass
        try:
            from apps.policies.policy_registry import invalidate_policy_cache

            invalidate_policy_cache(school)
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
        try:
            from apps.schools.activation_gate import set_activation_gate_pending

            set_activation_gate_pending(school)
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
        _record_school_event(
            school,
            event_type="COMPLETED",
            status="SUCCESS",
            message="Provisioning completed successfully.",
        )
        try:
            from apps.platform_runtime.events import emit_platform_event

            emit_platform_event(
                "provisioning_completed",
                {
                    "school_id": str(school.id),
                    "slug": getattr(school, "slug", "") or "",
                },
                tenant_id=str(getattr(school, "id", "") or ""),
                school_id=None,
                idempotency_key=f"provision-done:{school.id}",
            )
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
    logger.info("School %s provisioning complete", school_id)

    # Phase Welcome: send in-process so the same worker/env that finished
    # provisioning holds SMTP credentials (avoids a second queued task with no EMAIL_*).
    # v4.00.2 audit (2026-05-28): record WELCOME_EMAIL_{SENT,FAILED}
    # events so the tenant timeline + offboarding queue surface delivery
    # status. Uses string event-types (same pattern as DNS_* events
    # above) — no migration needed because CharField.choices is only
    # form-level validation in Django.
    if (contact_email or "").strip():
        from apps.schools.welcome_email import send_welcome_email

        sent = send_welcome_email(str(school.id), contact_email)
        recipient_domain = (
            contact_email.split("@", 1)[-1] if "@" in contact_email else ""
        )
        _record_school_event(
            school,
            event_type="WELCOME_EMAIL_SENT" if sent else "WELCOME_EMAIL_FAILED",
            status="SUCCESS" if sent else "WARNING",
            message=(
                "Welcome email sent."
                if sent
                else "Welcome email not sent (check EMAIL_*); provisioning still completed."
            ),
            payload={"recipient_domain": recipient_domain},
        )
        if not sent:
            logger.warning(
                "Welcome email not sent for school %s (check EMAIL_* on Celery worker)",
                school_id,
            )


# Celery task (optional)
try:
    from celery import shared_task

    @shared_task(bind=True, max_retries=3)
    def provision_school_task(self, school_id: str, contact_email: str = "", **kwargs):
        try:
            with transaction.atomic():
                _do_provision(school_id, contact_email=contact_email, **kwargs)
        except _PROVISIONING_FAILURES as exc:
            logger.exception("Provisioning failed for %s", school_id)
            _record_school_event_by_id(
                school_id,
                event_type="FAILED",
                status="ERROR",
                message="Provisioning failed",
                payload={"error": str(exc)},
            )
            raise self.retry(exc=exc)

    @shared_task(name="schools.purge_tenant_media_task")
    def purge_tenant_media_task(school_slug: str, manifest: dict | None = None) -> dict:
        from apps.schools.tenant_offboarding import cleanup_tenant_media

        return cleanup_tenant_media(school_slug, manifest)

    @shared_task(name="schools.run_scheduled_tenant_purges")
    def run_scheduled_tenant_purges_task(*, dry_run: bool = False, limit: int = 10) -> dict:
        from apps.schools.tenant_offboarding import run_scheduled_purges

        return run_scheduled_purges(actor=None, dry_run=dry_run, limit=limit)

    @shared_task(name="schools.ensure_demo_environment_scheduled")
    def ensure_demo_environment_scheduled() -> dict:
        """
        Nightly/periodic refresh of the public demo school (data + demo users).
        Opt-in: set env ENSURE_DEMO_CRON_SLUG (e.g. demo-school). No-op if unset.
        """
        import os

        from django.core.management import call_command

        slug = (os.getenv("ENSURE_DEMO_CRON_SLUG") or "").strip()
        if not slug:
            return {"ok": False, "skipped": True, "reason": "ENSURE_DEMO_CRON_SLUG unset"}
        call_command(
            "ensure_demo_environment",
            school_slug=slug,
        )
        return {"ok": True, "school_slug": slug}

except ImportError:

    def provision_school_task(*args, **kwargs):
        provision_school_sync(*args, **kwargs)

    def ensure_demo_environment_scheduled(*args, **kwargs):
        return None
