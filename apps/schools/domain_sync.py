"""
Domain synchronization helpers.

Goal: keep SchoolDomain, legacy School.custom_domain fields, and django-tenants
customers.Domain records consistent so verification implies routability.
"""

import logging
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.db.utils import DatabaseError
from django.utils import timezone

logger = logging.getLogger(__name__)


def use_django_tenants() -> bool:
    """Single source of truth for tenant mode across app code."""
    return bool(getattr(settings, "USE_DJANGO_TENANTS", False))


def get_base_domain() -> str:
    """
    Canonical base domain used for subdomain hostnames (e.g. portal links).
    Aligns with host_routing so we never build tenant URLs on *.onrender.com,
    which would cause ERR_SSL_VERSION_OR_CIPHER_MISMATCH (Render does not
    provide wildcard SSL for service subdomains).
    """
    from apps.schools.host_routing import get_canonical_base_domain

    return get_canonical_base_domain()


def normalize_domain(hostname: str) -> str:
    """Normalize hostnames for stable comparisons and unique checks."""
    domain = (hostname or "").strip().lower()
    if ":" in domain:
        domain = domain.split(":", 1)[0].strip().lower()
    return domain.rstrip(".")


def school_subdomain_fqdn(school) -> str:
    """Return `<school-subdomain>.<base-domain>` if both are available."""
    subdomain = (
        (getattr(school, "subdomain", "") or getattr(school, "slug", "") or "")
        .strip()
        .lower()
    )
    base = get_base_domain()
    if not subdomain or not base:
        return ""
    return f"{subdomain}.{base}"


def is_runtime_domain_in_use(domain: str, school=None) -> bool:
    """
    True if domain is already mapped to another school in runtime domain table.
    In non-django-tenants mode, returns False.
    """
    if not use_django_tenants():
        return False
    domain = normalize_domain(domain)
    if not domain:
        return False
    try:
        from apps.customers.models import Domain
    except (ImportError, AttributeError, DatabaseError):
        return False
    qs = Domain.objects.filter(domain=domain)
    if school is not None:
        qs = qs.exclude(tenant__school=school)
    return qs.exists()


def _schema_name_for_school(school) -> str:
    """
    Use UUID-backed schema names to avoid collisions globally.
    Format: s_<uuid-hex>, <= 63 chars (PostgreSQL schema limit).
    """
    sid = getattr(school, "id", None)
    sid_hex = getattr(sid, "hex", "") if sid is not None else ""
    if sid_hex:
        return f"s_{sid_hex}"[:63].lower()
    # Safe fallback for unusual cases
    slug = (getattr(school, "slug", "") or "school").replace("-", "_").strip().lower()
    return f"s_{slug}"[:63] or "s_school"


def ensure_tenant_client_for_school(school):
    """
    Ensure customers.Client exists for school in django-tenants mode.
    Returns Client or None.
    """
    if not use_django_tenants():
        return None
    try:
        from django.db import connection

        if connection.vendor != "postgresql":
            return None
        from apps.customers.models import Client
    except (ImportError, AttributeError, DatabaseError):
        return None

    client = Client.objects.filter(school=school).first()
    if client:
        return client

    schema_name = _schema_name_for_school(school)
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    client = Client.objects.filter(schema_name=schema_name).first()
    if client:
        if not client.school_id:
            client.school = school
            client.save(update_fields=["school"])
        return client

    # Legacy fallback: slug schema names from earlier versions.
    legacy_schema = (
        (getattr(school, "slug", "") or "school").strip().lower().replace("-", "_")
    )[:63]
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    if legacy_schema:
        legacy = Client.objects.filter(schema_name=legacy_schema).first()
        if legacy:
            if not legacy.school_id:
                legacy.school = school
                legacy.save(update_fields=["school"])
            return legacy

    client = Client(
        schema_name=schema_name,
        name=getattr(school, "name", "") or schema_name,
        school=school,
    )
    client.save()
    return client


