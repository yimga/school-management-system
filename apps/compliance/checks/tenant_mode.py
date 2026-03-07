"""
Django system checks for tenancy mode consistency.
Fails fast if production is misconfigured (USE_DJANGO_TENANTS vs DB engine).
"""
from django.conf import settings
from django.core.checks import Error, register


@register()
def check_tenant_mode_consistency(app_configs, **kwargs):
    errors = []
    use_tenants = getattr(settings, "USE_DJANGO_TENANTS", False)
    default_engine = (settings.DATABASES.get("default") or {}).get("ENGINE", "")

    if use_tenants:
        # django_tenants uses ENGINE "django_tenants.postgresql_backend" (does not end with "postgresql")
        is_postgres = (
            default_engine.endswith("postgresql")
            or "django_tenants.postgresql_backend" in default_engine
        )
        if not is_postgres:
            errors.append(
                Error(
                    "USE_DJANGO_TENANTS is True but default database engine is not PostgreSQL.",
                    hint="Schema-per-tenant requires PostgreSQL. Set USE_DJANGO_TENANTS=0 for SQLite or use a PostgreSQL DATABASE_URL.",
                    id="compliance.E001",
                )
            )
        elif "django_tenants.postgresql_backend" not in default_engine:
            errors.append(
                Error(
                    "USE_DJANGO_TENANTS is True but database ENGINE is not django_tenants.postgresql_backend.",
                    hint="Set DATABASES['default']['ENGINE'] to 'django_tenants.postgresql_backend' when using schema-per-tenant, or set USE_DJANGO_TENANTS=0 for single-schema mode.",
                    id="compliance.E002",
                )
            )

    return errors
