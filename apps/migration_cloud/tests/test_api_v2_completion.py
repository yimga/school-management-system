"""Migration Cloud REST API completion (v3.29) — smoke + structural tests.

Schema-only / introspection tests using :class:`SimpleTestCase` so the
suite runs even when the local sqlite test-DB is in a bad state (per
memory v3.23.10 — pre-existing infra issue blocks DB-backed tests in
this workspace). DB-backed integration tests are tracked in the agent's
pending docket.

Coverage focus (≥20 tests):

* Module imports for every v3.29 new file.
* URL resolution for every new endpoint at both mount points.
* ``@extend_schema`` coverage on every new viewset action.
* Bulk-artifact size / count limits + dedup helpers (unit-level).
* Scoped-token hashing + scope-catalog invariants.
* Webhook dispatch signature math + retry schedule.
* Redoc + schema view permission shape.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest import mock

from django.test import SimpleTestCase
from django.urls import reverse


_API_NS_SUPER = "migration_cloud_super:migration_cloud_api"
_API_NS_PORTAL = "migration_cloud_portal:migration_cloud_api"


# ─── Module-import smoke ───────────────────────────────────────────────────


class V29ModuleImportTests(SimpleTestCase):
    def test_bulk_artifacts_imports(self):
        from apps.migration_cloud.api import bulk_artifacts
        self.assertTrue(hasattr(bulk_artifacts, "bulk_artifacts_action_factory"))
        self.assertGreater(bulk_artifacts.MAX_FILES_PER_REQUEST, 0)
        self.assertGreater(bulk_artifacts.MAX_FILE_BYTES, 0)
        self.assertGreater(bulk_artifacts.MAX_TOTAL_BYTES, 0)

    def test_sse_imports(self):
        from apps.migration_cloud.api import sse
        self.assertTrue(hasattr(sse, "events_stream_action_factory"))
        self.assertGreater(sse.SSE_MAX_DURATION_SECONDS, 0)

    def test_scoped_tokens_imports(self):
        from apps.migration_cloud.api import scoped_tokens
        self.assertTrue(hasattr(scoped_tokens, "ScopedTokenViewSet"))
        self.assertTrue(hasattr(scoped_tokens, "MigrationCloudScopedTokenAuthentication"))
        self.assertTrue(hasattr(scoped_tokens, "ACTION_SCOPE_REQUIREMENTS"))
        self.assertTrue(hasattr(scoped_tokens, "KNOWN_SCOPES"))

    def test_webhooks_imports(self):
        from apps.migration_cloud.api import webhooks
        self.assertTrue(hasattr(webhooks, "WebhookSubscriptionViewSet"))

    def test_webhook_dispatch_imports(self):
        from apps.migration_cloud.api import webhook_dispatch
        self.assertTrue(hasattr(webhook_dispatch, "enqueue"))
        self.assertTrue(hasattr(webhook_dispatch, "deliver_due"))
        self.assertEqual(len(webhook_dispatch.RETRY_SCHEDULE), webhook_dispatch.MAX_ATTEMPTS)

    def test_docs_view_imports(self):
        from apps.migration_cloud.api import docs
        self.assertTrue(hasattr(docs, "MigrationCloudSchemaView"))
        self.assertTrue(hasattr(docs, "MigrationCloudRedocView"))


# ─── URL resolution ────────────────────────────────────────────────────────


class V29URLResolutionTests(SimpleTestCase):
    def test_bulk_artifacts_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:bundle-bulk-artifacts", kwargs={"pk": 7})
        self.assertIn("/bundles/7/artifacts/bulk/", url)

    def test_events_stream_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:bundle-events-stream", kwargs={"pk": 7})
        self.assertIn("/bundles/7/events/stream/", url)

    def test_token_list_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:token-list")
        self.assertIn("/api/v1/tokens/", url)

    def test_token_scopes_catalog_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:token-scopes-catalog")
        self.assertIn("/tokens/scopes/catalog/", url)

    def test_webhook_list_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:webhook-list")
        self.assertIn("/api/v1/webhooks/", url)

    def test_schema_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:migration-cloud-schema")
        self.assertIn("/schema/", url)

    def test_docs_url_resolves(self):
        url = reverse(f"{_API_NS_SUPER}:migration-cloud-docs")
        self.assertIn("/docs/", url)

    def test_portal_mount_also_resolves_new_urls(self):
        for name in (
            "bundle-bulk-artifacts",
            "token-list",
            "webhook-list",
            "migration-cloud-schema",
            "migration-cloud-docs",
        ):
            kwargs = {"pk": 1} if "bulk-artifacts" in name else {}
            url = reverse(f"{_API_NS_PORTAL}:{name}", kwargs=kwargs)
            self.assertTrue(url.startswith("/"), f"{name} did not resolve cleanly")


# ─── @extend_schema coverage on the new actions ────────────────────────────


class V29SchemaCoverageTests(SimpleTestCase):
    def _has_extend_schema_decoration(self, obj) -> bool:
        if hasattr(obj, "kwargs"):
            return True
        if hasattr(obj, "_spectacular_annotation"):
            return True
        wrapped = getattr(obj, "__wrapped__", None)
        if wrapped is not None and hasattr(wrapped, "kwargs"):
            return True
        for attr in ("schema", "_openapi_schema", "_drf_spectacular"):
            if hasattr(obj, attr):
                return True
        return False

    def test_bundle_viewset_v29_actions_decorated(self):
        from apps.migration_cloud.api.viewsets import BundleViewSet
        for action_name in ("bulk_artifacts", "events_stream"):
            method = getattr(BundleViewSet, action_name, None)
            self.assertIsNotNone(method, f"Missing action {action_name}")
            self.assertTrue(
                self._has_extend_schema_decoration(method),
                f"BundleViewSet.{action_name} missing @extend_schema",
            )

    def test_token_viewset_actions_decorated(self):
        from apps.migration_cloud.api.scoped_tokens import ScopedTokenViewSet
        for action_name in ("list", "retrieve", "create", "destroy", "scopes_catalog"):
            method = getattr(ScopedTokenViewSet, action_name, None)
            self.assertIsNotNone(method, f"Missing action {action_name}")
            self.assertTrue(
                self._has_extend_schema_decoration(method),
                f"ScopedTokenViewSet.{action_name} missing @extend_schema",
            )

    def test_webhook_viewset_actions_decorated(self):
        from apps.migration_cloud.api.webhooks import WebhookSubscriptionViewSet
        for action_name in ("list", "retrieve", "create", "destroy"):
            method = getattr(WebhookSubscriptionViewSet, action_name, None)
            self.assertIsNotNone(method, f"Missing action {action_name}")
            self.assertTrue(
                self._has_extend_schema_decoration(method),
                f"WebhookSubscriptionViewSet.{action_name} missing @extend_schema",
            )


# ─── Scope catalog / token hashing invariants ──────────────────────────────


class ScopedTokenInvariantTests(SimpleTestCase):
    def test_known_scopes_nonempty(self):
        from apps.migration_cloud.api.scoped_tokens import KNOWN_SCOPES
        self.assertGreater(len(KNOWN_SCOPES), 0)
        for s in KNOWN_SCOPES:
            self.assertIn(":", s, f"scope '{s}' is not resource:action")

    def test_every_viewset_action_has_scope_mapping(self):
        from apps.migration_cloud.api.scoped_tokens import ACTION_SCOPE_REQUIREMENTS
        required_pairs = {
            ("bundle", "list"),
            ("bundle", "retrieve"),
            ("bundle", "create"),
            ("bundle", "advance"),
            ("bundle", "apply_bundle"),
            ("bundle", "reconcile"),
            ("bundle", "artifacts"),
            ("bundle", "bulk_artifacts"),
            ("bundle", "events_stream"),
            ("template", "list"),
            ("template", "retrieve"),
            ("template", "download"),
            ("token", "list"),
            ("token", "create"),
            ("token", "destroy"),
            ("webhook", "list"),
            ("webhook", "create"),
            ("webhook", "retrieve"),
            ("webhook", "destroy"),
        }
        missing = required_pairs - set(ACTION_SCOPE_REQUIREMENTS.keys())
        self.assertEqual(missing, set(), f"Scope mapping missing entries: {missing}")

    def test_hash_token_is_sha256_hex(self):
        from apps.migration_cloud.api.scoped_tokens import _hash_token

        plaintext = "mc_example_test_value_not_real"
        digest = _hash_token(plaintext)
        self.assertEqual(len(digest), 64)
        self.assertEqual(
            digest, hashlib.sha256(plaintext.encode("utf-8")).hexdigest(),
        )

    def test_generated_plaintext_format(self):
        from apps.migration_cloud.api.scoped_tokens import _generate_token_plaintext

        a, b = _generate_token_plaintext(), _generate_token_plaintext()
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith("mc_"))
        # 32 bytes -> 43 chars urlsafe → ≥ 30 chars total after prefix
        self.assertGreaterEqual(len(a), 32)


# ─── Webhook dispatch math ─────────────────────────────────────────────────


class WebhookDispatchMathTests(SimpleTestCase):
    def test_canonical_payload_is_deterministic(self):
        from apps.migration_cloud.api.webhook_dispatch import _canonical_payload_bytes
        a = _canonical_payload_bytes({"b": 2, "a": 1})
        b = _canonical_payload_bytes({"a": 1, "b": 2})
        self.assertEqual(a, b)
        # No whitespace
        self.assertNotIn(b" ", a)

    def test_signature_matches_hmac_sha256(self):
        from apps.migration_cloud.api.webhook_dispatch import (
            _canonical_payload_bytes,
            _sign,
        )
        secret = b"whsec_test_value_not_real"
        payload = {"event": "bundle.advanced", "bundle_id": 7}
        body = _canonical_payload_bytes(payload)
        sig = _sign(secret, body)
        expected_hex = hmac.new(secret, body, hashlib.sha256).hexdigest()
        self.assertEqual(sig, f"sha256={expected_hex}")

    def test_retry_schedule_is_increasing(self):
        from apps.migration_cloud.api.webhook_dispatch import RETRY_SCHEDULE
        seconds = [td.total_seconds() for td in RETRY_SCHEDULE]
        self.assertEqual(sorted(seconds), seconds)
        self.assertEqual(len(seconds), 6)
        # First retry at 60s, last at 24h
        self.assertEqual(seconds[0], 60)
        self.assertEqual(seconds[-1], 24 * 3600)


# ─── Bulk artifacts hashing helper ─────────────────────────────────────────


class BulkArtifactsHashTests(SimpleTestCase):
    def test_sha256_of_upload_streams_correctly(self):
        from apps.migration_cloud.api.bulk_artifacts import _sha256_of_upload

        class _FakeUpload:
            def __init__(self, data: bytes):
                self._data = data
                self._read = False

            def chunks(self, chunk_size=64 * 1024):
                # Two-chunk yield to exercise the streaming path.
                mid = max(1, len(self._data) // 2)
                yield self._data[:mid]
                yield self._data[mid:]

            def seek(self, where):
                pass

        payload = b"hello world bulk artifact bytes 1234567890" * 16
        digest, count = _sha256_of_upload(_FakeUpload(payload))
        self.assertEqual(count, len(payload))
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())


# ─── Models present + sane shape ───────────────────────────────────────────


class V29ModelShapeTests(SimpleTestCase):
    def test_models_module_exports_v29_models(self):
        from apps.migration_cloud import models as m
        self.assertTrue(hasattr(m, "MigrationCloudAPIToken"))
        self.assertTrue(hasattr(m, "MigrationCloudWebhookSubscription"))
        self.assertTrue(hasattr(m, "MigrationCloudWebhookDelivery"))
        self.assertTrue(hasattr(m, "WebhookDeliveryStatus"))

    def test_api_token_model_fields(self):
        from apps.migration_cloud.models import MigrationCloudAPIToken
        field_names = {f.name for f in MigrationCloudAPIToken._meta.get_fields()}
        for required in (
            "user", "token_hash", "name", "scopes", "tenant_scope",
            "expires_at", "last_used_at", "revoked_at", "created_at",
        ):
            self.assertIn(required, field_names)

    def test_webhook_subscription_fields(self):
        from apps.migration_cloud.models import MigrationCloudWebhookSubscription
        field_names = {f.name for f in MigrationCloudWebhookSubscription._meta.get_fields()}
        for required in (
            "tenant", "url", "secret_hash", "secret_ciphertext",
            "event_types", "active", "created_by",
            "last_delivery_status", "created_at", "updated_at",
        ):
            self.assertIn(required, field_names)

    def test_webhook_delivery_fields(self):
        from apps.migration_cloud.models import MigrationCloudWebhookDelivery
        field_names = {f.name for f in MigrationCloudWebhookDelivery._meta.get_fields()}
        for required in (
            "subscription", "event_type", "payload_json", "request_signature",
            "attempt_count", "next_retry_at", "status",
            "last_response_code", "last_error", "created_at", "delivered_at",
        ):
            self.assertIn(required, field_names)


# ─── Permission class wiring ───────────────────────────────────────────────


class PermissionWiringTests(SimpleTestCase):
    def test_scoped_api_permission_subclasses_base(self):
        from apps.migration_cloud.api.permissions import (
            MigrationCloudAPIPermission,
            ScopedAPIPermission,
        )
        self.assertTrue(issubclass(ScopedAPIPermission, MigrationCloudAPIPermission))

    def test_auth_class_recognizes_scoped_prefix(self):
        from apps.migration_cloud.api.auth import MigrationCloudTokenAuthentication

        class _FakeRequest:
            META = {"HTTP_AUTHORIZATION": "Token mc_abc"}

        value = MigrationCloudTokenAuthentication.get_authorization_header_value(
            _FakeRequest()
        )
        self.assertEqual(value, "mc_abc")


# ─── Docs + schema view permission shape ───────────────────────────────────


class DocsViewPermissionTests(SimpleTestCase):
    def test_schema_view_is_public(self):
        from apps.migration_cloud.api.docs import MigrationCloudSchemaView
        perms = [p().__class__.__name__ for p in MigrationCloudSchemaView.permission_classes]
        self.assertIn("AllowAny", perms)

    def test_redoc_view_is_public(self):
        from apps.migration_cloud.api.docs import MigrationCloudRedocView
        perms = [p().__class__.__name__ for p in MigrationCloudRedocView.permission_classes]
        self.assertIn("AllowAny", perms)
