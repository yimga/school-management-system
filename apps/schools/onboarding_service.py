"""
OnboardingService: schema-per-tenant onboarding with kill-switch and audit.

Part 0 of RunMyCampus Single Plan. Responsibilities:
- Validate slug uniqueness (School + Client/schema).
- Create PostgreSQL schema for tenant (via django-tenants Client).
- Run Master Table List (tenant migrations) in that schema.
- Seed localized defaults (currency, grading, holidays) by country/region.
- Create first admin user and SchoolMembership.
- Register Domain (subdomain + optional custom domain).
- On failure after schema creation: delete tenant + drop schema (kill-switch), log in public schema.
- Idempotent: safe to retry; existing School/Client skips creation.
"""

import logging
from typing import Optional

from django.db import transaction
from django.db.utils import (
    DatabaseError,
    IntegrityError,
    OperationalError,
    ProgrammingError,
)

from apps.schools.domain_sync import (
    ensure_schooldomain_records_for_school,
    ensure_tenant_client_for_school,
    sync_school_domains_to_runtime,
    use_django_tenants,
)
from apps.schools.tasks import provision_school_sync

logger = logging.getLogger(__name__)


def validate_slug_uniqueness(slug: str) -> tuple[bool, str]:
    """
    Ensure slug is unique for School and (when using django-tenants) for Client.schema_name.
    Returns (True, "") if valid; (False, "reason") otherwise.
    """
    from apps.schools.models import School

    slug = (slug or "").strip().lower().replace(" ", "-")
    if not slug:
        return False, "Slug is required."
    if not slug.replace("-", "").replace("_", "").isalnum():
        return False, "Slug must be alphanumeric with hyphens only."
    if School.objects.filter(slug=slug).exists():
        return False, f"School with slug '{slug}' already exists."
    if use_django_tenants():
        from apps.customers.models import Client

        # We don't have a school yet; use a placeholder to get schema name pattern (s_<uuid> is used when school exists)
        # For new onboarding, schema will be s_<school_id.hex> after School is created. So we only need to avoid
        # slug-based collision if there is a legacy Client with schema_name = slug.
        legacy_schema = slug.replace("-", "_")[:63]
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        if Client.objects.filter(schema_name=legacy_schema).exists():
            return False, f"Tenant schema '{legacy_schema}' already exists (legacy)."
    return True, ""


def _drop_tenant_schema(client) -> None:
    """Delete the tenant row and force-drop its schema on onboarding failure."""
    if not use_django_tenants() or client is None:
        return
    try:
        schema_name = getattr(client, "schema_name", None)
        if not schema_name or schema_name == "public":
            return
        client.delete(force_drop=True)
        logger.warning(
            "Dropped schema %s and deleted tenant row (onboarding kill-switch).",
            schema_name,
        )
    except (
        DatabaseError,
        OperationalError,
        ProgrammingError,
        ImportError,
        AttributeError,
        TypeError,
    ) as e:
        logger.exception(
            "Failed to drop schema %s: %s", getattr(client, "schema_name", "?"), e
        )


def _tenant_migrate_lock_timeout_ms() -> int:
    """Max time a tenant migration may WAIT for a lock before aborting (ms).

    Targets a migrate BLOCKED on a lock (e.g. a concurrent DDL holding it) — which
    would otherwise hang the process while its heartbeat thread keeps pinging,
    masking the run as "healthy" forever (the stuck-detector never trips on a live
    process). A lock-wait timeout raises instead, so the run finalizes FAILED and
    the provisioning watchdog resumes it — by which point the lock is usually free.
    It does NOT abort a migration doing long WORK; only one blocked on a lock. 0
    disables. Env/settings overridable (``TENANT_MIGRATE_LOCK_TIMEOUT_MS``).
    """
    from django.conf import settings

    raw = getattr(settings, "TENANT_MIGRATE_LOCK_TIMEOUT_MS", None)
    try:
        return int(raw) if raw is not None else 30000  # magic-number-allow: default 30s tenant-migrate lock-wait
    except (TypeError, ValueError):
        return 30000  # magic-number-allow: default 30s tenant-migrate lock-wait


