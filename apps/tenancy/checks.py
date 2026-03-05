"""
Django system checks: enforce TENANCY_MODE / USE_DJANGO_TENANTS vs middleware and DB engine.
Never run both schema and RLS tenant resolution in the same request path.
"""
from django.conf import settings
from django.core.checks import Error, register


@register()
def tenancy_strategy_checks(app_configs, **kwargs):
    errors = []
    use_tenants = getattr(settings, "USE_DJANGO_TENANTS", False)
    mw = getattr(settings, "MIDDLEWARE", [])
    engine = (settings.DATABASES.get("default") or {}).get("ENGINE", "")

    if use_tenants:
        if not any("TenantMainMiddleware" in m for m in mw):
            errors.append(
                Error(
                    "USE_DJANGO_TENANTS is True but TenantMainMiddleware is missing.",
                    hint="Add django_tenants.middleware.main.TenantMainMiddleware when using schema-per-tenant.",
                    id="tenancy.E001",
                )
            )
        if "django_tenants" not in engine and "postgresql" not in engine:
            errors.append(
                Error(
                    "USE_DJANGO_TENANTS is True but DB engine is not django-tenants PostgreSQL backend.",
                    hint="Set DATABASES['default']['ENGINE'] to 'django_tenants.postgresql_backend' or set USE_DJANGO_TENANTS=0.",
                    id="tenancy.E002",
                )
            )
    else:
        # RLS mode: TenantMainMiddleware must not be present (single schema)
        if any("TenantMainMiddleware" in m for m in mw):
            errors.append(
                Error(
                    "USE_DJANGO_TENANTS is False but TenantMainMiddleware is present.",
                    hint="Remove TenantMainMiddleware for shared-schema (RLS) mode, or set USE_DJANGO_TENANTS=1.",
                    id="tenancy.E003",
                )
            )

    return errors
