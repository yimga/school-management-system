"""
Provisioning task: after School row is created, create admin user, school_members, seed terms/subjects, logo path.
Can be run as Celery task or synchronously.
When USE_DJANGO_TENANTS is True, ensures Client and Domain exist and runs tenant-scoped creation in tenant_context.
"""

import contextvars
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

# Re-entrancy guard for provisioning drives on the current execution context.
# The primary recursion source — a FAILED provision's finalize_run applying
# requeue_provision INLINE — is now closed at the root (the failure finalize
# passes auto_apply=False; retry is owned out-of-band by the provision
# watchdog). This guard remains as defense-in-depth against ANY other inline
# re-dispatch of a school already on the current call stack (the
# complete_provisioning_for_school booster, an operator requeue that runs eager,
# a poll re-trigger): without it such a re-entry recurses through _do_provision,
# nesting atomic blocks until the transaction is poisoned
# (TransactionManagementError) so the finalize never completes cleanly.
_active_provision_drives: contextvars.ContextVar[frozenset[str]] = (
    contextvars.ContextVar("rmc_active_provision_drives", default=frozenset())
)

try:
    from kombu.exceptions import OperationalError as KombuOperationalError
except ImportError:  # pragma: no cover - kombu is installed in production/test envs

    class KombuOperationalError(Exception):
        """Fallback exception type when kombu is unavailable."""


User = get_user_model()


def _merge_provisioning_settings(school, **updates) -> None:
    """Persist Phase A/B flags under ``school.settings['provisioning']``."""
    from django.utils import timezone

    settings_blob = dict(getattr(school, "settings", None) or {})
    prov = dict(settings_blob.get("provisioning") or {})
    prov.update(updates)
    if updates.get("phase_a_complete"):
        prov.setdefault("phase_a_at", timezone.now().isoformat())
    if updates.get("phase_b_complete"):
        prov.setdefault("phase_b_at", timezone.now().isoformat())
        prov["phase_b_step"] = "complete"
    settings_blob["provisioning"] = prov
    school.settings = settings_blob