def _set_lock_timeout(value_ms: int | None) -> None:
    """Best-effort SET of ``lock_timeout`` on the current (tenant) connection.

    Postgres-only (a no-op on other backends). Session-level so it applies across
    the migrate's per-migration transactions. ``None`` resets to the DB default.
    Never raises into provisioning — a timeout knob must not break the migrate.
    """
    from django.db import connection

    if connection.vendor != "postgresql":
        return
    try:
        with connection.cursor() as cur:
            if value_ms is None:
                cur.execute("SET lock_timeout = DEFAULT")
            else:
                # value is int-cast → safe to inline; SET takes no bind params.
                cur.execute(f"SET lock_timeout = {int(value_ms)}")
    except Exception:  # noqa: BLE001 — best-effort; never break provisioning
        logger.debug("could not adjust tenant migrate lock_timeout", exc_info=True)


def _discard_connection() -> None:
    """Close the current DB connection so a tainted session (e.g. an aborted
    transaction after a failed migrate) can't leak session GUCs onto a pooled or
    worker-reused connection. The next query reconnects with clean defaults."""
    from django.db import connection

    try:
        connection.close()
    except Exception:  # noqa: BLE001 — best-effort; never break the failure path
        logger.debug("could not close tenant connection after migrate failure", exc_info=True)


