"""
Django system checks: enforce TENANCY_MODE / USE_DJANGO_TENANTS vs middleware and DB engine.
Never run both schema and RLS tenant resolution in the same request path.
"""

from django.apps import apps as django_apps
from django.conf import settings
from django.core.checks import Error, Warning, register


SCHEMA_REQUIRED_APPS = {
    "apps.registries",
    "apps.billing",
    "apps.metadata.apps.MetadataConfig",
}

SCHEMA_TENANT_ONLY_APPS = {
    "apps.portal",
    "apps.student360",
    "apps.academics",
    "apps.people",
    "apps.finance",
    "apps.evals",
    "apps.reports",
    "apps.communication",
    "apps.analytics",
    "apps.payroll",
    "apps.school_events",
    "apps.schoolops",
}


@register()
def tenancy_strategy_checks(app_configs, **kwargs):
    errors = []
    use_tenants = getattr(settings, "USE_DJANGO_TENANTS", False)
    mw = getattr(settings, "MIDDLEWARE", [])
    engine = (settings.DATABASES.get("default") or {}).get("ENGINE", "")

    if use_tenants:
        if not any(
            "TenantMainMiddleware" in m or "HealthAwareTenantMainMiddleware" in m for m in mw
        ):
            errors.append(
                Error(
                    "USE_DJANGO_TENANTS is True but TenantMainMiddleware is missing.",
                    hint=(
                        "Add apps.schools.middleware_tenant_main.HealthAwareTenantMainMiddleware "
                        "(or django_tenants.middleware.main.TenantMainMiddleware) when using "
                        "schema-per-tenant."
                    ),
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
        missing_apps = sorted(
            app for app in SCHEMA_REQUIRED_APPS if app not in installed_apps
        )
        if missing_apps:
            errors.append(
                Error(
                    "Schema mode is missing required shared apps.",
                    hint="Add the missing platform apps to SHARED_APPS/INSTALLED_APPS: %s"
                    % ", ".join(missing_apps),
                    id="tenancy.E004",
                )
            )
        shared_apps = set(getattr(settings, "SHARED_APPS", []) or [])
        tenant_apps = set(getattr(settings, "TENANT_APPS", []) or [])
        leaked_shared_apps = sorted(
            app for app in SCHEMA_TENANT_ONLY_APPS if app in shared_apps
        )
        missing_tenant_apps = sorted(
            app for app in SCHEMA_TENANT_ONLY_APPS if app not in tenant_apps
        )
        if leaked_shared_apps:
            errors.append(
                Error(
                    "Schema mode has tenant-only apps in SHARED_APPS.",
                    hint="Move these apps to TENANT_APPS so tenant data never migrates into the public schema: %s"
                    % ", ".join(leaked_shared_apps),
                    id="tenancy.E005",
                )
            )
        if missing_tenant_apps:
            errors.append(
                Error(
                    "Schema mode is missing tenant-only apps from TENANT_APPS.",
                    hint="Add these apps to TENANT_APPS: %s"
                    % ", ".join(missing_tenant_apps),
                    id="tenancy.E006",
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


@register()
def shared_model_tenant_constraint_checks(app_configs, **kwargs):
    errors = []
    if not getattr(settings, "USE_DJANGO_TENANTS", False):
        return errors

    shared_apps = {
        app.split(".")[-1]
        for app in (getattr(settings, "SHARED_APPS", []) or [])
        if app == "emis" or app.startswith("apps.")
    }
    tenant_apps = {
        app.split(".")[-1]
        for app in (getattr(settings, "TENANT_APPS", []) or [])
        if app.startswith("apps.")
    }

    for model in django_apps.get_models():
        if model._meta.app_label not in shared_apps:
            continue
        for field in list(model._meta.local_fields) + list(
            model._meta.local_many_to_many
        ):
            if not getattr(field, "is_relation", False):
                continue
            remote_field = getattr(field, "remote_field", None)
            related_model = (
                getattr(remote_field, "model", None) if remote_field else None
            )
            if not getattr(related_model, "_meta", None):
                continue
            if related_model._meta.app_label not in tenant_apps:
                continue
            if getattr(field, "db_constraint", True):
                errors.append(
                    Error(
                        (
                            f"Schema mode has a shared-to-tenant relation: "
                            f"{model._meta.label}.{field.name} -> {related_model._meta.label}."
                        ),
                        hint=(
                            "Shared-app models must not point at tenant-app models. "
                            "Replace the relation with a tenant-safe pointer/value object, or move the model into a tenant app."
                        ),
                        id="tenancy.E007",
                    )
                )
    return errors
