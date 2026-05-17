"""HTTP-surface tests for the Migration Cloud intake wizard.

Locks down the reliability properties of ``MigrationCloudIntakeView`` —
the one user-visible entry point for "I have something to migrate."
Covers: GET renders, POST upload creates a bundle, idempotent double-
submit collapses to one bundle, empty-file uploads are rejected, URL
intake validates scheme, pending-method stages a bundle without an
adapter dispatch.

These tests are pure SimpleTestCase + Django test client; no live DB
beyond the model layer, no Celery, no network.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle


def _operator(email: str = "ops@example.com"):
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username=email,
        defaults={"email": email, "is_staff": True, "is_superuser": True},
    )
    user.set_password("x")
    user.save()
    return user


class IntakeWizardGetTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)

    def test_get_renders_wizard(self) -> None:
        url = reverse("migration_cloud_super:bundle_new")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Start a new migration")
        self.assertContains(resp, 'name="intake_method"')
        # Source-hint must be explicitly optional with a "leave blank" affordance.
        self.assertContains(resp, "source_hint")


class IntakeWizardUploadPostTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("migration_cloud_super:bundle_new")

    def _post(self, **overrides):
        payload = {
            "intake_method": IntakeMethod.FILE_UPLOAD,
            "label": "test bundle",
            "source_hint": "",  # blank — exercises the unknown_custom path
            "sla_tier": "small",
            "auto_advance": "",  # disabled in tests to keep them deterministic
        }
        payload.update(overrides)
        return self.client.post(self.url, data=payload)

    def test_upload_creates_bundle_and_redirects_to_detail(self) -> None:
        file_obj = SimpleUploadedFile("students.csv", b"id,name\n1,Ada\n", content_type="text/csv")
        resp = self._post(artifacts=file_obj)
        self.assertEqual(resp.status_code, 302)
        # 302 target must be the bundle detail page.
        self.assertIn("/super/migration/", resp["Location"])
        # Exactly one bundle exists, INGESTING after artifact landed.
        bundle = MigrationBundle.objects.get()
        self.assertEqual(bundle.intake_method, IntakeMethod.FILE_UPLOAD)
        self.assertEqual(bundle.artifacts.count(), 1)
        self.assertEqual(bundle.status, BundleStatus.INGESTING)

    def test_double_submit_collapses_to_one_bundle(self) -> None:
        """Same operator + same payload twice → one bundle row.

        Validates the deterministic idempotency key derived from file
        sha256s. Double-click / browser-retry must not produce duplicates.
        """
        # First submit takes the cache lock + creates the bundle.
        file_obj_1 = SimpleUploadedFile("dedup.csv", b"id\n1\n", content_type="text/csv")
        resp1 = self._post(artifacts=file_obj_1)
        self.assertEqual(resp1.status_code, 302)
        first_count = MigrationBundle.objects.count()
        self.assertEqual(first_count, 1)

        # Cache lock must be released by the end of the first request so
        # the legitimate retry is allowed (idempotency-key collapse, not
        # lock rejection).
        file_obj_2 = SimpleUploadedFile("dedup.csv", b"id\n1\n", content_type="text/csv")
        resp2 = self._post(artifacts=file_obj_2)
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(MigrationBundle.objects.count(), 1)

    def test_empty_file_rejected(self) -> None:
        empty = SimpleUploadedFile("empty.csv", b"", content_type="text/csv")
        resp = self._post(artifacts=empty)
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "non-empty", status_code=400)
        self.assertEqual(MigrationBundle.objects.count(), 0)

    def test_missing_files_rejected(self) -> None:
        resp = self._post()  # no artifacts attached
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(MigrationBundle.objects.count(), 0)


class IntakeWizardUrlAndPendingPostTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("migration_cloud_super:bundle_new")

    def test_url_intake_rejects_unsupported_scheme(self) -> None:
        resp = self.client.post(self.url, data={
            "intake_method": IntakeMethod.URL,
            "intake_source_uri": "ftp://example.com/file.zip",  # scheme not supported
            "sla_tier": "small",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "http://", status_code=400)
        self.assertEqual(MigrationBundle.objects.count(), 0)

    def test_url_intake_requires_uri(self) -> None:
        resp = self.client.post(self.url, data={
            "intake_method": IntakeMethod.URL,
            "intake_source_uri": "",
            "sla_tier": "small",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(MigrationBundle.objects.count(), 0)

    def test_pending_method_stages_bundle_without_adapter(self) -> None:
        """OAuth folder / database / mailbox / API methods create the row
        for follow-up wiring without invoking an adapter."""
        resp = self.client.post(self.url, data={
            "intake_method": IntakeMethod.OAUTH_FOLDER,
            "sla_tier": "small",
            "source_hint": "custom",
        })
        self.assertEqual(resp.status_code, 302)
        bundle = MigrationBundle.objects.get()
        self.assertEqual(bundle.intake_method, IntakeMethod.OAUTH_FOLDER)
        # Pending bundles stay PENDING (no adapter ran) — operator wires
        # the credentials from the detail page.
        self.assertEqual(bundle.status, BundleStatus.PENDING)
        self.assertEqual(bundle.artifacts.count(), 0)


class ApplyDryRunGateTests(TestCase):
    """The /apply/ endpoint must default to dry-run unless ?confirm=1 is set.

    Without this contract, an API-misuse / browser-replay could WRITE to
    a live tenant. The UI's 'Apply (live)' button always sends ?confirm=1
    plus a JS confirm() prompt; the API just enforces the gate.
    """

    def setUp(self) -> None:
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)
        # Create a MAPPED bundle to exercise the apply gate.
        self.bundle = MigrationBundle.objects.create(
            label="apply gate test",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="apply-gate-test",
            status=BundleStatus.MAPPED,
        )

    def test_apply_without_confirm_defaults_to_dry_run(self) -> None:
        url = reverse("migration_cloud_super:bundle_apply", kwargs={"bundle_id": self.bundle.pk})
        resp = self.client.post(url)  # no ?confirm, no ?dry_run
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("dry_run"), f"expected dry_run=True by default, got {data}")

    def test_apply_with_explicit_dry_run_stays_dry_run(self) -> None:
        url = reverse("migration_cloud_super:bundle_apply", kwargs={"bundle_id": self.bundle.pk})
        resp = self.client.post(url + "?dry_run=1&confirm=1")  # dry_run wins over confirm
        data = resp.json()
        self.assertTrue(data.get("dry_run"))

    def test_apply_with_confirm_goes_live(self) -> None:
        url = reverse("migration_cloud_super:bundle_apply", kwargs={"bundle_id": self.bundle.pk})
        resp = self.client.post(url + "?confirm=1")
        data = resp.json()
        self.assertFalse(data.get("dry_run"))


class IntakeWizardCustomSourceHintTests(TestCase):
    """The user's primary scenario: migrating from a custom in-house
    product not present in the classifier's known-vendor list."""

    def setUp(self) -> None:
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)

    def test_custom_source_hint_lands_cleanly(self) -> None:
        url = reverse("migration_cloud_super:bundle_new")
        file_obj = SimpleUploadedFile(
            "custom_export.csv",
            b"student_id_internal,full_legal_name,homeroom\n42,Ada Lovelace,7A\n",
            content_type="text/csv",
        )
        resp = self.client.post(url, data={
            "intake_method": IntakeMethod.FILE_UPLOAD,
            "label": "Custom in-house SIS migration",
            "source_hint": "custom",  # not a known competitor — exercises unknown_custom
            "sla_tier": "small",
            "artifacts": file_obj,
        })
        self.assertEqual(resp.status_code, 302)
        bundle = MigrationBundle.objects.get()
        self.assertEqual(bundle.source_hint, "custom")
        self.assertEqual(bundle.artifacts.count(), 1)
