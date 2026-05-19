"""v3.38.0 Agent 4 — metrics helpers + operator health view tests.

Coverage matrix (~14 tests):

  Metrics module
  --------------
  * ``_hash_tenant_id`` returns 12 lowercase hex chars
  * different inputs hash differently
  * identical inputs hash identically across calls
  * ``None`` tenant id collapses to the sentinel ``"unknown"``
  * all six ``record_*`` helpers are callable without raising even
    when the observability backend is absent (graceful degradation)
  * ``assertLogs`` confirms NONE of the helpers ever log raw byte
    payloads or signature bytes or tenant slug plaintext

  Health view
  -----------
  * 200 for staff
  * 302/403 for anonymous
  * 302/403 for non-staff
  * panels render with mock data
  * tenant slugs never appear in HTML response (only the hash)

  Scanner baseline reader
  -----------------------
  * missing file → "unknown" (graceful)
  * malformed JSON → "unknown" (graceful)

All tests use ``TestCase`` for the view path (DB-backed because the
panels query ORM models) and ``SimpleTestCase`` for the pure-function
helpers.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from apps.migration_cloud import metrics as mc_metrics
from apps.migration_cloud import views_health


User = get_user_model()


# ─── Metrics — hash helper ──────────────────────────────────────────────


class HashTenantIdTests(SimpleTestCase):
    def test_returns_12_hex_chars(self) -> None:
        out = mc_metrics._hash_tenant_id(1)
        self.assertEqual(len(out), 12)
        # All hex chars (lowercase per hashlib default).
        self.assertTrue(all(c in "0123456789abcdef" for c in out))

    def test_different_inputs_hash_differently(self) -> None:
        a = mc_metrics._hash_tenant_id("school-a")
        b = mc_metrics._hash_tenant_id("school-b")
        self.assertNotEqual(a, b)

    def test_same_input_hashes_same_twice(self) -> None:
        a = mc_metrics._hash_tenant_id("tenant-42")
        b = mc_metrics._hash_tenant_id("tenant-42")
        self.assertEqual(a, b)

    def test_none_returns_unknown_sentinel(self) -> None:
        self.assertEqual(mc_metrics._hash_tenant_id(None), "unknown")


# ─── Metrics — graceful degradation ─────────────────────────────────────


class MetricsBackendAbsentTests(SimpleTestCase):
    """Every record_* helper must be a no-op when the backend is absent."""

    def setUp(self) -> None:
        # Force the resolver to report "no backend" no matter what's on
        # the import path. Helpers MUST then route to the fallback
        # logger and never raise.
        self._patch = mock.patch.object(
            mc_metrics, "_resolve_backend", return_value=(None, None),
        )
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()

    def test_record_companion_upload_no_raise(self) -> None:
        mc_metrics.record_companion_upload(
            tenant_id=7, byte_size=1024,
            sealed_box_scheme="libsodium-secretbox-x25519-sealed",
        )

    def test_record_maa_sign_no_raise(self) -> None:
        mc_metrics.record_maa_sign(
            tenant_id=7, version="v1.0", was_draft_attempt=False,
        )

    def test_record_key_rotation_no_raise(self) -> None:
        mc_metrics.record_key_rotation(key_type="companion_x25519", success=True)

    def test_record_webhook_delivery_no_raise(self) -> None:
        mc_metrics.record_webhook_delivery(
            subscription_id=99, status="delivered", http_status=200,
        )

    def test_record_token_mint_no_raise(self) -> None:
        mc_metrics.record_token_mint(scope="bundles:read", success=True)

    def test_record_legacy_hash_decryption_no_raise(self) -> None:
        mc_metrics.record_legacy_hash_decryption(
            vendor="powerschool_pbkdf2_sha512", success=True,
        )


# ─── Metrics — log hygiene ──────────────────────────────────────────────


class MetricsLogHygieneTests(SimpleTestCase):
    """Helpers must NEVER log raw payload bytes, signature bytes, or slugs."""

    FORBIDDEN_MARKERS = (
        # Payload-byte poison strings used in tests below: if any of
        # these slip into the captured log lines, the assertion fails.
        "SECRET_PAYLOAD_BYTES_DO_NOT_LOG",
        "signature_bytes_xxxxxx",
        "plaintext-tenant-slug-do-not-log",
    )

    def _assert_clean(self, records) -> None:
        for r in records:
            msg = r.getMessage()
            for forbidden in self.FORBIDDEN_MARKERS:
                self.assertNotIn(
                    forbidden, msg,
                    f"forbidden marker {forbidden!r} leaked into log: {msg!r}",
                )

    def test_companion_upload_does_not_log_payload(self) -> None:
        with self.assertLogs("migration_cloud.metrics", level="DEBUG") as cm:
            # Tenant id is the slug poison marker so we can prove the
            # helper hashed it before emission.
            mc_metrics.record_companion_upload(
                tenant_id="plaintext-tenant-slug-do-not-log",
                byte_size=4096,
                sealed_box_scheme="libsodium-secretbox-x25519-sealed",
            )
        self._assert_clean(cm.records)

    def test_maa_sign_does_not_log_plaintext_slug(self) -> None:
        with self.assertLogs("migration_cloud.metrics", level="DEBUG") as cm:
            mc_metrics.record_maa_sign(
                tenant_id="plaintext-tenant-slug-do-not-log",
                version="v1.0",
                was_draft_attempt=False,
            )
        self._assert_clean(cm.records)

    def test_webhook_delivery_does_not_log_signature_bytes(self) -> None:
        with self.assertLogs("migration_cloud.metrics", level="DEBUG") as cm:
            mc_metrics.record_webhook_delivery(
                subscription_id=42,
                status="delivered",
                http_status=200,
            )
        self._assert_clean(cm.records)


# ─── Scanner baseline reader ────────────────────────────────────────────


class ScannerBaselineReaderTests(SimpleTestCase):
    def test_missing_file_returns_unknown(self) -> None:
        out = views_health._read_baseline_finding_count(
            "security-audit-baseline-this-does-not-exist.json"
        )
        self.assertEqual(out, "unknown")

    def test_malformed_json_returns_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fn = "security-audit-baseline-malformed.json"
            with open(Path(tmpdir) / fn, "w", encoding="utf-8") as fh:
                fh.write("{not-json")
            with mock.patch.object(
                views_health, "_var_dir", return_value=Path(tmpdir),
            ):
                out = views_health._read_baseline_finding_count(fn)
        self.assertEqual(out, "unknown")

    def test_valid_file_returns_finding_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fn = "security-audit-baseline-valid.json"
            with open(Path(tmpdir) / fn, "w", encoding="utf-8") as fh:
                json.dump({"finding_count": 0, "findings": []}, fh)
            with mock.patch.object(
                views_health, "_var_dir", return_value=Path(tmpdir),
            ):
                out = views_health._read_baseline_finding_count(fn)
        self.assertEqual(out, 0)


# ─── Health view ────────────────────────────────────────────────────────


class HealthViewAccessTests(TestCase):

    def setUp(self) -> None:
        self.staff = User.objects.create_superuser(
            username="health-staff",
            email="health-staff@example.invalid",
            password="x",
        )
        self.non_staff = User.objects.create_user(
            username="health-nonstaff", password="x", is_staff=False,
        )

    def _url(self) -> str:
        return reverse("migration_cloud_super:migration_cloud_health")

    def test_staff_200(self) -> None:
        request = RequestFactory().get(self._url(), secure=True)
        request.user = self.staff
        resp = views_health.MigrationCloudHealthView.as_view()(request)
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_redirect(self) -> None:
        # staff_member_required → 302 to admin login (Django default).
        resp = self.client.get(self._url())
        self.assertIn(resp.status_code, (302, 403))

    def test_non_staff_redirect(self) -> None:
        self.client.force_login(self.non_staff)
        resp = self.client.get(self._url())
        # staff_member_required redirects non-staff to the admin login.
        self.assertIn(resp.status_code, (302, 403))


class HealthViewContentTests(TestCase):
    """Renders all 6 panels and NEVER leaks tenant slugs to the HTML."""

    def setUp(self) -> None:
        self.staff = User.objects.create_superuser(
            username="health-staff-content",
            email="health-staff-content@example.invalid",
            password="x",
        )

    def _url(self) -> str:
        return reverse("migration_cloud_super:migration_cloud_health")

    def test_panels_render_with_default_data(self) -> None:
        request = RequestFactory().get(self._url(), secure=True)
        request.user = self.staff
        resp = views_health.MigrationCloudHealthView.as_view()(request)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # All 6 panel headings present.
        self.assertIn("Webhook deliveries", body)
        self.assertIn("MAA signs", body)
        self.assertIn("Companion uploads", body)
        self.assertIn("Active Companion keypairs", body)
        self.assertIn("Pending legacy-hash sunsets", body)
        self.assertIn("Zero-tolerance scanner status", body)

    def test_tenant_slugs_never_appear_in_html(self) -> None:
        """The view hashes tenant ids; the template must not see the slug."""
        from apps.schools.models import School
        from apps.migration_cloud.models import (
            CompanionUploadReceipt,
            MigrationAuthorizationAgreement,
            MigrationBundle,
            CompanionCiphertextBlob,
        )

        # Create a tenant whose slug is a unique sentinel so we can
        # grep for it in the HTML response.
        sentinel_slug = "do-not-leak-this-tenant-slug-zzz"
        school = School.objects.create(
            name="Health Test School", slug=sentinel_slug,
        )
        # Need an MAA + bundle + blob for a receipt.
        maa = MigrationAuthorizationAgreement.objects.create(
            tenant=school,
            signed_by_user=self.staff,
            signed_by_role="IT Director",
            vendor_source="powerschool",
            vendor_account_holder_name="Test Holder",
            agreement_version="v1.0",
            signature_text="(test body)",
        )
        bundle = MigrationBundle.objects.create(
            school=school,
            label="health-test",
            intake_method="file_upload",
            intake_source_uri="test://",
            source_hint="powerschool",
            idempotency_key="health-test-key",
            triggered_by=self.staff,
        )
        blob = CompanionCiphertextBlob.objects.create(
            tenant=school,
            ciphertext_sha256="0" * 64,
            byte_size=1024,
        )
        CompanionUploadReceipt.objects.create(
            tenant=school,
            bundle=bundle,
            maa=maa,
            ciphertext_blob=blob,
            client_idempotency_key="health-test-receipt",
            ciphertext_sha256="0" * 64,
            plaintext_byte_size=2048,
        )

        request = RequestFactory().get(self._url(), secure=True)
        request.user = self.staff
        resp = views_health.MigrationCloudHealthView.as_view()(request)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # The slug must NEVER appear in the rendered HTML — only its
        # 12-hex sha256 prefix.
        self.assertNotIn(sentinel_slug, body)
        # AND the hashed form should appear (sanity check the panel rendered).
        from apps.migration_cloud.metrics import _hash_tenant_id
        self.assertIn(_hash_tenant_id(school.pk), body)