def _activate_portal_phase_a(
    school,
    *,
    school_id: str,
    contact_email: str,
    admin_user,
    wf_run,
    pulse,
) -> None:
    """Phase A terminus — portal login enabled; Phase B seed may continue async."""
    pulse(wf_run, "activate")
    _merge_provisioning_settings(school, phase_a_complete=True)
    school.is_active = True
    school.save(update_fields=["is_active", "settings", "updated_at"])
    try:
        from apps.schools.signup_completion_notifications import finalize_tenant_activation

        finalize_tenant_activation(school, contact_email, admin_user=admin_user)
    except ImportError:
        pass
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
        event_type="PORTAL_READY",
        status="SUCCESS",
        message="Portal activated — optional setup may continue in background.",
    )
    try:
        from apps.lifecycle.unified_lifecycle import record_unified_transition

        record_unified_transition(
            school,
            "activating",
            note="portal_phase_a_complete",
            payload={"phase": "a"},
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass


# v4.00.2 audit — provisioning event_type constants for sites that need to
# filter the timeline. SchoolProvisioningEvent.event_type is a free-form
# CharField (choices=EventType.choices is form-level only, not a DB
# constraint); the canonical EventType TextChoices in apps.schools.models
# covers the provisioning state machine. The constants below cover the
# tail-end provisioning events recorded via _record_school_event using
# string event_types — keep them in sync with the actual emit sites in
# _do_provision and _provision_dns_record below.
EVENT_DNS_RECORD_SKIPPED = "DNS_RECORD_SKIPPED"
EVENT_DNS_RECORD_FAILED = "DNS_RECORD_FAILED"
EVENT_DNS_RECORD_CREATED = "DNS_RECORD_CREATED"
EVENT_DNS_REACHABLE = "DNS_REACHABLE"
EVENT_DNS_NOT_REACHABLE = "DNS_NOT_REACHABLE"
EVENT_WELCOME_EMAIL_SENT = "WELCOME_EMAIL_SENT"
EVENT_WELCOME_EMAIL_FAILED = "WELCOME_EMAIL_FAILED"


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

        # Nested atomic = savepoint so a best-effort log write cannot poison
        # the outer provision_school_task / provision_school_sync transaction.
        with transaction.atomic():
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
        with transaction.atomic():
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
            event_type=EVENT_DNS_RECORD_SKIPPED,
            status="INFO",
            message="DNS automation disabled (DNS_PROVIDER unset).",
            payload={"fqdn": fqdn},
        )
        return
    if not target:
        _record_school_event(
            school,
            event_type=EVENT_DNS_RECORD_FAILED,
            status="WARNING",
            message="DNS_CNAME_TARGET not configured.",
            payload={"fqdn": fqdn, "provider": provider.name},
        )
        return

    result = provider.create_record(subdomain=fqdn, target=target)
    if result.ok:
        _record_school_event(
            school,
            event_type=EVENT_DNS_RECORD_CREATED,
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
            event_type=EVENT_DNS_RECORD_FAILED,
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
        event_type=EVENT_DNS_REACHABLE if reachable else EVENT_DNS_NOT_REACHABLE,
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
        from apps.policies.models import BlueprintPack, TenantBlueprint
    except (ImportError, ModuleNotFoundError):
        return
    try:
        pack = BlueprintPack.objects.filter(slug=pack_slug, is_active=True).first()  # tenant-isolation-allow: celery-platform-provisioning-beat-cross-tenant
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
    # Idempotency guard: a requeue / reconcile re-runs this provisioning step,
    # and apply_blueprint_pack() creates a fresh PolicyBundle on every call (by
    # design — that powers version-bump history in update_bundle_for_schools).
    # Without this check, each requeue accrues a redundant "(applied)" bundle.
    # A *failed* first apply never sets TenantBlueprint.applied_pack, so this
    # still retries on the next requeue — it only skips an already-applied pack.
    try:
        if TenantBlueprint.objects.filter(  # tenant-isolation-allow: celery-platform-provisioning-beat-cross-tenant
            school=school, applied_pack=pack
        ).exists():
            return
    except (DatabaseError, AttributeError, TypeError, ValueError):
        pass
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
    """Run provisioning synchronously (no Celery).

    Intentionally **not** wrapped in a single outer ``transaction.atomic()``:
    ``_do_provision`` creates a ``WorkflowRun`` at the start and pulses steps
    while work runs. An outer atomic block hid the run from poll APIs until
    the entire job committed (owners saw fake 5% for minutes).
    """
    try:
        _do_provision(school_id, contact_email=contact_email, **kwargs)
    except _PROVISIONING_FAILURES as exc:
        _record_school_event_by_id(
            school_id,
            event_type="FAILED",
            status="ERROR",
            message="Provisioning failed",
            payload={"error": str(exc)},
        )
        try:
            from apps.schools.models import School

            school = School.objects.filter(id=school_id).first()
            if school:
                _emit_provisioning_failed_notification(
                    school, contact_email, error=str(exc)
                )
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
        raise


def _emit_provisioning_failed_notification(school, contact_email: str, *, error: str) -> None:
    """NOTIF-001 facade — idempotent operator alert on provision failure."""
    try:
        from apps.platform_runtime.tenant_lifecycle_notifications import (
            EVENT_PROVISIONING_FAILED,
            emit_tenant_lifecycle_notification,
        )

        emit_tenant_lifecycle_notification(
            school,
            EVENT_PROVISIONING_FAILED,
            contact_email=contact_email or "",
            error=error or "",
        )
    except ImportError:
        from apps.schools.signup_completion_notifications import (
            notify_provisioning_failed_operator,
        )

        notify_provisioning_failed_operator(school, contact_email, error=error)


def resolve_provisioning_contact_email(school, contact_email: str = "") -> str:
    """Best available owner email for this school — the ONLY way to repair a husk.

    ``ensure_admin_user_for_school`` returns ``(None, False)`` on an empty email,
    so the tenant-admin step silently skips and the school ends up with no owner
    account. That was a FIXED POINT on the broken state: every resume path sourced
    its email from ``_primary_owner_user`` (a SchoolMembership lookup), and the
    only thing that creates that membership is the step that just skipped. No
    membership -> no email -> step skips -> still no membership, forever. A
    re-drive could never repair the one thing it was re-driven to repair.

    So this resolves from every durable record of the owner's address, not just
    the one the failed step would have written:

      1. an explicitly passed address (the signup / operator path)
      2. the primary owner membership (the normal, already-healthy case)
      3. ``SignupVerification.email`` — written at signup, BEFORE provisioning
         runs, and never dependent on the admin_user step having succeeded
      4. the onboarding blob captured on the school's own settings

    Returns "" when genuinely unknown; callers must still treat that as a skip.
    """
    email = (contact_email or "").strip()
    if email:
        return email

    try:
        from apps.schools.pending_tenant_discovery import _primary_owner_user

        owner = _primary_owner_user(school)
        email = (getattr(owner, "email", "") or "").strip()
        if email:
            return email
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
        logger.debug("resolve_provisioning_contact_email: owner lookup failed", exc_info=True)

    try:
        from .models import SignupVerification

        row = (
            SignupVerification.objects.filter(school=school)
            .only("email")
            .order_by("-created_at")
            .first()
        )
        email = (getattr(row, "email", "") or "").strip()
        if email:
            logger.info(
                "resolve_provisioning_contact_email: recovered owner email from "
                "SignupVerification for school_id=%s (no owner membership exists)",
                getattr(school, "id", None),
            )
            return email
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
        logger.debug("resolve_provisioning_contact_email: signup lookup failed", exc_info=True)

    settings_blob = getattr(school, "settings", None) or {}
    if isinstance(settings_blob, dict):
        blob = settings_blob.get("rmc_public_onboarding")
        if isinstance(blob, dict):
            for key in ("contact_email", "email", "owner_email", "admin_email"):
                email = str(blob.get(key) or "").strip()
                if email:
                    return email
    return ""


def ensure_admin_user_for_school(school, contact_email: str):
    """Find-or-create the school's bootstrap ADMIN owner + primary membership.

    Idempotent, and deliberately callable from BOTH the (possibly async)
    provisioning task AND synchronously from the signup-verify view. The verify
    view needs the owner row to EXIST so it can hand the new owner a token-authed
    onboarding link — but on a broker-backed deploy provisioning is queued on a
    Celery worker that may not have run yet, so the owner wouldn't exist at
    redirect time and would be dumped on the login page (the dead-end this flow
    removes). Whichever path runs first creates the row; the other finds it.
    Returns ``(admin_user, created)`` (``(None, False)`` when no email).
    """
    from .models import SchoolMembership

    if not (contact_email or "").strip():
        return None, False
    contact_email = contact_email.strip()
    # tenant-isolation-allow: bootstrap-owner-lookup-by-email-pre-membership
    admin_user = User.objects.filter(email=contact_email).first()
    created = False
    if not admin_user:
        username = contact_email.split("@")[0][:150] or f"admin_{school.slug}"  # magic-number-allow: string-truncation-cap
        # tenant-isolation-allow: bootstrap-owner-username-uniqueness-check
        if User.objects.filter(username=username).exists():
            username = f"{username}_{school.slug}"[:150]  # magic-number-allow: string-truncation-cap
        admin_user = User.objects.create_user(
            username=username,
            email=contact_email,
            # Strong random value even though password login is disabled below.
            password=secrets.token_urlsafe(32),  # magic-number-allow: token-byte-length
            role=User.Role.ADMIN,
        )
        admin_user.set_unusable_password()
        admin_user.save()
        created = True
        logger.info(
            "Created admin user %s for school %s",
            admin_user.username,
            getattr(school, "id", None),
        )
    membership, membership_created = SchoolMembership.objects.get_or_create(
        user=admin_user,
        school=school,
        # The user who creates the school is its OWNER ("super admin") by default.
        # Ownership is a per-school flag (transferable, multi-owner), NOT User.role.
        defaults={
            "role": User.Role.ADMIN,
            "is_primary": True,
            "is_school_owner": True,
        },
    )
    if not membership_created:
        SchoolMembership.objects.filter(pk=membership.pk, school=school).update(
            role=User.Role.ADMIN,
            is_primary=True,
            is_school_owner=True,
        )
    # Repeat signups with the same email must not keep an older demo school
    # as primary — onboarding resolves is_primary=True first.
    SchoolMembership.objects.filter(user=admin_user, is_primary=True).exclude(  # tenant-isolation-allow: provision-demote-other-primary-memberships-same-user
        school=school
    ).update(is_primary=False)
    return admin_user, created


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


def complete_provisioning_for_school(
    school_id: str, contact_email: str = "", **kwargs
) -> dict:
    """
    Queue provisioning when Celery is available, then run sync in-process if the
    school is still inactive. Owner-critical paths use this so signup does not
    stall when the worker is asleep or the queue succeeds but nothing consumes it.
    """
    from .models import School

    result = dict(
        dispatch_provision_school(str(school_id), contact_email=contact_email, **kwargs)
    )
    school = School.objects.filter(id=school_id).only("is_active", "settings").first()
    try:
        from apps.schools.provisioning_progress import resolve_portal_ready

        portal_ready = resolve_portal_ready(school) if school else False
    except ImportError:
        portal_ready = bool(school and school.is_active)

    if result.get("fallback"):
        result["sync_completed"] = True
        result["portal_ready"] = portal_ready
        result["is_active"] = portal_ready
        return result
    if school and not portal_ready:
        try:
            provision_school_sync(str(school_id), contact_email=contact_email, **kwargs)
            result["sync_completed"] = True
        except _PROVISIONING_FAILURES as exc:
            result["sync_completed"] = False
            result["sync_error"] = str(exc)[:200]
            logger.warning(
                "complete_provisioning sync failed for school %s: %s",
                school_id,
                exc,
            )
        school.refresh_from_db(fields=["is_active", "settings"])
        try:
            from apps.schools.provisioning_progress import resolve_portal_ready

            portal_ready = resolve_portal_ready(school)
        except ImportError:
            portal_ready = bool(school.is_active)
    else:
        result["sync_completed"] = False
    result["portal_ready"] = portal_ready
    result["is_active"] = portal_ready
    return result


def kick_complete_provisioning_background(
    school_id: str, contact_email: str = "", **kwargs
) -> None:
    """Best-effort daemon-thread completion so verify_signup stays fast (<1s)."""
    import threading

    from django.db import close_old_connections, transaction

    sid = str(school_id)
    email = (contact_email or "").strip()
    kw = dict(kwargs)

    def _run() -> None:
        try:
            from .models import School

            school = School.objects.filter(id=sid).only("is_active", "settings").first()
            from apps.schools.provisioning_progress import provisioning_needs_resume

            # Run when the school is not yet active OR when it is active but
            # Phase B never completed (half-provisioned tenant the operator is
            # repairing from Tenant 360 / the flight-deck Retry card).
            if school and (
                not school.is_active or provisioning_needs_resume(school)
            ):
                complete_provisioning_for_school(sid, contact_email=email, **kw)
        except (
            DatabaseError,
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            OSError,
        ):
            logger.warning(
                "kick_complete_provisioning_background failed school_id=%s",
                sid,
                exc_info=True,
            )
        finally:
            close_old_connections()

    def _start() -> None:
        threading.Thread(
            target=_run,
            daemon=True,
            name=f"provision-kick-{sid[:8]}",
        ).start()

    transaction.on_commit(_start)


# pg_advisory_lock() takes a signed bigint — mask the sha256 slice to 63 bits so the
# key is always positive.
_PG_ADVISORY_LOCK_KEY_MASK = 0x7FFFFFFFFFFFFFFF  # magic-number-allow: postgres-signed-bigint-advisory-lock-key-mask


def _provision_lock_key(school_id: str) -> int:
    import hashlib

    digest = hashlib.sha256(f"provision:{school_id}".encode()).digest()
    # Mask to a 63-bit POSITIVE int: pg_advisory_lock takes a signed bigint, so the
    # sign bit must be cleared or the key overflows.
    return int.from_bytes(digest[:8], "big") & _PG_ADVISORY_LOCK_KEY_MASK


def _acquire_provision_lock(school_id: str) -> bool:
    """Cross-process single-flight for a provisioning drive. True ⇒ proceed.

    A Postgres SESSION advisory lock — genuinely cross-worker (unlike the watchdog's
    per-process cache lock under LocMemCache), and a dead drive's lock auto-releases
    when its connection drops. No-op ⇒ True on non-Postgres (single-process local
    dev). Fail-OPEN on any error so a lock-infra hiccup never blocks provisioning.
    """
    from django.db import connection

    if connection.vendor != "postgresql":
        return True
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [_provision_lock_key(school_id)])
            row = cur.fetchone()
            return bool(row and row[0])
    except Exception:  # noqa: BLE001 — never block provisioning on a lock error
        logger.debug("provision advisory lock acquire failed for %s", school_id, exc_info=True)
        return True