def _upsert_runtime_domain(*, client, domain: str, is_primary: bool):
    """Create/update customers.Domain safely for this tenant."""
    if not client:
        return None
    domain = normalize_domain(domain)
    if not domain:
        return None
    from apps.customers.models import Domain

    existing = Domain.objects.select_related("tenant").filter(domain=domain).first()
    if existing and existing.tenant_id != client.id:
        raise ValueError(
            f"Domain '{domain}' is already attached to a different tenant."
        )

    if existing:
        updates = []
        if existing.tenant_id != client.id:
            existing.tenant = client
            updates.append("tenant")
        if existing.is_primary != is_primary:
            existing.is_primary = is_primary
            updates.append("is_primary")
        if updates:
            existing.save(update_fields=updates)
        return existing

    if is_primary:
        Domain.objects.filter(tenant=client, is_primary=True).update(is_primary=False)
    return Domain.objects.create(domain=domain, tenant=client, is_primary=is_primary)


def ensure_schooldomain_records_for_school(school):
    """
    Ensure SchoolDomain rows exist for canonical subdomain/custom domain values.
    Does not verify pending custom domains.
    """
    from apps.schools.models import SchoolDomain

    now = timezone.now()
    sub_fqdn = school_subdomain_fqdn(school)
    if sub_fqdn:
        entry, _ = SchoolDomain.objects.get_or_create(
            school=school,
            domain=sub_fqdn,
            defaults={
                "kind": SchoolDomain.Kind.SUBDOMAIN,
                "is_verified": True,
                "verified_at": now,
            },
        )
        needs_update = False
        if entry.kind != SchoolDomain.Kind.SUBDOMAIN:
            entry.kind = SchoolDomain.Kind.SUBDOMAIN
            needs_update = True
        if not entry.is_verified:
            entry.is_verified = True
            entry.verified_at = now
            needs_update = True
        if needs_update:
            entry.save(update_fields=["kind", "is_verified", "verified_at"])

    custom = normalize_domain(getattr(school, "custom_domain", ""))
    if custom and getattr(school, "custom_domain_verified", False):
        entry, _ = SchoolDomain.objects.get_or_create(
            school=school,
            domain=custom,
            defaults={
                "kind": SchoolDomain.Kind.CUSTOM,
                "is_verified": True,
                "verified_at": now,
            },
        )
        needs_update = False
        if entry.kind != SchoolDomain.Kind.CUSTOM:
            entry.kind = SchoolDomain.Kind.CUSTOM
            needs_update = True
        if not entry.is_verified:
            entry.is_verified = True
            entry.verified_at = now
            needs_update = True
        if needs_update:
            entry.save(update_fields=["kind", "is_verified", "verified_at"])


def sync_verified_schooldomain(school_domain, *, prefer_primary: Optional[bool] = None):
    """
    Sync one verified SchoolDomain row into runtime routing tables/fields.
    """
    from apps.schools.models import SchoolDomain

    if not isinstance(school_domain, SchoolDomain):
        return
    if not school_domain.is_verified:
        return

    school = school_domain.school
    domain = normalize_domain(school_domain.domain)
    if not domain:
        return

    update_fields = []
    if school_domain.kind == SchoolDomain.Kind.CUSTOM:
        if school.custom_domain != domain:
            school.custom_domain = domain
            update_fields.append("custom_domain")
        if not school.custom_domain_verified:
            school.custom_domain_verified = True
            update_fields.append("custom_domain_verified")
    if update_fields:
        school.save(update_fields=update_fields + ["updated_at"])

    if not use_django_tenants():
        return

    client = ensure_tenant_client_for_school(school)
    if not client:
        return

    if prefer_primary is None:
        is_primary = school_domain.kind == SchoolDomain.Kind.SUBDOMAIN
    else:
        is_primary = bool(prefer_primary)
    _upsert_runtime_domain(client=client, domain=domain, is_primary=is_primary)


def sync_school_domains_to_runtime(school):
    """
    Ensure domain records exist and route correctly for this school.
    Safe to call repeatedly.
    """
    from apps.schools.models import SchoolDomain

    with transaction.atomic():
        ensure_schooldomain_records_for_school(school)
        for row in SchoolDomain.objects.filter(
            school=school, is_verified=True
        ).order_by("kind", "domain"):
            try:
                sync_verified_schooldomain(row)
            except (
                OSError,
                ConnectionError,
                DatabaseError,
                AttributeError,
                TypeError,
                ValueError,
            ):
                log_exception_with_context(
                    "domain_sync.sync_verified_schooldomain: failed to sync verified domain for school",
                    school_id=school.id,
                    extra={"domain": str(row.domain)},
                )
