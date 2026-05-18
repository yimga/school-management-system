"""URL routing for the Migration Cloud public REST API alpha.

DRF DefaultRouter mounts:
  - /bundles/                                 (list, create)
  - /bundles/<pk>/                            (retrieve)
  - /bundles/<pk>/advance/                    (custom action)
  - /bundles/<pk>/apply/                      (custom action)
  - /bundles/<pk>/reconcile/                  (custom action)
  - /bundles/<pk>/artifacts/                  (custom action)
  - /templates/                               (list)
  - /templates/<domain>/                      (retrieve)
  - /templates/download/                      (custom action)

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

from .viewsets import BundleViewSet, CanonicalTemplateViewSet

app_name = "migration_cloud_api"

router = DefaultRouter()
router.register(r"bundles", BundleViewSet, basename="bundle")
router.register(r"templates", CanonicalTemplateViewSet, basename="template")

urlpatterns = [
    path("", include(router.urls)),
]