def _release_provision_lock(school_id: str) -> None:
    from django.db import connection

    if connection.vendor != "postgresql":
        return
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", [_provision_lock_key(school_id)])
    except Exception:  # noqa: BLE001 — a stale/closed-session lock frees itself anyway
        logger.debug("provision advisory unlock failed for %s", school_id, exc_info=True)


def _has_prior_failed_provision(school_id: str) -> bool:
    """True if this school already has a failed/cancelled provision run.

    Used to email the operator only on the FIRST failure — not on every auto-resume
    — so a permanently-broken provision cannot generate an alert storm.
    """
    try:
        from apps.platform_runtime.models import WorkflowRun

        # tenant-isolation-allow: provision-email-dedup-prior-failed-run-lookup
        return WorkflowRun.objects.filter(
            workflow_key="tenant_school_provision",
            school_id=str(school_id),
            status__in=("failed", "cancelled"),
        ).exists()
    except Exception:  # noqa: BLE001
        return False


def _do_provision(school_id: str, contact_email: str = "", **kwargs):
    from .models import School

    school = School.objects.filter(id=school_id).first()
    if not school:
        logger.warning("School %s not found for provisioning", school_id)
        return
    if school.is_active:
        from apps.schools.provisioning_progress import provisioning_needs_resume

        if not provisioning_needs_resume(school):
            # Fully provisioned: Phase A activated AND Phase B seed completed.
            # Nothing left to do but keep runtime domain routing in sync.
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
            logger.info(
                "School %s already fully provisioned, skip provisioning", school_id
            )
            return
        # Active but Phase B never completed — e.g. the seed_data step failed on a
        # tenant schema missing recently-added columns (academics.school_id), leaving
        # the school LIVE (Phase A) but with no academic year / terms / subjects /
        # classrooms. Do NOT bail here: fall through to re-run the pipeline so the
        # tenant-schema migrate + idempotent seed can finish Phase B. Every step is
        # get_or_create / delivery-gated, so re-entry on an active school is safe.
        # This is what lets the flight-deck "Retry" card (requeue_provision) and the
        # stuck-sweep autopilot actually REPAIR a half-provisioned tenant instead of
        # no-op'ing on it.
        logger.info(
            "School %s active but Phase B incomplete — resuming provisioning",
            school_id,
        )

    # Single-flight guard (2026-07-15): refuse to start a second concurrent drive
    # while one is genuinely in flight (a WorkflowRun whose heartbeat is fresh).
    # This kills the double-migrate race where a queued task and the in-request
    # booster in complete_provisioning_for_school both run `migrate` on one fresh
    # schema, and it stops an owner poll from re-triggering a new inline migrate
    # every few seconds while a background resume is already running. A
    # heartbeat-DEAD run is NOT "live", so this never blocks a legitimate resume of
    # a run whose process died mid-migrate. Best-effort: a check failure falls
    # through to the normal drive rather than blocking provisioning.
    try:
        from apps.schools.provision_watchdog import provisioning_drive_is_live

        if provisioning_drive_is_live(school):
            logger.info(
                "School %s already has a live provisioning drive — skipping concurrent re-entry",
                school_id,
            )
            return
    except (ImportError, AttributeError, TypeError, ValueError):
        logger.debug("provisioning single-flight check skipped", exc_info=True)

    # Re-entrancy guard (2026-07-16): suppress a synchronous re-drive of a school
    # already on the current call stack. The primary inline-recursion source — the
    # failure finalize below applying requeue_provision INLINE — is now closed at
    # its root (it passes auto_apply=False; the async watchdog / reconcile sweep
    # off the /health/ tick owns the retry out-of-band). This guard stays as
    # defense-in-depth against any OTHER inline re-drive of a school already on the
    # call stack, which would otherwise recurse here unboundedly and poison the
    # transaction.
    _sid = str(school_id)
    _active_drives = _active_provision_drives.get()
    if _sid in _active_drives:
        logger.warning(
            "Re-entrant provisioning drive for school %s suppressed "
            "(auto-fix recursion guard); async watchdog will retry",
            school_id,
        )
        return
    _drive_token = _active_provision_drives.set(_active_drives | {_sid})
    _lock_ok = False
    try:
        # Cross-process single-flight (Finding 1): the watchdog's per-process cache
        # lock does NOT span gunicorn workers under LocMemCache (the Redis-less
        # topology), so two workers could both pass provisioning_drive_is_live and
        # migrate one fresh schema. A Postgres advisory lock is genuinely
        # cross-session (no-op ⇒ proceed on sqlite/local single-process).
        _lock_ok = _acquire_provision_lock(_sid)
        if not _lock_ok:
            logger.info(
                "School %s: another process is already driving provisioning — skipping",
                school_id,
            )
            return
        # Email the operator only on the FIRST failure for this school, never on
        # every auto-resume — otherwise a permanently-broken provision storms the
        # operator inbox (Finding 3).
        email_on_failure = not _has_prior_failed_provision(_sid)
        from apps.platform_runtime.workflow_tracker import (
            begin_run,
            finalize_run,
            pulse_workflow_step,
        )

        wf_run = begin_run(
            workflow_key="tenant_school_provision",
            steps=("admin_user", "profile", "tenant_schema", "seed_data", "activate"),
            school_id=str(school_id),
            # 600s (= registry slo_seconds). The `tenant_schema` step runs a blocking
            # django-tenants schema create + migrate that can take minutes with no
            # heartbeat; the old 180s (→270s stuck threshold) flagged a healthy run as
            # "stuck" mid-migrate. 600s → 900s threshold; the >1h abandonment reaper
            # still catches genuinely dead runs.
            expected_duration_seconds=600,  # magic-number-allow: workflow-expected-duration-seconds
            payload={"slug": getattr(school, "slug", "") or ""},
        )
        from apps.tenancy.boundary_core_guard import pinned_tenant_boundary

        try:
            with pinned_tenant_boundary(
                school_id=str(school_id), host="celery:provision"
            ):
                _do_provision_tracked(
                    school,
                    school_id,
                    contact_email=contact_email,
                    wf_run=wf_run,
                    pulse_workflow_step=pulse_workflow_step,
                    **kwargs,
                )
            finalize_run(wf_run, status="succeeded")
        except Exception as exc:
            # auto_apply=False: do NOT inline-remediate a provisioning failure.
            # finalize's failure-path auto-apply would run requeue_provision
            # INLINE, re-entering _do_provision synchronously (recursion + a
            # transaction-poison window that can swallow the FAILED finalize).
            # Provisioning retry is owned out-of-band by the provision watchdog +
            # reconcile sweeps (heartbeat-staleness driven, single-flighted,
            # circuit-broken), whose sweep already picks up status="failed" runs.
            finalize_run(
                wf_run,
                status="failed",
                error=exc,
                email_on_failure=email_on_failure,
                auto_apply=False,
            )
            raise
    finally:
        if _lock_ok:
            _release_provision_lock(_sid)
        _active_provision_drives.reset(_drive_token)


