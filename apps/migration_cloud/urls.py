"""URL grammar for the Migration Cloud wizard.

Mounted twice from ``config/urls.py`` — once under ``/super/migration/``
(operator) and once under ``/portal/configure/migration/`` (tenant,
plan-gated). The single URL set + ``shell`` kwarg keeps view logic
unified.

Example mount in ``config/urls.py``::

    path("super/migration/", include(("apps.migration_cloud.urls", "migration_cloud_super"), namespace="migration_cloud_super"), {"shell": "super"}),
    path("portal/configure/migration/", include(("apps.migration_cloud.urls", "migration_cloud_portal"), namespace="migration_cloud_portal"), {"shell": "portal"}),
"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "migration_cloud"

urlpatterns = [
    path("", views.MigrationCloudConsoleView.as_view(), name="console"),
    path("<int:bundle_id>/", views.MigrationCloudBundleDetailView.as_view(), name="bundle_detail"),
    path("<int:bundle_id>/advance/", views.MigrationCloudAdvanceView.as_view(), name="bundle_advance"),
    path("<int:bundle_id>/apply/", views.MigrationCloudApplyView.as_view(), name="bundle_apply"),
    path("<int:bundle_id>/reconcile/", views.MigrationCloudReconcileView.as_view(), name="bundle_reconcile"),
    path("<int:bundle_id>/feedback/", views.MigrationCloudFeedbackView.as_view(), name="bundle_feedback"),
    path("<int:bundle_id>/save-profile/", views.MigrationCloudSaveProfileView.as_view(), name="bundle_save_profile"),
    path("<int:bundle_id>/review/", views.MigrationCloudAnomalyNudgeView.as_view(), name="bundle_review"),
    path("<int:bundle_id>/shadow/", views.MigrationCloudShadowView.as_view(), name="bundle_shadow"),
    path("<int:bundle_id>/runs/<int:run_id>/rollback/", views.MigrationCloudRollbackView.as_view(), name="run_rollback"),
]