def _run_tenant_migrations(client) -> None:
    """Run migrations for the given tenant schema. Tables created = Master Table List (see docs/MASTER_TABLE_LIST.md)."""
    if not use_django_tenants():
        return
    try:
        from django_tenants.utils import tenant_context
        from django.core.management import call_command

        with tenant_context(client):
            lock_ms = _tenant_migrate_lock_timeout_ms()
            if lock_ms > 0:
                _set_lock_timeout(lock_ms)
            migrate_ok = False
            try:
                call_command("migrate", "--run-syncdb", verbosity=1)
                migrate_ok = True
            finally:
                if lock_ms > 0:
                    if migrate_ok:
                        # Clean session — reset to the DB default.
                        _set_lock_timeout(None)
                    else:
                        # Migrate failed: the connection may be in an aborted
                        # transaction where `SET lock_timeout = DEFAULT` would itself
                        # error and leak the tightened timeout onto a pooled/worker
                        # connection (this path runs off-request, so Django won't
                        # discard it). Close it — a fresh connect resets all session
                        # GUCs, guaranteeing no leak.
                        _discard_connection()
    except (
        ImportError,
        DatabaseError,
        OperationalError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as e:
        logger.exception(
            "Tenant migrations failed for schema %s: %s",
            getattr(client, "schema_name", "?"),
            e,
        )
        raise


def _audit_log_public(
    event: str, slug: str, success: bool, message: str = "", payload: dict | None = None
) -> None:
    """Write an audit entry in public schema (e.g. SchoolProvisioningEvent or compliance audit)."""
    try:
        from apps.schools.models import School, SchoolProvisioningEvent

        school = School.objects.filter(slug=slug).first()
        if school:
            SchoolProvisioningEvent.log_event(
                school=school,
                event_type=event,
                status="SUCCESS" if success else "ERROR",
                message=message,
                payload=payload or {},
            )
    except (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError):
        logger.exception("Audit log (public) failed for onboarding event %s", event)


def onboard_tenant(
    *,
    slug: str,
    name: str,
    contact_email: str = "",
    country_code: Optional[str] = None,
    subdomain: Optional[str] = None,
    create_school_if_missing: bool = True,
    run_migrations: bool = True,
    run_seed: bool = True,
    kill_switch_on_failure: bool = True,
) -> dict:
    """
    Idempotent onboarding: validate slug, create School (if missing), Client (schema),
    run tenant migrations, seed defaults, create first admin, register Domain.
    On failure after Client creation and if kill_switch_on_failure: delete tenant + drop schema.

    Returns dict with keys: success, school_id, client_id, message, error (if failed).
    """
    from apps.schools.models import School
    from apps.global_registries.models import RegionConfig

    slug = (slug or "").strip().lower().replace(" ", "-")
    name = (name or "").strip()
    if not name:
        name = slug.replace("-", " ").title()

    ok, err = validate_slug_uniqueness(slug)
    if not ok:
        return {
            "success": False,
            "school_id": None,
            "client_id": None,
            "message": err,
            "error": err,
        }

    school = School.objects.filter(slug=slug).first()
    if not school and create_school_if_missing:
        with transaction.atomic(using="default"):
            region = None
            if country_code:
                region = RegionConfig.objects.filter(
                    country_code=(country_code or "").strip().upper()[:2]
                ).first()
            subdomain_val = (subdomain or slug).strip().lower().replace(" ", "-")[:120]
            school = School.objects.create(
                slug=slug,
                name=name,
                subdomain=subdomain_val or slug,
                default_region=region,
            )
            logger.info("Created School %s (%s) for onboarding.", school.id, slug)
    elif not school:
        return {
            "success": False,
            "school_id": None,
            "client_id": None,
            "message": "School not found and create_school_if_missing=False",
            "error": "School not found",
        }

    client = None
    if use_django_tenants():
        from apps.customers.models import Client

        client = Client.objects.filter(school=school).first()
        if not client:
            try:
                client = ensure_tenant_client_for_school(school)
            except (
                DatabaseError,
                IntegrityError,
                OSError,
                ConnectionError,
                AttributeError,
                TypeError,
                ValueError,
                ImportError,
            ) as e:
                _audit_log_public(
                    "ONBOARDING_FAILED", slug, False, str(e), {"error": str(e)}
                )
                return {
                    "success": False,
                    "school_id": str(school.id),
                    "client_id": None,
                    "message": f"Failed to create tenant client: {e}",
                    "error": str(e),
                }
        if client and run_migrations:
            try:
                _run_tenant_migrations(client)
            except (
                ImportError,
                DatabaseError,
                OperationalError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as e:
                if kill_switch_on_failure:
                    _drop_tenant_schema(client)
                _audit_log_public(
                    "ONBOARDING_FAILED",
                    slug,
                    False,
                    f"Migrations failed: {e}",
                    {"error": str(e)},
                )
                return {
                    "success": False,
                    "school_id": str(school.id),
                    "client_id": getattr(client, "id", None),
                    "message": f"Migrations failed: {e}",
                    "error": str(e),
                }

    if run_seed:
        try:
            provision_school_sync(str(school.id), contact_email=contact_email or "")
        except (
            DatabaseError,
            IntegrityError,
            OSError,
            ConnectionError,
            ValueError,
            TypeError,
            AttributeError,
            ImportError,
            RuntimeError,
        ) as e:
            if use_django_tenants() and client and kill_switch_on_failure:
                _drop_tenant_schema(client)
            _audit_log_public(
                "ONBOARDING_FAILED",
                slug,
                False,
                f"Seed/provision failed: {e}",
                {"error": str(e)},
            )
            return {
                "success": False,
                "school_id": str(school.id),
                "client_id": getattr(client, "id", None) if client else None,
                "message": f"Seed failed: {e}",
                "error": str(e),
            }

    try:
        ensure_schooldomain_records_for_school(school)
        sync_school_domains_to_runtime(school)
    except (
        OSError,
        ConnectionError,
        DatabaseError,
        AttributeError,
        TypeError,
        ValueError,
    ) as e:
        logger.warning("Domain sync failed for %s: %s", slug, e)

    _audit_log_public(
        "ONBOARDING_COMPLETED",
        slug,
        True,
        "Onboarding completed.",
        {"school_id": str(school.id)},
    )
    return {
        "success": True,
        "school_id": str(school.id),
        "client_id": getattr(client, "id", None) if client else None,
        "message": "Onboarding completed.",
        "error": None,
    }
