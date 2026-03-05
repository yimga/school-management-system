"""
Install/uninstall pipeline and widget registry (RunMyCampus blueprint).
On install: record install, apply schema patches if any, register widgets, audit log.
"""
import logging
from django.utils import timezone
from django.core.management import call_command

logger = logging.getLogger(__name__)


def run_schema_patches_for_installation(installation):
    """
    Run schema patches (migrations) for an app installation when the app manifest
    declares a Django app to migrate (e.g. "migrations_app": "my_app").
    P3: In schema-per-tenant mode, ensures tenant schema is active before running migrate
    (so patches run in the correct tenant schema whether install is from view or task).
    In RLS mode, runs in the single schema. Optional; failures are logged, not raised.
    """
    from apps.marketplace.models import AppInstallation, AppAuditLog

    if not isinstance(installation, AppInstallation):
        return
    app = getattr(installation, "app", None)
    if not app:
        return
    manifest = getattr(app, "manifest", None) or {}
    app_label = manifest.get("migrations_app") or manifest.get("schema_patch_app")
    if not app_label or not isinstance(app_label, str):
        return
    app_label = app_label.strip()
    if not app_label:
        return

    def _run_migrate():
        call_command("migrate", app_label, verbosity=1, run_syncdb=False)

    try:
        school = getattr(installation, "school", None)
        if school:
            from apps.schools.domain_sync import use_django_tenants, ensure_tenant_client_for_school
            if use_django_tenants():
                client = ensure_tenant_client_for_school(school)
                if client and getattr(client, "schema_name", None):
                    from django_tenants.utils import schema_context
                    with schema_context(client.schema_name):
                        _run_migrate()
                else:
                    _run_migrate()
            else:
                _run_migrate()
        else:
            _run_migrate()
        logger.info("Schema patches applied for installation %s (app=%s)", installation.id, app_label)
        AppAuditLog.objects.create(
            installation=installation,
            school=installation.school,
            app=app,
            action="schema_patch",
            payload={"app_label": app_label},
            actor=None,
        )
    except Exception as e:
        logger.warning("Schema patch failed for installation %s (app=%s): %s", installation.id, app_label, e)


def install_app(school, app, *, installed_by=None, config=None, run_schema_patches=True):
    """
    Install an app for a school. Creates AppInstallation, optionally runs schema patches,
    logs audit, returns installation.
    If the app manifest has "migrations_app" or "schema_patch_app" (Django app label),
    and run_schema_patches is True, migrations for that app are run in the current
    connection context (tenant schema in schema-per-tenant mode; single schema in RLS).
    """
    from apps.marketplace.models import AppInstallation, AppAuditLog, MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    installation, created = AppInstallation.objects.get_or_create(
        school=school,
        app=app,
        defaults={
            "status": AppInstallation.Status.ACTIVE,
            "installed_by": installed_by,
            "config": config or {},
            "widget_config": app.manifest.get("widgets", {}),
        },
    )
    if not created:
        installation.status = AppInstallation.Status.ACTIVE
        installation.config = config or installation.config
        installation.widget_config = app.manifest.get("widgets", {})
        installation.save(update_fields=["status", "config", "widget_config"])
    if run_schema_patches:
        run_schema_patches_for_installation(installation)
    AppAuditLog.objects.create(
        installation=installation,
        school=school,
        app=app,
        action="install",
        payload={"config": installation.config},
        actor=installed_by,
    )
    return installation


def uninstall_app(school, app, *, uninstalled_by=None):
    """Mark app as uninstalled for the school; audit log."""
    from apps.marketplace.models import AppInstallation, AppAuditLog, MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    installation = AppInstallation.objects.get(school=school, app=app)
    installation.status = AppInstallation.Status.UNINSTALLED
    installation.save(update_fields=["status"])
    AppAuditLog.objects.create(
        installation=installation,
        school=school,
        app=app,
        action="uninstall",
        payload={},
        actor=uninstalled_by,
    )
    return installation


def suspend_app(school, app, *, suspended_by=None, reason: str = ""):
    """
    Kill switch (A2): suspend an app for a school. Widgets and capabilities are no longer served.
    get_installed_widgets already filters status=ACTIVE, so suspended apps are excluded.
    """
    from apps.marketplace.models import AppInstallation, AppAuditLog, MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    installation = AppInstallation.objects.get(school=school, app=app)
    installation.status = AppInstallation.Status.SUSPENDED
    installation.save(update_fields=["status"])
    AppAuditLog.objects.create(
        installation=installation,
        school=school,
        app=app,
        action="suspend",
        payload={"reason": reason or ""},
        actor=suspended_by,
    )
    return installation


def unsuspend_app(school, app, *, unsuspended_by=None):
    """Re-enable a suspended app for the school."""
    from apps.marketplace.models import AppInstallation, AppAuditLog, MarketplaceApp

    if not isinstance(app, MarketplaceApp):
        app = MarketplaceApp.objects.get(slug=app) if isinstance(app, str) else MarketplaceApp.objects.get(pk=app)
    installation = AppInstallation.objects.get(school=school, app=app)
    installation.status = AppInstallation.Status.ACTIVE
    installation.save(update_fields=["status"])
    AppAuditLog.objects.create(
        installation=installation,
        school=school,
        app=app,
        action="unsuspend",
        payload={},
        actor=unsuspended_by,
    )
    return installation


def grant_scopes(installation, scope_codes_or_scope_objects, granted_by=None):
    """
    Grant one or more scopes to an installation (tenant-approved). Creates ScopeGrant records.
    scope_codes_or_scope_objects: list of scope_code strings or AppScope instances for this app.
    """
    from apps.marketplace.models import AppScope, ScopeGrant

    for item in scope_codes_or_scope_objects:
        if isinstance(item, AppScope):
            scope = item
        else:
            scope = AppScope.objects.get(app=installation.app, scope_code=item)
        ScopeGrant.objects.get_or_create(
            installation=installation,
            scope=scope,
            defaults={"granted_by": granted_by},
        )


def get_installed_widgets(school):
    """
    Return list of widget configs for active installations (for dashboard/portal injection).
    Each item: { "app_slug": ..., "widget_id": ..., "config": ... } from manifest + widget_config.
    """
    from apps.marketplace.models import AppInstallation

    widgets = []
    for inst in AppInstallation.objects.filter(school=school, status=AppInstallation.Status.ACTIVE).select_related(
        "app"
    ):
        wconfig = inst.widget_config or inst.app.manifest.get("widgets") or {}
        if isinstance(wconfig, dict):
            for widget_id, cfg in wconfig.items():
                widgets.append({
                    "app_slug": inst.app.slug,
                    "widget_id": widget_id,
                    "config": cfg if isinstance(cfg, dict) else {},
                })
        elif isinstance(wconfig, list):
            for w in wconfig:
                widgets.append({
                    "app_slug": inst.app.slug,
                    "widget_id": w.get("id", ""),
                    "config": w,
                })
    return widgets
