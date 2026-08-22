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
  - /bundles/<pk>/quarantine/                 (held-row list + summary)
  - /bundles/<pk>/quarantine/resolve/         (held-row actions)
  - /bundles/<pk>/quarantine/export/          (CSV export)
  - /bundles/<pk>/ai-explain/                 (AI row explanation)
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

import mimetypes
import os

from django.http import FileResponse, Http404
from django.urls import include, path
from django.views.decorators.http import require_GET
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


# ─── v3.33.0 — verifier SDK downloads ─────────────────────────────────────

#: Map of url-segment → on-disk asset name. Each file is shipped under
#: ``apps/migration_cloud/api/static/`` and served with appropriate
#: ``Content-Type`` + ``Content-Disposition: attachment`` for the
#: subscriber-side reference SDKs / verification docs.
_VERIFIER_ASSETS = {
    "python": ("webhook_verifier_sdk.py", "text/x-python"),
    "javascript": ("runmycampus_webhook_verifier.js", "application/javascript"),
    "docs": ("WEBHOOK_VERIFICATION.md", "text/markdown"),
}


@require_GET
def webhook_verifier_download(request, asset: str):
    """Serve a single verifier-SDK asset as a downloadable attachment.

    Public-anonymous: the SDK files contain zero secrets — they are the
    reference verification code partners use on their own servers. The
    docs page links to each.
    """
    if asset not in _VERIFIER_ASSETS:
        raise Http404("unknown asset")
    # The Python SDK file ships in the api package directory; the JS +
    # docs ship under api/static/. Resolve from package __file__ so the
    # path holds across deployment layouts.
    here = os.path.dirname(os.path.abspath(__file__))
    if asset == "python":
        path_on_disk = os.path.join(here, _VERIFIER_ASSETS[asset][0])
    else:
        path_on_disk = os.path.join(here, "static", _VERIFIER_ASSETS[asset][0])
    if not os.path.isfile(path_on_disk):
        raise Http404("asset missing")
    content_type = _VERIFIER_ASSETS[asset][1] or (
        mimetypes.guess_type(path_on_disk)[0] or "application/octet-stream"
    )
    response = FileResponse(open(path_on_disk, "rb"), content_type=content_type)
    filename = os.path.basename(path_on_disk)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "public, max-age=300"
    return response


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
    # v3.33.0 — subscriber-side verifier SDK downloads (Python + JS + docs).
    path(
        "webhooks/verifier/<str:asset>/",
        webhook_verifier_download,
        name="webhook-verifier-download",
    ),
]
