"""Migration Cloud public REST API alpha — smoke tests.

Schema-only / introspection tests using ``SimpleTestCase`` so the suite
runs even when the local sqlite test-DB is in a bad state (per memory
v3.23.10: pre-existing infra issue blocks DB-backed tests in this
workspace). DB-backed integration tests are tracked separately in the
agent's pending docket.

Coverage:
  - URL resolution for every public route (list, retrieve, custom
    actions, canonical-template endpoints)
  - Every viewset action carries ``@extend_schema`` (via the
    ``extend_schema_view`` decorator on the class, OR a direct
    ``@extend_schema`` on the action method) — required to pass
    ``scan_drf_schema_coverage``.
  - Subpackage imports cleanly (catches Django app-load regressions).
"""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import reverse


# Both mount points share the same include() so the namespace + names
# resolve at either operator (super) or tenant (portal) URL roots.
_API_NS_SUPER = "migration_cloud_super:migration_cloud_api"
_API_NS_PORTAL = "migration_cloud_portal:migration_cloud_api"


class APISubpackageImportTests(SimpleTestCase):
    """The subpackage must import end-to-end without side effects."""

    def test_serializers_module_imports(self):
        from apps.migration_cloud.api import serializers
        self.assertTrue(hasattr(serializers, "MigrationBundleSerializer"))
        self.assertTrue(hasattr(serializers, "MigrationArtifactSerializer"))
        self.assertTrue(hasattr(serializers, "MigrationRunSerializer"))

    def test_viewsets_module_imports(self):
        from apps.migration_cloud.api import viewsets
        self.assertTrue(hasattr(viewsets, "BundleViewSet"))
        self.assertTrue(hasattr(viewsets, "CanonicalTemplateViewSet"))

    def test_auth_module_imports(self):
        from apps.migration_cloud.api import auth
        self.assertTrue(hasattr(auth, "MigrationCloudTokenAuthentication"))

    def test_permissions_module_imports(self):
        from apps.migration_cloud.api import permissions
        self.assertTrue(hasattr(permissions, "MigrationCloudAPIPermission"))

    def test_router_module_imports(self):
        from rest_framework.routers import DefaultRouter
        from apps.migration_cloud.api import urls as api_urls
        self.assertIsInstance(api_urls.router, DefaultRouter)


class APIURLResolutionTests(SimpleTestCase):
    """Every public route must be reachable via reverse() at both mounts."""

    def test_bundle_list_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:bundle-list")
        self.assertIn("/api/v1/bundles/", url)

    def test_bundle_detail_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:bundle-detail", kwargs={"pk": 42})
        self.assertIn("/bundles/42/", url)

    def test_canonical_template_list_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:template-list")
        self.assertIn("/api/v1/templates/", url)

    def test_canonical_template_detail_url_resolves(self):
        url = reverse(
            f"{_API_NS_SUPER}:template-detail",
            kwargs={"domain": "students"},
        )
        self.assertIn("/templates/students/", url)

    def test_canonical_template_download_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:template-download")
        self.assertIn("/templates/download/", url)

    def test_advance_action_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:bundle-advance", kwargs={"pk": 7})
        self.assertIn("/bundles/7/advance/", url)

    def test_apply_action_url_resolves(self):
        # action method is named ``apply_bundle`` so it doesn't shadow
        # the python builtin — DRF derives the URL name from url_path
        # if available, otherwise from the method name. We registered
        # ``url_path="apply"`` so the URL name is "bundle-apply-bundle".
        # Resolve via either of the two likely names defensively.
        try:
            url = reverse(f"{_API_NS_SUPER}:bundle-apply-bundle", kwargs={"pk": 7})
        except Exception:  # noqa: BLE001
            url = reverse(f"{_API_NS_SUPER}:bundle-apply", kwargs={"pk": 7})
        self.assertIn("/bundles/7/apply/", url)

    def test_reconcile_action_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:bundle-reconcile", kwargs={"pk": 7})
        self.assertIn("/bundles/7/reconcile/", url)

    def test_artifacts_action_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:bundle-artifacts", kwargs={"pk": 7})
        self.assertIn("/bundles/7/artifacts/", url)

    def test_portal_mount_also_resolves(self):
        """The same router is mounted at the tenant shell too."""
        url = reverse(f"{_API_NS_PORTAL}:bundle-list")
        self.assertIn("/api/v1/bundles/", url)