def _do_provision_tracked(
    school,
    school_id: str,
    *,
    contact_email: str = "",
    wf_run=None,
    pulse_workflow_step=None,
    **kwargs,
):
    """Body of ``_do_provision`` with workflow-progress step pulses."""
    # These names are used throughout this function. They were originally
    # imported locally inside ``_do_provision`` before this body was extracted
    # into its own function; the extraction left them out of scope here, which
    # crashed synchronous provisioning (the broker-unavailable fallback path,
    # e.g. when no Celery worker is running) with a NameError on
    # ``resolve_profile_for_school``. Re-declare the same local imports here.
    from apps.academics.models import AcademicYear, Term, Subject
    from apps.siteconfig.education_profile_engine import resolve_profile_for_school
    from django.utils import timezone
    from datetime import date, timedelta

    pulse = pulse_workflow_step or (lambda *a, **k: None)
    _record_school_event(
        school,
        event_type="STARTED",
        status="INFO",
        message="Provisioning job started.",
    )
    try:
        from apps.lifecycle.unified_lifecycle import record_unified_transition

        record_unified_transition(
            school,
            "provisioning",
            note="provision_job_started",
            payload={"workflow_key": "tenant_school_provision"},
        )
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
        pass
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

    pulse(wf_run, "admin_user")

    # Create default admin user if an owner email is resolvable and no user exists.
    # Shared with the signup-verify view via ensure_admin_user_for_school so the
    # owner row is identical no matter which path (sync provisioning here, or the
    # verify view up-front) creates it first.
    #
    # Resolve rather than trusting the passed value: a school whose FIRST drive
    # ran without an email has no owner membership, and every resume path derives
    # its email FROM that membership — so the missing owner could never be
    # repaired by a re-drive (a fixed point on the broken state). The resolver
    # falls back to SignupVerification / the onboarding blob, which are written
    # before provisioning and survive the failure.
    admin_user = None
    contact_email = resolve_provisioning_contact_email(school, contact_email)
    if contact_email:
        admin_user, _ = ensure_admin_user_for_school(school, contact_email)
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

    pulse(wf_run, "profile")

    # Ensure the school is linked to its region BEFORE profile resolution.
    # resolve_profile_for_school() / EducationSystemProfile.for_school() match an
    # approved profile by school.default_region_id. A school created without an
    # explicit region (operator create_school, region-less signup paths) leaves
    # default_region_id None, which made an existing approved country profile
    # (e.g. usa-any-auto) UNREACHABLE — for_school() returned None and the
    # auto_create branch passed region_code=None, so resolution fell through to
    # the generic fallback (the "No approved education profile resolved" WARNING).
    # The block below restores the assumption the comment under it already makes:
    # derive the region from country_code, idempotently + best-effort.
    if not school.default_region_id and (getattr(school, "country_code", "") or "").strip():
        try:
            from apps.siteconfig.education_profile_engine import (
                ensure_region_for_country,
            )

            _linked_region = ensure_region_for_country(school.country_code)
            if _linked_region is not None:
                school.default_region = _linked_region
                school.save(update_fields=["default_region", "updated_at"])
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            DatabaseError,
            IntegrityError,
        ):
            logger.debug(
                "region link from country_code skipped for school %s",
                school_id,
                exc_info=True,
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

    pulse(wf_run, "tenant_schema")

    # Schema-per-tenant: ensure Client and Domain exist so tenant schema is available
    tenant_client = _ensure_tenant_client(school)
    if tenant_client is None:
        if _use_django_tenants():
            # Schema mode but NO Client ⇒ client/schema creation soft-failed.
            # ensure_tenant_client_for_school() returns None (not raise) on a swallowed
            # DatabaseError or a non-postgres connection, so a transient DB blip here
            # would otherwise fall straight through to Phase A activation — producing a
            # LIVE tenant with no schema that 500s on every tenant-scoped query (the
            # half-provisioned "broken tenant" symptom). Refuse to activate: record +
            # raise so the run finalizes "failed" and the Retry card appears, exactly
            # like the TENANT_SCHEMA_FAILED path below. A retry re-runs this idempotently.
            _record_school_event(
                school,
                event_type="TENANT_CLIENT_FAILED",
                status="ERROR",
                message="Tenant client/schema unavailable in schema mode; aborting before activation.",
                payload={"schema_mode": True},
            )
            raise RuntimeError(
                f"tenant client unavailable for school {getattr(school, 'id', '?')} "
                "in schema mode; refusing to activate a schema-less tenant"
            )
        # RLS mode: no per-tenant Client is expected — sync domains and continue.
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
    else:
        # Bring the tenant schema to migration HEAD BEFORE Phase A activation and
        # seeding. ``Client.auto_create_schema`` migrates a brand-new schema when it
        # is first created, but two real cases leave a schema short of HEAD:
        #   (1) the schema already existed from an earlier provisioning attempt, so
        #       ensure_tenant_client_for_school returns it WITHOUT re-migrating; and
        #   (2) a schema created between deploys whose create-time migrate did not
        #       reach the latest leaf.
        # Either way a tenant-scoped query then 500s with "column ... does not
        # exist" (e.g. academics 0028 school_id) — exactly what made the seed_data
        # step fail and the owner's onboarding/done page + dashboard 500. ``migrate``
        # is idempotent (already-applied migrations are no-ops); this is the same
        # guarantee the onboard_tenant path and render_predeploy already provide.
        # DDL runs under boundary_bypass — a documented bypass case for the guard.
        try:
            from apps.platform_runtime.workflow_tracker import heartbeat_during
            from apps.schools.onboarding_service import _run_tenant_migrations
            from apps.tenancy.boundary_core_guard import boundary_bypass

            # The full-app-set schema migrate is one long blocking step. Without an
            # intra-step heartbeat a healthy-but-slow migrate (loaded free-tier DB)
            # blows past the stuck threshold and the run is false-flagged
            # "abandoned: no heartbeat past the stuck threshold" — exactly the
            # tenant_schema flight-deck card. Keep the run alive while it works.
            with boundary_bypass(reason="tenant-provision-schema-migrate"):
                with heartbeat_during(wf_run):
                    _run_tenant_migrations(tenant_client)
            _record_school_event(
                school,
                event_type="TENANT_SCHEMA_READY",
                status="SUCCESS",
                message="Tenant schema migrated to HEAD.",
                payload={"schema_name": getattr(tenant_client, "schema_name", "")},
            )
        except (
            ImportError,
            DatabaseError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            # Schema not ready ⇒ refuse to activate/seed a broken tenant. Record the
            # failure and re-raise so the run finalizes "failed" and the flight-deck
            # Retry card appears; a retry re-runs this idempotent migrate.
            _record_school_event(
                school,
                event_type="TENANT_SCHEMA_FAILED",
                status="ERROR",
                message="Tenant schema migrate failed; aborting before activation.",
                payload={"error": str(exc)[:500]},
            )
            raise

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

    # Phase A: activate portal before heavy seed (owner may log in while Phase B runs).
    _activate_portal_phase_a(
        school,
        school_id=school_id,
        contact_email=contact_email,
        admin_user=admin_user,
        wf_run=wf_run,
        pulse=pulse,
    )
    _merge_provisioning_settings(school, phase_b_step="seed_data")
    school.save(update_fields=["settings", "updated_at"])

    pulse(wf_run, "seed_data")

    # Tenant-scoped creation: schema mode uses tenant_context(client); RLS mode pins
    # app.current_school_id to the new school so FORCE'd WITH CHECK clauses pass.
    with _optional_tenant_context(tenant_client), rls_school(school.id):
        # Heal any COLUMN drift (e.g. academics ``school_id``) BEFORE the first
        # tenant-scoped seed query. The provision-time ``migrate`` above only fixes
        # drift that ``django_migrations`` still records as unapplied; when a heal
        # migration is recorded-applied yet its column never physically landed,
        # ``migrate`` is a no-op and the seed_data step 500s with "column ... does
        # not exist" on every attempt — so the flight-deck Requeue card loops
        # forever. These introspection-based repairs are idempotent (a cheap no-op
        # on a healthy schema) and are the one thing that lets a requeue actually
        # REPAIR that failure. Best-effort: a repair error is logged, then the seed
        # proceeds and fails loudly as before if a column is genuinely unrecoverable.
        try:
            from apps.schools.tenant_schema_guard import run_tenant_column_repairs
            from apps.tenancy.boundary_core_guard import boundary_bypass

            with boundary_bypass(reason="tenant-provision-column-repair"):
                repaired = run_tenant_column_repairs()
            if any(repaired.values()):
                logger.warning(
                    "Provision column-repair healed drift for school %s: %s",
                    school_id,
                    {k: v for k, v in repaired.items() if v},
                )
        except (ImportError, DatabaseError, OSError, RuntimeError, TypeError, ValueError):
            logger.exception(
                "Provision column-repair raised for school %s (continuing to seed)",
                school_id,
            )

        # Track critical seed-step failures. Sub-steps deliberately never abort the
        # whole provision (the school is already active from Phase A), but if a
        # CRITICAL step fails we must NOT mark phase_b_complete — otherwise a
        # half-seeded tenant (no terms / subjects / classrooms / ComplianceProfile)
        # goes live and is never re-seeded. Leaving the flag unset routes it into
        # the existing resume path (provisioning_needs_resume → reconcile/requeue).
        phase_b_failed_steps: list[str] = []
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

            approved = EducationSystemProfile.objects.filter(  # tenant-isolation-allow: celery-platform-provisioning-beat-cross-tenant
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
        # Exactly ONE active year per school. AcademicYear has no single-active DB
        # constraint, and this seed can legitimately mint a second year (the name is
        # derived from ``start_month``, so an academic-calendar config change between
        # a failed drive and its resume produces a DIFFERENT name -> a NEW row, also
        # is_active=True). Two active years make every ``.get(is_active=True)``
        # caller raise MultipleObjectsReturned — a 500 across the academic surfaces,
        # caused by the repair. Enforce the invariant here rather than trusting
        # ``defaults``, which get_or_create IGNORES on an existing row.
        AcademicYear.objects.filter(school=school, is_active=True).exclude(
            pk=ay.pk
        ).update(is_active=False)
        if not ay.is_active:
            # tenant-isolation-allow: provisioning-activate-year-by-pk-resolved-school-scoped-above
            AcademicYear.objects.filter(pk=ay.pk).update(is_active=True)
            ay.refresh_from_db(fields=["is_active"])
        # Seed terms idempotently — independent of whether the AcademicYear was
        # just created. A prior provision may have created the year then died
        # before terms; Term.get_or_create makes a requeue safely backfill them
        # (the old ``if created:`` gate left such years permanently term-less).
        try:
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
            # The year MUST end up with an active term. ``is_active`` sits in
            # ``defaults``, which get_or_create IGNORES when the row already
            # exists — so a resume over terms seeded by an earlier partial drive
            # (or by the structure/blueprint seeders, which don't set it) leaves
            # the year with NO active term. That is not cosmetic: the teacher
            # marks-entry surface resolves the current term and 403s without one,
            # so grade entry is dead for the year — created by the repair.
            if not Term.objects.filter(
                school=school, academic_year=ay, is_active=True
            ).exists():
                first_term = (
                    Term.objects.filter(school=school, academic_year=ay)
                    .order_by("position", "start_date", "id")
                    .first()
                )
                if first_term is not None:
                    # tenant-isolation-allow: provisioning-activate-term-by-pk-resolved-school-scoped-above
                    Term.objects.filter(pk=first_term.pk).update(is_active=True)
                    logger.info(
                        "Activated term %s for school %s (year had no active term)",
                        first_term.pk,
                        school_id,
                    )
        except (DatabaseError, IntegrityError, ValueError, TypeError):
            # One seed sub-step must never abort the whole provision: the school
            # is already active (Phase A) and missing terms are recoverable.
            logger.exception("Term seeding failed for school %s", school_id)
            phase_b_failed_steps.append("terms")
        # The event must report what HAPPENED, not what was attempted. It used to
        # be recorded unconditionally outside this guard, so a failed term seed
        # still emitted SUCCESS carrying the INTENDED term_count — and the owner's
        # progress strip keys its "Creating your academic year" tick off exactly
        # this event type (provisioning_progress.EXTENDED_PROVISION_STEP_SPECS),
        # where event-presence outranks the parent run state. Net effect: a green
        # tick on a step that failed, on a tenant with no terms.
        _terms_failed = "terms" in phase_b_failed_steps
        if _terms_failed:
            logger.warning(
                "Academic year/term seeding incomplete for school %s", school_id
            )
        else:
            logger.info(
                "Seeded academic year and %s terms for school %s", term_count, school_id
            )
        _record_school_event(
            school,
            event_type="ACADEMIC_YEAR_READY",
            status="FAILED" if _terms_failed else "SUCCESS",
            message=(
                "Academic year and terms could not be prepared."
                if _terms_failed
                else "Academic year and terms prepared."
            ),
            payload={
                "academic_year": ay.name,
                "created": bool(created),
                # Report what is actually in the DB, not the intended count.
                "term_count": int(
                    Term.objects.filter(school=school, academic_year=ay).count()
                ),
                "intended_term_count": int(term_count),
                "failed": _terms_failed,
            },
        )

        try:
            from apps.academics.structure_provisioning import (
                provision_academic_structure_for_school,
            )

            school_settings = getattr(school, "settings", None) or {}
            raw_types = ""
            if isinstance(school_settings, dict):
                raw_types = str(
                    school_settings.get("school_type")
                    or school_settings.get("school_type_raw")
                    or ""
                ).strip()
            school_type_codes = [
                t.strip()
                for t in raw_types.replace(",", "|").split("|")
                if t.strip()
            ]
            structure_payload = provision_academic_structure_for_school(
                school,
                school_type_codes=school_type_codes or None,
                academic_year=ay,
            )
            try:
                from apps.policies.grading_nuance_templates import (
                    sync_grading_nuance_from_policy,
                )

                sync_grading_nuance_from_policy(school)
            except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
                logger.debug(
                    "Grading nuance sync skipped during provisioning for %s",
                    school_id,
                )
            _record_school_event(
                school,
                event_type="ACADEMIC_STRUCTURE_READY",
                status="SUCCESS",
                message="Academic structure nodes provisioned from country pack.",
                payload=structure_payload,
            )
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            DatabaseError,
        ):
            logger.exception(
                "Academic structure provisioning failed for school %s", school_id
            )
            phase_b_failed_steps.append("academic_structure")

        # Optional: seed default subjects. Subject name is unique per school (school_id, name).
        #
        # Deliberately NOT gated on ``if not Subject.objects.filter(school).exists()``.
        # That gate made the seed all-or-nothing: a drive killed partway (the
        # tenant_schema migrate is the usual casualty) leaves, say, 3 of 15 subjects
        # written, and every subsequent resume then sees "subjects exist" and skips —
        # so the tenant is stuck with a partial subject list FOREVER, and the step
        # reports success each time. The loop below is pure get_or_create, so running
        # it unconditionally is idempotent and completes a partial seed.
        #
        # Re-seeding cannot resurrect subjects a school deliberately deleted: this
        # whole Phase B block only runs while ``phase_b_complete`` is unset, and
        # ``_do_provision`` returns early on a settled school (see its is_active
        # guard). A school that finished provisioning never reaches here again.
        subject_created = 0
        try:
            subject_seed = []
            if profile:
                subject_seed = profile.normalized_subject_seed()
            if not subject_seed:
                # Last-resort fallback (no resolved profile / empty seed). Delegate
                # to the engine's language-aware helper instead of a hardcoded list
                # so an English-medium school never gets French as a core subject
                # (the old fallback hardcoded Math/English/French/Science for every
                # region). Derive language from the school, falling back to the
                # FR/EN sub-system marker when default_language is unset.
                from apps.siteconfig.education_profile_engine import (
                    _default_subject_seed,
                )

                fallback_lang = (getattr(school, "default_language", "") or "").strip()
                if not fallback_lang:
                    sub_system = (getattr(school, "sub_system", "") or "").upper()
                    fallback_lang = "fr" if sub_system == "FR" else "en"
                subject_seed = _default_subject_seed(fallback_lang)
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
            logger.info(
                "Seeded default subjects for school %s (%s new)",
                school_id,
                subject_created,
            )
        except (DatabaseError, IntegrityError, ValueError, TypeError):
            logger.exception("Subject seeding failed for school %s", school_id)
            phase_b_failed_steps.append("subjects")
        # Report the OUTCOME, not the attempt — see the ACADEMIC_YEAR_READY note
        # above. This event drives the owner's "Setting up subjects" tick.
        _subjects_failed = "subjects" in phase_b_failed_steps
        _record_school_event(
            school,
            event_type="SUBJECTS_READY",
            status="FAILED" if _subjects_failed else "SUCCESS",
            message=(
                "Default subjects could not be prepared."
                if _subjects_failed
                else "Default subjects prepared."
            ),
            payload={
                "subjects_created": int(subject_created),
                # Ground truth: what the tenant actually has, not what we tried.
                "subjects_total": int(Subject.objects.filter(school=school).count()),
                "failed": _subjects_failed,
            },
        )

        # 10X local-first: seed the per-school grading scale (+ a matching school-wide
        # default AssessmentWeights) from the school's COUNTRY, so a new school lands with
        # a configured scale instead of "none configured" until an admin runs the wizard.
        # Idempotent + never overrides an existing admin/wizard default. Non-blocking.
        try:
            from apps.evals.grading_provisioning import ensure_local_grading_scale

            grading_result = ensure_local_grading_scale(school, academic_year=ay)
            # ensure_local_grading_scale contractually NEVER raises — it logs and
            # returns {"ok": False, "error": ...}. So the except below could only
            # ever fire on ImportError, and a real grading-scale failure sailed
            # through as SUCCESS (carrying ok=False in its own payload) without
            # ever landing in phase_b_failed_steps. That let phase_b_complete=True
            # on a tenant with no grading scale — which then reads as "settled",
            # so no reconcile or watchdog would ever re-seed it. A school with no
            # grading scale cannot publish a grade. Inspect the returned contract.
            _grading_ok = bool((grading_result or {}).get("ok"))
            if not _grading_ok:
                logger.error(
                    "Grading scale provisioning returned not-ok for school %s: %s",
                    school_id,
                    (grading_result or {}).get("error"),
                )
                phase_b_failed_steps.append("grading_scale")
            _record_school_event(
                school,
                event_type="GRADING_SCALE_READY",
                status="SUCCESS" if _grading_ok else "FAILED",
                message=(
                    "Local grading scale provisioned."
                    if _grading_ok
                    else "Local grading scale could not be provisioned."
                ),
                payload=grading_result,
            )
        except (DatabaseError, IntegrityError, ValueError, TypeError, ImportError):
            logger.exception("Grading scale provisioning failed for school %s", school_id)
            phase_b_failed_steps.append("grading_scale")

        try:
            from apps.metadata.country_eav_catalog import seed_country_eav_definitions

            eav_result = seed_country_eav_definitions(
                school=school,
                country_code=getattr(school, "country_code", None),
            )
            _record_school_event(
                school,
                event_type="EAV_CATALOG_READY",
                status="SUCCESS",
                message="Country identity field catalog provisioned.",
                payload=eav_result,
            )
        except (DatabaseError, IntegrityError, ValueError, TypeError, ImportError):
            logger.exception("EAV catalog provisioning failed for school %s", school_id)
            phase_b_failed_steps.append("eav_catalog")

        # W1-5: Seed 1–3 default classrooms from profile (or generic names).
        # Wrapped so a classroom/department seeding error cannot abort the whole
        # provision (the school is already active in Phase A).
        try:
            from apps.academics.models import Classroom

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
            # Reuse the single canonical "General" department (the academic-
            # structure provisioner above ensures it) instead of minting a second
            # one — that double-create left every new tenant with two "General"
            # departments. dept_code stays the classroom-code namespace prefix so
            # already-seeded tenants don't regenerate duplicate classrooms.
            from apps.academics.structure_provisioning import ensure_general_department

            dept_code = f"{school.slug}-GEN" if school.slug else f"{school.id.hex[:8]}-GEN"
            department = ensure_general_department(school)
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
        except (DatabaseError, IntegrityError, ValueError, TypeError):
            logger.exception("Classroom seeding failed for school %s", school_id)
            phase_b_failed_steps.append("classrooms")

        # Seed the teaching grid — the classroom x subject x term SubjectAssignment
        # rows the school day actually runs on. Provisioning used to mark a tenant
        # COMPLETED with ZERO of these, which made a "successful" provision
        # unusable: teachers reach classrooms via
        # TeacherAssignment -> subject_assignment__classroom, and marks point at a
        # SubjectAssignment. With none, a day-1 teacher opened the classroom
        # dropdown and saw nothing, and no grade could be entered — silently, as an
        # empty dropdown rather than an error. The same step seeds the default
        # Specialty, whose absence also made FeePlan (non-null specialty FK)
        # uncreatable, so the fee task reported SUCCESS with {"status": "no_plans"}.
        # Runs after subjects AND classrooms; idempotent, so a resume completes a
        # partial grid.
        try:
            from apps.academics.structure_provisioning import (
                provision_teaching_grid_for_school,
            )

            grid_summary = provision_teaching_grid_for_school(school, academic_year=ay)
            _record_school_event(
                school,
                event_type="TEACHING_GRID_READY",
                status="SUCCESS" if not grid_summary.get("skipped") else "INFO",
                message=(
                    "Teaching grid prepared (classes x subjects x terms)."
                    if not grid_summary.get("skipped")
                    else "Teaching grid skipped: %s" % grid_summary.get("skipped")
                ),
                payload=grid_summary,
            )
        except (DatabaseError, IntegrityError, ValueError, TypeError, ImportError):
            logger.exception("Teaching grid seeding failed for school %s", school_id)
            phase_b_failed_steps.append("teaching_grid")
            _record_school_event(
                school,
                event_type="TEACHING_GRID_READY",
                status="FAILED",
                message="Teaching grid could not be prepared.",
                payload={"failed": True},
            )

        # Assign default dashboard packs per role (Dashboard Packs revival). Idempotent
        # via (school, role) unique_together; never overwrites an operator's choice. A
        # school with no seeded packs is skipped gracefully (role-home default renders).
        try:
            from apps.siteconfig.dashboard_pack_resolver import (
                assign_default_dashboard_packs,
            )

            dp_summary = assign_default_dashboard_packs(school, apply=True)
            if dp_summary.get("pack_assignments_created") or dp_summary.get(
                "layout_assignments_created"
            ):
                logger.info(
                    "Seeded dashboard pack assignments for school %s: %s",
                    school_id,
                    dp_summary,
                )
        except (DatabaseError, IntegrityError, ValueError, TypeError, ImportError):
            logger.exception(
                "Default dashboard pack assignment failed for school %s", school_id
            )

        # Ensure the tenant schema has an active ComplianceProfile. finance is
        # TENANT_APPS (schema-per-tenant): a fresh schema has zero rows, and
        # Invoice.profile is a PROTECT, non-null FK — without this, the first fee
        # generation dead-ends on an empty-table fallback and raises IntegrityError.
        # Idempotent; never overwrites an operator's profile. Non-fatal.
        try:
            from apps.finance.provisioning_seed import (
                ensure_tenant_compliance_profile,
            )

            cp = ensure_tenant_compliance_profile(school)
            if cp is not None:
                logger.info(
                    "Ensured tenant ComplianceProfile for school %s (profile %s)",
                    school_id,
                    cp.pk,
                )
        except (DatabaseError, IntegrityError, ValueError, TypeError, ImportError):
            logger.exception(
                "Tenant ComplianceProfile seed failed for school %s", school_id
            )
            phase_b_failed_steps.append("compliance_profile")

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

        # Pass 8: ensure a platform billing subscription exists. Historically this
        # was wired only into the entry surfaces (api_create_school / control-plane
        # lifecycle / billing views), so a pure-engine provision (operator
        # create_school, resume sweep) left the tenant with TenantSubscription
        # MISSING + plan_id None until a billing view lazily get-or-created one.
        # Fold it into the canonical engine so every provisioning path is uniform.
        # Idempotent (get-or-create) + best-effort: a billing hiccup must never
        # wedge provisioning or block completion, and the lazy self-heal still
        # backstops it, so this step is deliberately NOT added to
        # phase_b_failed_steps.
        try:
            from apps.billing.services import ensure_subscription_for_school

            _billing_account, _subscription, subscription_created = (
                ensure_subscription_for_school(school)
            )
            if subscription_created:
                _record_school_event(
                    school,
                    event_type="SUBSCRIPTION_SEEDED",
                    status="SUCCESS",
                    message="Platform billing subscription created during provisioning.",
                )
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
                "ensure_subscription_for_school failed during provisioning school=%s",
                school_id,
                exc_info=True,
            )

        if phase_b_failed_steps:
            # A critical step failed. Do NOT mark complete — record the failure and
            # leave the tenant resumable. provisioning_needs_resume() returns True on
            # an unset phase_b_complete, so the stuck-sweep / Tenant-360 Requeue
            # re-runs the idempotent Phase B seed and backfills the missing rows.
            failed = sorted(set(phase_b_failed_steps))
            _merge_provisioning_settings(school, phase_b_failed_steps=failed)
            school.save(update_fields=["settings", "updated_at"])
            logger.warning(
                "Phase B seeding incomplete for school %s; failed=%s "
                "(left resumable, NOT marked complete)",
                school_id,
                failed,
            )
            _record_school_event(
                school,
                event_type="PHASE_B_INCOMPLETE",
                status="WARNING",
                message="Provisioning seeding partially failed; queued for resume.",
                payload={"failed_steps": failed},
            )
        else:
            _merge_provisioning_settings(
                school, phase_b_complete=True, phase_b_failed_steps=[]
            )
            school.save(update_fields=["settings", "updated_at"])
            _record_school_event(
                school,
                event_type="COMPLETED",
                status="SUCCESS",
                message="Provisioning completed successfully.",
            )
            try:
                from apps.lifecycle.unified_lifecycle import record_unified_transition

                record_unified_transition(
                    school,
                    "live",
                    note="provisioning_phase_b_complete",
                    payload={"phase": "b"},
                )
            except (ImportError, AttributeError, TypeError, ValueError):
                pass
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
    logger.info("School %s provisioning seed pass finished", school_id)

    # Legacy tail: provisioning events for observability (email handled by
    # finalize_tenant_activation → notify_tenant_signup_completed).
    if (contact_email or "").strip():
        recipient_domain = (
            contact_email.split("@", 1)[-1] if "@" in contact_email else ""
        )
        state = ((school.settings or {}).get("signup_notifications") or {})
        try:
            from apps.schools.signup_completion_notifications import (
                signup_completion_was_delivered,
            )

            sent = signup_completion_was_delivered(school)
        except ImportError:
            sent = bool(state.get("completed_delivered_at") or state.get("completed_at"))
        _record_school_event(
            school,
            event_type=EVENT_WELCOME_EMAIL_SENT if sent else EVENT_WELCOME_EMAIL_FAILED,
            status="SUCCESS" if sent else "WARNING",
            message=(
                "Portal-ready email sent."
                if sent
                else "Portal-ready email not confirmed; check signup_notifications state."
            ),
            payload={"recipient_domain": recipient_domain},
        )
        if not sent:
            logger.warning(
                "Portal-ready email not confirmed for school %s",
                school_id,
            )


def reconcile_half_provisioned_tenants(
    *, limit: int = 25, cooldown_minutes: int = 30, dry_run: bool = False
) -> dict:
    """Durable seal: finish tenants left LIVE (Phase A) but with Phase B unfinished.

    Finds schools that are active (owner can sign in) yet never completed Phase B
    — no academic year / terms / subjects / classrooms — and re-drives
    provisioning to finish them. This catches a half-provisioned tenant REGARDLESS
    of whether its original workflow run is stuck, failed, or already gone, which
    the stuck-sweep autopilot (it only fires on an in-flight run) cannot reach.

    Also finishes the HUSK class (second pass below): an ACTIVE school that was
    never provisioned at all, which no other healer can reach.

    Safe by construction:
    - ``provisioning_needs_resume`` demands POSITIVE evidence either way: the
      explicit ``phase_a_complete`` marker, or a PROVABLY absent tenant workspace.
      A legacy school (no provisioning flags, but a real schema behind it) matches
      neither and is never touched — and outside schema mode the workspace probe
      answers "unknowable", which is not absence, so the husk pass is inert there.
    - Bounded to ``limit`` re-drives per tick.
    - Per-school ``cooldown_minutes`` (stamped as ``last_reconcile_at``) so a
      permanently-unrepairable tenant is retried at most ~twice/hour, not every
      beat tick.
    - Skips any school with provisioning already in flight (no double-fire).
    - Each re-drive resumes Phase B idempotently (get_or_create everywhere).
    """
    from datetime import datetime, timedelta
    from django.utils import timezone

    from .models import School
    from apps.schools.provisioning_progress import provisioning_needs_resume

    try:
        from apps.schools.tenant_offboarding import provisioning_in_flight
    except ImportError:

        def provisioning_in_flight(_school):
            return False

    now = timezone.now()
    cutoff = now - timedelta(minutes=max(0, cooldown_minutes))
    requeued = 0
    husks_requeued = 0
    skipped_in_flight = 0
    skipped_cooldown = 0

    # Narrow at the DB level to live tenants that ran Phase A (positive JSON key
    # match only — NOT an exclude on phase_b_complete: a `.exclude(... =True)` on a
    # MISSING JSON key drops the row via SQL three-valued logic, i.e. exactly the
    # half-provisioned rows we want). The authoritative phase_b gate is the Python
    # ``provisioning_needs_resume`` re-check below, so this filter is a pure
    # optimization that is always a safe superset.
    # tenant-isolation-allow: platform-operator-provisioning-reconciler-cross-tenant-by-design
    candidates = School.objects.filter(
        is_active=True, settings__provisioning__phase_a_complete=True
    ).order_by("updated_at")

    def _consider(school) -> str:
        """Evaluate one candidate. Returns the verdict, dispatching if due."""
        nonlocal requeued, skipped_in_flight, skipped_cooldown
        # Authoritative gate (handles the phase_b_complete absent/false cases the
        # DB filter deliberately does not).
        if not provisioning_needs_resume(school):
            return "not_needed"
        prov = (getattr(school, "settings", None) or {}).get("provisioning") or {}
        last_raw = str(prov.get("last_reconcile_at") or "").strip()
        if last_raw:
            try:
                last_dt = datetime.fromisoformat(last_raw)
                if timezone.is_naive(last_dt):
                    last_dt = timezone.make_aware(
                        last_dt, timezone.get_default_timezone()
                    )
                if last_dt > cutoff:
                    skipped_cooldown += 1
                    return "cooldown"
            except (ValueError, TypeError):
                pass
        if provisioning_in_flight(school):
            skipped_in_flight += 1
            return "in_flight"
        if dry_run:
            requeued += 1
            return "requeued"
        contact_email = resolve_provisioning_contact_email(school)
        # Stamp the cooldown BEFORE dispatch so a crash mid-dispatch still backs
        # off the next tick rather than hammering the same school.
        _merge_provisioning_settings(school, last_reconcile_at=now.isoformat())
        school.save(update_fields=["settings", "updated_at"])
        dispatch_provision_school(str(school.id), contact_email=contact_email)
        requeued += 1
        logger.info(
            "reconcile_half_provisioned_tenants requeued school_id=%s", school.id
        )
        return "requeued"

    for school in candidates.iterator():
        if requeued >= limit:
            break
        _consider(school)

    # Second pass — the HUSK class: active, but carrying NO Phase A marker.
    #
    # ``School.is_active`` defaults to True, so a row created outside the pipeline
    # lands "live" with no workspace behind it and 500s on every request. The
    # filter above cannot see it (no marker to match) and NO other healer covers
    # it: the watchdog sweep keys off a WorkflowRun, and a husk has none.
    #
    # This is not a hypothetical class with one unlucky member — the migration
    # ``schools/0012_seed_default_gilead_school`` MANUFACTURES one on every
    # deployment (a single-tenant-era leftover that seeds ``gilead-school``
    # active-but-unprovisioned), so every database the platform has ever created
    # carries one. It is a get_or_create, so deleting the row is not a fix either;
    # provisioning it is.
    #
    # This pass is a bounded PYTHON scan, not a SQL filter, on purpose: "JSON key
    # absent" is not reliably expressible across both backends — an .exclude() on
    # a missing key drops the row via three-valued logic (the same trap the
    # comment above documents for phase_b_complete), so the SQL would silently
    # match nothing. It stays cheap because ``provisioning_needs_resume``
    # short-circuits on the marker for every normally-provisioned school, and only
    # a marker-less active school pays the (cached, tri-state) workspace probe —
    # which answers None outside schema mode, so this whole pass is inert locally.
    if requeued < limit:
        scan_cap = max(limit * 20, 100)  # magic-number-allow: husk-scan-row-cap
        # NOTE: deliberately NOT `.exclude(settings__provisioning__phase_a_complete=True)`
        # — that is the very three-valued-logic trap described above and would drop
        # every husk (missing key -> NULL -> excluded), matching nothing at all. The
        # marker check is done in Python below, where a missing key is just falsy.
        # tenant-isolation-allow: platform-operator-provisioning-reconciler-cross-tenant-by-design
        husk_candidates = School.objects.filter(is_active=True).order_by("updated_at")[
            :scan_cap
        ]
        for school in husk_candidates.iterator():
            if requeued >= limit:
                break
            prov = (getattr(school, "settings", None) or {}).get("provisioning") or {}
            if prov.get("phase_a_complete"):
                continue  # owned by the first pass; never double-consider
            if _consider(school) == "requeued":
                husks_requeued += 1
                logger.warning(
                    "reconcile_half_provisioned_tenants: requeued NEVER-PROVISIONED "
                    "active school school_id=%s slug=%s (no tenant workspace behind it)",
                    school.id,
                    getattr(school, "slug", ""),
                )

    result = {
        "requeued": requeued,
        "husks_requeued": husks_requeued,
        "skipped_in_flight": skipped_in_flight,
        "skipped_cooldown": skipped_cooldown,
        "dry_run": dry_run,
    }
    if requeued or skipped_in_flight or skipped_cooldown:
        logger.info("reconcile_half_provisioned_tenants summary=%s", result)
    return result


def detect_tenant_table_drift_scan() -> dict:
    """Read-only sweep: flag tenant schemas missing expected tenant-app tables.

    Detection only — the ensure-table heal migrations repair on the next deploy;
    this surfaces the rarer "fake-applied CreateModel" drift between deploys via
    log(ERROR) + a best-effort operator-inbox email so it never goes unnoticed.
    Never raises (a monitoring sweep must not crash the beat).
    """
    try:
        from apps.schools.tenant_schema_guard import scan_all_tenant_schemas

        report = scan_all_tenant_schemas()
    except (DatabaseError, ImportError, OSError, RuntimeError, ValueError) as exc:
        logger.exception("detect_tenant_table_drift_scan: scan failed: %s", exc)
        return {"ok": False, "error": str(exc)}

    drifted = {
        schema: [table for _app, _model, table in rows]
        for schema, rows in report.items()
        if rows
    }
    summary = {
        "ok": True,
        "schemas_checked": len(report),
        "drifted_schemas": len(drifted),
        "drift": drifted,
    }
    if drifted:
        logger.error("detect_tenant_table_drift: tenant table drift found: %s", drifted)
        _alert_operator_table_drift(drifted)
    else:
        logger.info(
            "detect_tenant_table_drift: %s schema(s) checked, no drift", len(report)
        )
    return summary


def _alert_operator_table_drift(drifted: dict) -> None:
    """Best-effort operator-inbox email for detected table drift. Never raises."""
    try:
        from django.core.mail import send_mail

        from apps.platform_runtime.platform_email_matrix import resolve_operator_inbox

        recipients = resolve_operator_inbox({})
        if not recipients:
            return
        lines = [
            f"  [{schema}] missing: {', '.join(tables)}"
            for schema, tables in sorted(drifted.items())
        ]
        body = (
            "Tenant-schema table drift detected (recorded-applied migration but the "
            "table is missing — see `manage.py detect_tenant_table_drift`).\n\n"
            + "\n".join(lines)
            + "\n\nThe ensure-table heal migrations repair this on the next deploy; "
            "trigger a deploy (or run migrate_schemas --tenant) to clear it."
        )
        send_mail(
            subject=f"[RunMyCampus] Tenant table drift: {len(drifted)} schema(s)",
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=recipients,
            fail_silently=True,
        )
    except (DatabaseError, ImportError, OSError, RuntimeError, ValueError, TypeError):
        logger.exception("_alert_operator_table_drift: could not send operator alert")


# Celery task (optional)
try:
    from celery import shared_task

    @shared_task(bind=True, max_retries=3)
    def provision_school_task(self, school_id: str, contact_email: str = "", **kwargs):
        try:
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
            try:
                from apps.schools.models import School

                school = School.objects.filter(id=school_id).first()
                if school:
                    _emit_provisioning_failed_notification(
                        school, contact_email, error=str(exc)
                    )
            except (ImportError, AttributeError, TypeError, ValueError):
                pass
            raise self.retry(exc=exc)

    @shared_task(name="schools.purge_tenant_media_task")
    def purge_tenant_media_task(school_slug: str, manifest: dict | None = None) -> dict:
        from apps.schools.tenant_offboarding import cleanup_tenant_media

        return cleanup_tenant_media(school_slug, manifest)

    from apps.platform_runtime.workflow_tracker import track_workflow

    @shared_task(name="schools.run_scheduled_tenant_purges")
    @track_workflow(
        "tenant_school_offboard_purge",
        steps=("scan", "purge", "notify"),
        expected_duration_seconds=600,  # magic-number-allow: workflow-expected-duration-seconds
        email_on_failure=True,
    )
    def run_scheduled_tenant_purges_task(*, dry_run: bool = False, limit: int = 10) -> dict:
        from apps.schools.tenant_offboarding import run_scheduled_purges

        return run_scheduled_purges(actor=None, dry_run=dry_run, limit=limit)

    provision_school_task.rmc_workflow_explicit = True

    @shared_task(name="schools.reconcile_half_provisioned_tenants")
    def reconcile_half_provisioned_tenants_task(
        *, limit: int = 25, cooldown_minutes: int = 30, dry_run: bool = False
    ) -> dict:
        """Beat entry point — completes Phase B on any half-provisioned tenant."""
        return reconcile_half_provisioned_tenants(
            limit=limit, cooldown_minutes=cooldown_minutes, dry_run=dry_run
        )

    @shared_task(name="schools.resume_stuck_provisions")
    def resume_stuck_provisions_task(*, limit: int = 5) -> dict:
        """Beat entry point — resume provisions whose drive died mid-run.

        The heartbeat-staleness watchdog is ALSO registered as an in-process
        periodic job that ticks off ``/health/``. That path covers only the
        broker-less topology: ``periodic.inprocess_scheduler_enabled()`` is
        ``auto`` by default, i.e. enabled ONLY while ``CELERY_BROKER_URL`` is
        unset, so it stands down the moment a worker + beat are provisioned. The
        hourly ``scheduled_job_health_monitor`` does not cover the hand-off
        either — its ``auto_recovery_enabled()`` mirrors the same broker check,
        and ``select_recovery_candidates`` deliberately skips ``auto_eligible``
        jobs. Without this beat entry the watchdog would therefore run in
        exactly the topology that needs it least, and never in production.

        Limit is per tick and deliberately small: a resume re-drives a full
        tenant migrate, so a burst would pile heavy work onto one worker.
        """
        from apps.schools.provision_watchdog import resume_stuck_provisions

        return resume_stuck_provisions(limit=limit, reason="beat-sweep")

    @shared_task(name="schools.detect_tenant_table_drift")
    def detect_tenant_table_drift_task() -> dict:
        """Beat entry point — read-only sweep for tenant schemas missing tables."""
        return detect_tenant_table_drift_scan()

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

    def reconcile_half_provisioned_tenants_task(*args, **kwargs):
        return reconcile_half_provisioned_tenants(*args, **kwargs)

    def detect_tenant_table_drift_task(*args, **kwargs):
        return detect_tenant_table_drift_scan()
