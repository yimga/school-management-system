"""Customer-facing Migration Cloud URLs (v3.40.0 Agent 7).

Mounted from ``config/urls.py`` at ``/migration/`` (NOT
``/super/migration/`` — that namespace is operator-side).

::

    path("migration/", include(("apps.migration_cloud.urls_customer",
        "migration_intake_customer"), namespace="migration_intake_customer")),

The router uses string UUIDs for ``<id>`` so the underlying view layer
can do its own ``UUID()`` parse + raise 404 on malformed input. (The
``<uuid:>`` path converter would 404 *before* the view, which is fine,
but the explicit parse in the view also covers programmatic callers.)
"""

from __future__ import annotations

from django.urls import path

from . import views_customer

app_name = "migration_intake_customer"

urlpatterns = [
    path(
        "",
        views_customer.MigrationIntakeListView.as_view(),
        name="migration-intake-list",
    ),
    path(
        "start/",
        views_customer.MigrationIntakeStartView.as_view(),
        name="migration-intake-start",
    ),
    path(
        "<uuid:id>/sign-maa/",
        views_customer.MigrationIntakeMAASignView.as_view(),
        name="migration-intake-sign-maa",
    ),
    path(
        "<uuid:id>/upload/",
        views_customer.MigrationIntakeUploadView.as_view(),
        name="migration-intake-upload",
    ),
    path(
        "<uuid:id>/status/",
        views_customer.MigrationIntakeStatusView.as_view(),
        name="migration-intake-status",
    ),
    path(
        "<uuid:id>/status/stream/",
        views_customer.MigrationIntakeStatusStreamView.as_view(),
        name="migration-intake-status-stream",
    ),
    path(
        "<uuid:id>/abandon/",
        views_customer.MigrationIntakeAbandonView.as_view(),
        name="migration-intake-abandon",
    ),
    path(
        "<uuid:id>/approve-promotion/",
        views_customer.MigrationIntakePromotionApproveView.as_view(),
        name="migration-intake-approve-promotion",
    ),
]