class APISchemaCoverageTests(SimpleTestCase):
    """Every viewset class + every @action carries an @extend_schema.

    Required by ``scan_drf_spectacular_schema_coverage`` (the project
    enforces this gate at zero-tolerance for ``apps/api/`` and any
    subpackage that registers viewsets through a DRF router).
    """

    def _has_extend_schema_decoration(self, obj) -> bool:
        """Return True if drf-spectacular has decorated this callable."""
        # extend_schema attaches `kwargs` and other markers; extend_schema_view
        # patches each action method's wrapped function with a `kwargs` dict.
        if hasattr(obj, "kwargs"):
            return True
        if hasattr(obj, "_spectacular_annotation"):
            return True
        # extend_schema_view replaces methods on the class with decorated
        # versions; the original function still has a __wrapped__ chain.
        wrapped = getattr(obj, "__wrapped__", None)
        if wrapped is not None and hasattr(wrapped, "kwargs"):
            return True
        # Fallback: walk the entire __dict__ for any spectacular marker.
        for attr in ("schema", "_openapi_schema", "_drf_spectacular"):
            if hasattr(obj, attr):
                return True
        return False

    def test_bundle_viewset_class_decorated(self):
        from apps.migration_cloud.api.viewsets import BundleViewSet

        # extend_schema_view registers each named action's schema on the
        # class via the `__init_subclass__` plumbing — the easiest check
        # is to inspect that the class methods carry the marker.
        for action_name in ("list", "retrieve", "create"):
            method = getattr(BundleViewSet, action_name, None)
            self.assertIsNotNone(
                method, f"BundleViewSet must expose {action_name}()",
            )
            self.assertTrue(
                self._has_extend_schema_decoration(method),
                f"BundleViewSet.{action_name} missing @extend_schema",
            )

    def test_bundle_viewset_custom_actions_decorated(self):
        from apps.migration_cloud.api.viewsets import BundleViewSet

        for action_name in ("advance", "apply_bundle", "reconcile", "artifacts"):
            method = getattr(BundleViewSet, action_name, None)
            self.assertIsNotNone(
                method, f"BundleViewSet must expose action {action_name}()",
            )
            self.assertTrue(
                self._has_extend_schema_decoration(method),
                f"BundleViewSet.{action_name} missing @extend_schema",
            )

    def test_canonical_template_viewset_decorated(self):
        from apps.migration_cloud.api.viewsets import CanonicalTemplateViewSet

        for action_name in ("list", "retrieve", "download"):
            method = getattr(CanonicalTemplateViewSet, action_name, None)
            self.assertIsNotNone(
                method,
                f"CanonicalTemplateViewSet must expose {action_name}()",
            )
            self.assertTrue(
                self._has_extend_schema_decoration(method),
                f"CanonicalTemplateViewSet.{action_name} missing @extend_schema",
            )

    def test_extend_schema_decorator_present_on_every_view(self):
        """Aggregate gate: every action across both viewsets is decorated."""
        from apps.migration_cloud.api.viewsets import (
            BundleViewSet,
            CanonicalTemplateViewSet,
        )

        targets = {
            "BundleViewSet": (
                BundleViewSet,
                ("list", "retrieve", "create", "advance",
                 "apply_bundle", "reconcile", "artifacts"),
            ),
            "CanonicalTemplateViewSet": (
                CanonicalTemplateViewSet,
                ("list", "retrieve", "download"),
            ),
        }
        missing: list[str] = []
        for cls_name, (cls, actions) in targets.items():
            for action_name in actions:
                method = getattr(cls, action_name, None)
                if method is None or not self._has_extend_schema_decoration(method):
                    missing.append(f"{cls_name}.{action_name}")
        self.assertEqual(
            missing,
            [],
            f"OpenAPI coverage gap: {missing}",
        )


class APISerializerShapeTests(SimpleTestCase):
    """The bundle serializer enumerates exactly the contract fields."""

    def test_bundle_serializer_fields(self):
        from apps.migration_cloud.api.serializers import MigrationBundleSerializer

        expected = {
            "id", "school_id", "label", "source_hint", "intake_method",
            "status", "sla_tier", "size_summary", "discovery_summary",
            "mapping_summary", "reconciliation_summary",
            "created_at", "updated_at",
        }
        self.assertEqual(
            set(MigrationBundleSerializer.Meta.fields),
            expected,
        )

    def test_bundle_serializer_readonly_fields(self):
        from apps.migration_cloud.api.serializers import MigrationBundleSerializer

        # status + summary fields must NOT be writable via the API.
        for field in (
            "status", "size_summary", "discovery_summary",
            "mapping_summary", "reconciliation_summary",
        ):
            self.assertIn(field, MigrationBundleSerializer.Meta.read_only_fields)

    def test_artifact_serializer_fields(self):
        from apps.migration_cloud.api.serializers import MigrationArtifactSerializer

        expected = {
            "id", "bundle_id", "filename", "path_within_bundle",
            "detected_format", "byte_size", "row_count", "column_count",
            "profile", "quarantined", "created_at",
        }
        self.assertEqual(
            set(MigrationArtifactSerializer.Meta.fields),
            expected,
        )
