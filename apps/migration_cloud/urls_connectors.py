"""Migration Cloud connector wizard URLs."""

from __future__ import annotations

from django.urls import path

from . import views_connectors, views_tenant_provisioning, views_tenant_upload

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
    # Live auto-detection progress (JSON), polled by the review page while the
    # pipeline profiles/classifies/maps the upload. Tenant-scoped (404 on cross
    # tenant). See TenantMigrationProgressView.
    path(
        "bundle/<int:bundle_id>/progress/",
        views_tenant_upload.TenantMigrationProgressView.as_view(),
        name="bundle-progress",
    ),
    path(
        "bundle/<int:bundle_id>/retry/",
        views_tenant_upload.TenantMigrationRetryAdvanceView.as_view(),
        name="bundle-retry",
    ),
    path(
        "bundle/<int:bundle_id>/apply/",
        views_tenant_upload.TenantMigrationApplyView.as_view(),
        name="bundle-apply",
    ),
    # Safe idempotent re-import for a failed / partially-held bundle. See
    # TenantMigrationRepairView + repair.repair_bundle (conservative guardrails).
    path(
        "bundle/<int:bundle_id>/repair/",
        views_tenant_upload.TenantMigrationRepairView.as_view(),
        name="bundle-repair",
    ),
    # ── Self-serve provisioning (G-4) — tenant-admin gated. Lets a partner /
    # district mint a Migration Cloud scoped API token FORCE-BOUND to their own
    # school and register/deactivate outbound webhook subscriptions, without an
    # operator hand-off. All URLs are pre-resolved in the views (no cross-host
    # {% url %}). See views_tenant_provisioning.
    path(
        "tokens/",
        views_tenant_provisioning.TenantTokenListView.as_view(),
        name="provisioning-tokens",
    ),
    path(
        "tokens/mint/",
        views_tenant_provisioning.TenantTokenMintView.as_view(),
        name="provisioning-token-mint",
    ),
    path(
        "tokens/<int:token_id>/revoke/",
        views_tenant_provisioning.TenantTokenRevokeView.as_view(),
        name="provisioning-token-revoke",
    ),
    path(
        "webhooks/",
        views_tenant_provisioning.TenantWebhookView.as_view(),
        name="provisioning-webhooks",
    ),
    path(
        "webhooks/<int:sub_id>/deactivate/",
        views_tenant_provisioning.TenantWebhookDeactivateView.as_view(),
        name="provisioning-webhook-deactivate",
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
