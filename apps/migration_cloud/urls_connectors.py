"""Migration Cloud connector wizard URLs."""

from __future__ import annotations

from django.urls import path

from . import views_connectors, views_tenant_upload

app_name = "migration_cloud_connector"

urlpatterns = [
    path(
        "",
        views_connectors.MigrationCloudConnectorHomeView.as_view(),
        name="connector-home",
    ),
    path(
        "connect/",
        views_connectors.MigrationCloudConnectorConnectView.as_view(),
        name="connector-connect",
    ),
    # Connectionless file-first path: drop an Excel/CSV/PDF/ZIP, the bundle
    # pipeline auto-detects format + entity, tenant reviews, then imports.
    # No source connection required. Tenant-shelled (portal_base) so it renders
    # on the tenant host; URLs pre-resolved in the view (no cross-host {% url %}).
    path(
        "upload/",
        views_tenant_upload.TenantMigrationUploadView.as_view(),
        name="upload",
    ),
    path(
        "bundle/<int:bundle_id>/review/",
        views_tenant_upload.TenantMigrationReviewView.as_view(),
        name="bundle-review",
    ),
    path(
        "bundle/<int:bundle_id>/apply/",
        views_tenant_upload.TenantMigrationApplyView.as_view(),
        name="bundle-apply",
    ),
    path(
        "<uuid:connection_id>/discover/",
        views_connectors.MigrationCloudConnectorDiscoverView.as_view(),
        name="connector-discover",
    ),
    path(
        "<uuid:connection_id>/discover/<uuid:run_id>/mapping/",
        views_connectors.MigrationCloudConnectorMappingView.as_view(),
        name="connector-mapping",
    ),
    path(
        "<uuid:connection_id>/discover/<uuid:run_id>/validate/",
        views_connectors.MigrationCloudConnectorValidateView.as_view(),
        name="connector-validate",
    ),
    path(
        "<uuid:connection_id>/quarantine/<uuid:batch_id>/",
        views_connectors.MigrationCloudConnectorQuarantineView.as_view(),
        name="connector-quarantine",
    ),
    path(
        "<uuid:connection_id>/import/<uuid:batch_id>/",
        views_connectors.MigrationCloudConnectorImportView.as_view(),
        name="connector-import",
    ),
    path(
        "<uuid:connection_id>/review/<uuid:import_run_id>/",
        views_connectors.MigrationCloudConnectorReviewView.as_view(),
        name="connector-review",
    ),
    path(
        "<uuid:connection_id>/revoke/",
        views_connectors.MigrationCloudConnectorRevokeView.as_view(),
        name="connector-revoke",
    ),
]
