"""
TenantStrategy: SCHEMA (django-tenants) vs RLS (shared schema + app.current_school_id).
Aligns with TENANCY_MODE in settings when set; otherwise derived from USE_DJANGO_TENANTS.
"""
from enum import Enum
from django.conf import settings


class TenantStrategy(str, Enum):
    SCHEMA_PER_TENANT = "schema"
    SHARED_SCHEMA = "shared"


def get_tenant_strategy() -> TenantStrategy:
    """Return the active tenancy strategy (schema-per-tenant or shared-schema RLS)."""
    mode = getattr(settings, "TENANCY_MODE", None)
    if mode == "SCHEMA":
        return TenantStrategy.SCHEMA_PER_TENANT
    if mode == "RLS":
        return TenantStrategy.SHARED_SCHEMA
    # Backward compatibility: derive from USE_DJANGO_TENANTS
    use_tenants = getattr(settings, "USE_DJANGO_TENANTS", False)
    return TenantStrategy.SCHEMA_PER_TENANT if use_tenants else TenantStrategy.SHARED_SCHEMA
