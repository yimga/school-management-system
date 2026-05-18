"""URL routing for the Migration Cloud public REST API (v3.27 alpha + v3.29).

DRF DefaultRouter mounts:
  - /bundles/                                 (list, create)
  - /bundles/<pk>/                            (retrieve)
  - /bundles/<pk>/advance/                    (custom action)
  - /bundles/<pk>/apply/                      (custom action)
  - /bundles/<pk>/reconcile/                  (custom action)
  - /bundles/<pk>/artifacts/                  (read-only artifact list)
  - /bundles/<pk>/artifacts/bulk/             (v3.29 — multipart bulk upload)
  - /bundles/<pk>/events/stream/              (v3.29 — SSE progress mirror)
  - /templates/                               (list)
  - /templates/<domain>/                      (retrieve)
  - /templates/download/                      (custom action)
  - /tokens/                                  (v3.29 — mint / list / revoke scoped API tokens)
  - /tokens/<id>/                             (revoke)
  - /tokens/scopes/catalog/                   (known-scopes catalog)
  - /webhooks/                                (v3.29 — register / list webhook subscriptions)
  - /webhooks/<id>/                           (deactivate)
  - /schema/                                  (v3.29 — raw OpenAPI YAML)
  - /docs/                                    (v3.29 — Redoc HTML UI)

Mount point is added in ``apps/migration_cloud/urls.py`` with prefix
``api/v1/`` so the full path under the operator shell is
``/super/migration/api/v1/bundles/`` and under the tenant shell is
``/portal/configure/migration/api/v1/bundles/``.

App namespace: ``migration_cloud_api`` (uniqueness preserved across
both mount points because the parent ``app_name`` is shared).
"""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .docs import MigrationCloudRedocView, MigrationCloudSchemaView
from .scoped_tokens import ScopedTokenViewSet
from .viewsets import BundleViewSet, CanonicalTemplateViewSet
from .webhooks import WebhookSubscriptionViewSet

app_name = "migration_cloud_api"

router = DefaultRouter()
router.register(r"bundles", BundleViewSet, basename="bundle")
router.register(r"templates", CanonicalTemplateViewSet, basename="template")
router.register(r"tokens", ScopedTokenViewSet, basename="token")
router.register(r"webhooks", WebhookSubscriptionViewSet, basename="webhook")


_SCHEMA_NAME = "migration-cloud-schema"

urlpatterns = [
    path("", include(router.urls)),
    path(
        "schema/",
        MigrationCloudSchemaView.as_view(),
        name=_SCHEMA_NAME,
    ),
    path(
        "docs/",
        MigrationCloudRedocView.as_view(),
        name="migration-cloud-docs",
    ),
]
