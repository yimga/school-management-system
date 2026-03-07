"""
Django system checks: enforce TENANCY_MODE / USE_DJANGO_TENANTS vs middleware and DB engine.
Never run both schema and RLS tenant resolution in the same request path.
"""
from django.conf import settings
from django.core.checks import Error, Warning, register


SCHEMA_REQUIRED_APPS = {
    "apps.registries",
    "apps.billing",
    "apps.student360",
    "apps.metadata.apps.MetadataConfig",
}


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
        installed_apps = set(getattr(settings, "INSTALLED_APPS", []) or [])
        missing_apps = sorted(app for app in SCHEMA_REQUIRED_APPS if app not in installed_apps)
        if missing_apps:
            errors.append(
                Error(
                    "Schema mode is missing required shared apps.",
                    hint="Add the missing platform apps to SHARED_APPS/INSTALLED_APPS: %s" % ", ".join(missing_apps),
                    id="tenancy.E004",
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


@register()
def control_plane_cookie_scope_checks(app_configs, **kwargs):
    warnings = []
    session_domain = str(getattr(settings, "SESSION_COOKIE_DOMAIN", "") or "").strip()
    csrf_domain = str(getattr(settings, "CSRF_COOKIE_DOMAIN", "") or "").strip()
    if session_domain.startswith(".") or csrf_domain.startswith("."):
        warnings.append(
            Warning(
                "Cross-subdomain auth cookies are enabled.",
                hint=(
                    "Manager and tenant hosts should use host-only cookies by default. "
                    "Unset SESSION_COOKIE_DOMAIN / CSRF_COOKIE_DOMAIN unless shared auth scope is intentional."
                ),
                id="tenancy.W001",
            )
        )
    return warnings
