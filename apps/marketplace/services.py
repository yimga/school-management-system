"""
Install/uninstall pipeline and widget registry (RunMyCampus blueprint).
On install: record install, apply schema patches if any, register widgets, audit log.
"""
from django.utils import timezone


def install_app(school, app, *, installed_by=None, config=None):
    """
    Install an app for a school. Creates AppInstallation, logs audit, returns installation.
    Does not run migrations (schema patches) — that can be added as a separate step or background task.
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
