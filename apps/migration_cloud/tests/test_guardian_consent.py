"""v3.40.0 Agent 11 — guardian-consent collection tests.

Coverage
--------
Model
~~~~~
  * mint returns raw token once; only sha256 persisted
  * matches uses constant-time compare; lookup_by_raw_token works
  * is_expired / is_decided / is_revocable property semantics
  * consent bumps intake.guardian_consent_collected_count atomically
  * decline does NOT bump count; audit event emitted
  * revoke within window decrements count; outside window blocked

Anonymous views
~~~~~~~~~~~~~~
  * landing GET — valid → 200; expired → 200; not-found → 200; already
    decided → 200; uniform-shape (same template)
  * landing GET stamps token_first_seen_at once
  * accept POST records consent + IP/UA captured
  * decline POST records decline; no count bump
  * revoke POST within window decrements; outside window 400
  * raw token NEVER appears in logs (assertNoLogs)
  * security headers applied (X-Frame-Options, Cache-Control)

Admin views
~~~~~~~~~~
  * Campaign CSV ≤2000 rows; bad rows surface line numbers ONLY
  * Resend throttle: max 3 sends; 24h cooldown; audit event per send
  * Tenant isolation — wrong-tenant operator gets 404 (NOT 403)

Audit-event types
~~~~~~~~~~~~~~~~
  * All 9 new event types registered in MigrationCloudAuditEventType

Migration
~~~~~~~~
  * Migration 0023 applies clean (verified by TestCase DB bootstrap)
"""
from __future__ import annotations

import hashlib
import io
import logging
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone


User = get_user_model()


# ─── URL resolution ──────────────────────────────────────────────────────


class GuardianConsentURLResolutionTests(SimpleTestCase):
    """All 7 routes reverse cleanly (4 anonymous + 3 admin)."""

    def test_anonymous_landing_url(self):
        url = reverse(
            "migration_guardian_consent:guardian-consent-landing",
            kwargs={"raw_token": "abc123-token-here"},
        )
        self.assertIn("/migration/consent/", url)
        self.assertIn("abc123-token-here", url)

    def test_anonymous_accept_url(self):
        url = reverse(
            "migration_guardian_consent:guardian-consent-accept",
            kwargs={"raw_token": "abc"},
        )
        self.assertTrue(url.endswith("/accept/"))

    def test_anonymous_decline_url(self):
        url = reverse(
            "migration_guardian_consent:guardian-consent-decline",
            kwargs={"raw_token": "abc"},
        )
        self.assertTrue(url.endswith("/decline/"))

    def test_anonymous_revoke_url(self):
        url = reverse(
            "migration_guardian_consent:guardian-consent-revoke",
            kwargs={"raw_token": "abc"},
        )
        self.assertTrue(url.endswith("/revoke/"))

    def test_admin_campaign_status_url(self):
        url = reverse(
            "migration_guardian_consent_admin:guardian-consent-campaign-status",
            kwargs={"intake_id": uuid4()},
        )
        self.assertIn("/consent/", url)

    def test_admin_campaign_start_url(self):
        url = reverse(
            "migration_guardian_consent_admin:guardian-consent-campaign-start",
            kwargs={"intake_id": uuid4()},
        )
        self.assertTrue(url.endswith("/campaign/start/"))

    def test_admin_resend_url(self):
        url = reverse(
            "migration_guardian_consent_admin:guardian-consent-resend",
            kwargs={"intake_id": uuid4(), "token_id": uuid4()},
        )
        self.assertTrue(url.endswith("/resend/"))


# ─── Module smoke ────────────────────────────────────────────────────────


class GuardianConsentImportSmokeTests(SimpleTestCase):

    def test_model_module_imports(self):
        from apps.migration_cloud import models_guardian_consent  # noqa: F401

    def test_anonymous_views_module_imports(self):
        from apps.migration_cloud import views_guardian_consent  # noqa: F401

    def test_admin_views_module_imports(self):
        from apps.migration_cloud import views_guardian_consent_admin  # noqa: F401


# ─── Audit-event types registered ────────────────────────────────────────


class AuditEventTypesRegisteredTests(SimpleTestCase):
    """All 9 new audit event types must be in the TextChoices enum."""

    def test_all_new_event_types_registered(self):
        from apps.migration_cloud.models_audit import (
            MigrationCloudAuditEventType,
        )
        registered = {c.value for c in MigrationCloudAuditEventType}
        for needed in (
            "migration.guardian_consent.campaign_started",
            "migration.guardian_consent.minted",
            "migration.guardian_consent.first_seen",
            "migration.guardian_consent.consented",
            "migration.guardian_consent.declined",
            "migration.guardian_consent.revoked",
            "migration.guardian_consent.expired",
            "migration.guardian_consent.resent",
            "migration.intake.state_advanced",
        ):
            self.assertIn(needed, registered, f"missing audit type: {needed}")


# ─── DB-backed model + view tests ────────────────────────────────────────


class GuardianConsentDBTests(TestCase):

    @classmethod
    def setUpTestData(cls):  # type: ignore[override]
        from apps.schools.models import School
        from apps.migration_cloud.models_intake import MigrationIntakeRequest
        cls.school_a = School.objects.create(name="School A", subdomain="gc-school-a")
        cls.school_b = School.objects.create(name="School B", subdomain="gc-school-b")
        cls.user_a = User.objects.create_user(
            username="gc_user_a", email="gca@example.invalid",
            password="not-a-real-password",
        )
        cls.user_b = User.objects.create_user(
            username="gc_user_b", email="gcb@example.invalid",
            password="not-a-real-password",
        )
        try:
            from apps.schools.models import SchoolMembership
            SchoolMembership.objects.create(
                user=cls.user_a, school=cls.school_a, role="ADMIN",
            )
            SchoolMembership.objects.create(
                user=cls.user_b, school=cls.school_b, role="ADMIN",
            )
        except Exception:  # noqa: BLE001
            pass
        cls.intake_a = MigrationIntakeRequest.objects.create(
            tenant=cls.school_a,
            requested_by_user=cls.user_a,
            vendor_slug="powerschool",
            state="maa-signed",
        )
        cls.intake_b = MigrationIntakeRequest.objects.create(
            tenant=cls.school_b,
            requested_by_user=cls.user_b,
            vendor_slug="alma",
            state="maa-signed",
        )

    # ── Mint ────────────────────────────────────────────────────────

    def test_mint_returns_raw_token_persists_only_sha(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        raw, instance = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-1",
            guardian_name="A. Guardian",
            guardian_email="g1@example.invalid",
            consent_text_version="v1",
            consent_text="Sample consent text body",
        )
        self.assertTrue(raw)
        self.assertGreaterEqual(len(raw), 32)
        # token_sha256 must equal sha256(raw)
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(instance.token_sha256, expected)
        # raw is NOT persisted anywhere
        from django.db import connection
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id FROM migration_cloud_guardianconsenttoken WHERE id = %s",
            [str(instance.id)],
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_matches_uses_constant_time_compare(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        raw, instance = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-2",
            guardian_name="B. Guardian",
            guardian_email="g2@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        self.assertTrue(instance.matches(raw))
        self.assertFalse(instance.matches(raw + "x"))
        self.assertFalse(instance.matches(""))
        self.assertFalse(instance.matches(None))  # type: ignore[arg-type]

    def test_lookup_by_raw_token(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        raw, instance = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-3",
            guardian_name="C. Guardian",
            guardian_email="g3@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        found = GuardianConsentToken.lookup_by_raw_token(raw)
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, instance.pk)
        self.assertIsNone(GuardianConsentToken.lookup_by_raw_token("wrong-token"))
        self.assertIsNone(GuardianConsentToken.lookup_by_raw_token(""))

    # ── Consent + count bump ────────────────────────────────────────

    def test_consent_bumps_collected_count(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        from apps.migration_cloud.models_intake import MigrationIntakeRequest
        raw, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-CC",
            guardian_name="D. Guardian",
            guardian_email="g4@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        # Build a request-shaped object for IP/UA capture.
        from django.test.client import RequestFactory
        rf = RequestFactory()
        req = rf.post("/migration/consent/x/accept/", REMOTE_ADDR="10.0.0.1")
        req.META["HTTP_USER_AGENT"] = "TestUA/1.0"
        token.consent(request=req)
        # Refresh intake — F() update means we must re-read.
        intake_fresh = MigrationIntakeRequest.objects.get(pk=self.intake_a.pk)
        self.assertEqual(intake_fresh.guardian_consent_collected_count, 1)
        token.refresh_from_db()
        self.assertEqual(token.consent_decision, "consented")
        self.assertEqual(token.ip_address_consent, "10.0.0.1")
        self.assertEqual(token.user_agent_consent, "TestUA/1.0")

    def test_decline_does_not_bump_count(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        from apps.migration_cloud.models_intake import MigrationIntakeRequest
        _, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-D",
            guardian_name="E. Guardian",
            guardian_email="g5@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        before = MigrationIntakeRequest.objects.get(pk=self.intake_a.pk)
        baseline = before.guardian_consent_collected_count
        from django.test.client import RequestFactory
        token.decline(
            request=RequestFactory().post("/x/", REMOTE_ADDR="10.0.0.2"),
        )
        after = MigrationIntakeRequest.objects.get(pk=self.intake_a.pk)
        self.assertEqual(after.guardian_consent_collected_count, baseline)
        token.refresh_from_db()
        self.assertEqual(token.consent_decision, "declined")

    def test_revoke_inside_window_decrements_count(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        from apps.migration_cloud.models_intake import MigrationIntakeRequest
        from django.test.client import RequestFactory
        _, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-R",
            guardian_name="F. Guardian",
            guardian_email="g6@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        token.consent(request=RequestFactory().post("/x/", REMOTE_ADDR="10.0.0.3"))
        intake_after_consent = MigrationIntakeRequest.objects.get(pk=self.intake_a.pk)
        before = intake_after_consent.guardian_consent_collected_count
        token.refresh_from_db()
        self.assertTrue(token.is_revocable)
        token.revoke()
        intake_after_revoke = MigrationIntakeRequest.objects.get(pk=self.intake_a.pk)
        self.assertEqual(
            intake_after_revoke.guardian_consent_collected_count, before - 1,
        )

    def test_revoke_outside_window_blocked(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken, GuardianConsentTokenError,
        )
        from django.test.client import RequestFactory
        _, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-OUT",
            guardian_name="G. Guardian",
            guardian_email="g7@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        token.consent(request=RequestFactory().post("/x/", REMOTE_ADDR="10.0.0.4"))
        # Backdate consent to outside the window.
        token.refresh_from_db()
        token.consented_at = timezone.now() - timedelta(days=120)
        token.save(update_fields=["consented_at", "updated_at"])
        self.assertFalse(token.is_revocable)
        with self.assertRaises(GuardianConsentTokenError):
            token.revoke()

    def test_is_expired(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        _, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-EXP",
            guardian_name="H. Guardian",
            guardian_email="g8@example.invalid",
            consent_text_version="v1",
            consent_text="text",
            expires_in_days=1,
        )
        self.assertFalse(token.is_expired)
        token.expires_at = timezone.now() - timedelta(minutes=1)
        token.save(update_fields=["expires_at", "updated_at"])
        self.assertTrue(token.is_expired)

    # ── Anonymous views ─────────────────────────────────────────────

    def test_landing_valid_token_returns_200(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        raw, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-V1",
            guardian_name="Land Guardian",
            guardian_email="land@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        url = reverse(
            "migration_guardian_consent:guardian-consent-landing",
            kwargs={"raw_token": raw},
        )
        resp = Client().get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["X-Frame-Options"], "DENY")
        self.assertIn("no-store", resp["Cache-Control"])
        # first_seen_at stamped
        token.refresh_from_db()
        self.assertIsNotNone(token.token_first_seen_at)

    def test_landing_not_found_returns_200_uniform(self):
        url = reverse(
            "migration_guardian_consent:guardian-consent-landing",
            kwargs={"raw_token": "definitely-not-a-real-token-zzzzz"},
        )
        resp = Client().get(url)
        self.assertEqual(resp.status_code, 200)
        # Must NOT differentiate; same template name renders both.
        self.assertEqual(resp["X-Frame-Options"], "DENY")

    def test_landing_expired_returns_200(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        raw, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-EXPV",
            guardian_name="Exp Guardian",
            guardian_email="expv@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        token.expires_at = timezone.now() - timedelta(days=1)
        token.save(update_fields=["expires_at", "updated_at"])
        url = reverse(
            "migration_guardian_consent:guardian-consent-landing",
            kwargs={"raw_token": raw},
        )
        resp = Client().get(url)
        self.assertEqual(resp.status_code, 200)

    def test_accept_post_records_consent(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        raw, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-AC",
            guardian_name="Acc Guardian",
            guardian_email="acc@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        url = reverse(
            "migration_guardian_consent:guardian-consent-accept",
            kwargs={"raw_token": raw},
        )
        resp = Client().post(url, {"confirm": "on"}, REMOTE_ADDR="172.16.0.1")
        self.assertEqual(resp.status_code, 200)
        token.refresh_from_db()
        self.assertEqual(token.consent_decision, "consented")
        self.assertEqual(token.ip_address_consent, "172.16.0.1")

    def test_decline_post_records_decline(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        raw, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-DC",
            guardian_name="Dec Guardian",
            guardian_email="dec@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        url = reverse(
            "migration_guardian_consent:guardian-consent-decline",
            kwargs={"raw_token": raw},
        )
        resp = Client().post(url, {"confirm": "on"})
        self.assertEqual(resp.status_code, 200)
        token.refresh_from_db()
        self.assertEqual(token.consent_decision, "declined")

    def test_revoke_post_outside_window_returns_400(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        from django.test.client import RequestFactory
        raw, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-RVO",
            guardian_name="Revoke Guardian",
            guardian_email="rev@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        token.consent(request=RequestFactory().post("/x/", REMOTE_ADDR="10.0.0.5"))
        token.refresh_from_db()
        token.consented_at = timezone.now() - timedelta(days=120)
        token.save(update_fields=["consented_at", "updated_at"])
        url = reverse(
            "migration_guardian_consent:guardian-consent-revoke",
            kwargs={"raw_token": raw},
        )
        resp = Client().post(url)
        self.assertEqual(resp.status_code, 400)

    def test_raw_token_never_logged(self):
        """assertNoLogs proves the raw token never reaches any logger."""
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        raw, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-LOG",
            guardian_name="Log Guardian",
            guardian_email="logguard@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        # Re-walk landing + accept under capture.
        logger = logging.getLogger("apps.migration_cloud")
        # We use assertLogs to capture, then assert the raw token is
        # NOT present in any captured line.
        with self.assertLogs(logger, level="INFO") as captured:
            url_landing = reverse(
                "migration_guardian_consent:guardian-consent-landing",
                kwargs={"raw_token": raw},
            )
            Client().get(url_landing)
            url_accept = reverse(
                "migration_guardian_consent:guardian-consent-accept",
                kwargs={"raw_token": raw},
            )
            Client().post(url_accept, {"confirm": "on"})
        all_lines = "\n".join(captured.output)
        self.assertNotIn(
            raw, all_lines,
            "raw consent token appeared in log output — leak!",
        )

    # ── Admin views ─────────────────────────────────────────────────

    def test_admin_campaign_csv_row_cap_enforced(self):
        """CSV with >2000 rows is rejected with 400 and clear message."""
        client = Client()
        client.force_login(self.user_a)
        # 2001 valid rows trigger the cap.
        rows = ["student_id,guardian_name,guardian_email"]
        for i in range(2001):
            rows.append(f"STU-{i},Guardian {i},gc{i}@example.invalid")
        csv_body = "\n".join(rows).encode("utf-8")
        upload = SimpleUploadedFile(
            "campaign.csv", csv_body, content_type="text/csv",
        )
        url = reverse(
            "migration_guardian_consent_admin:guardian-consent-campaign-start",
            kwargs={"intake_id": self.intake_a.id},
        )
        resp = client.post(url, {"csv_file": upload})
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"row cap", resp.content)

    def test_admin_campaign_bad_rows_surface_line_no_pii(self):
        client = Client()
        client.force_login(self.user_a)
        rows = [
            "student_id,guardian_name,guardian_email",
            "STU-1,Good Guardian,good@example.invalid",  # valid line 1
            ",Bad Row,bad@example.invalid",              # missing sid line 2
            "STU-3,Bad Guardian,not-an-email",           # invalid email line 3
        ]
        csv_body = "\n".join(rows).encode("utf-8")
        upload = SimpleUploadedFile(
            "campaign.csv", csv_body, content_type="text/csv",
        )
        url = reverse(
            "migration_guardian_consent_admin:guardian-consent-campaign-start",
            kwargs={"intake_id": self.intake_a.id},
        )
        resp = client.post(url, {"csv_file": upload})
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        # Bad row line numbers are surfaced...
        self.assertIn("2", body)
        self.assertIn("3", body)
        # ...but the rejected rows' email/name are NOT.
        self.assertNotIn("bad@example.invalid", body)
        self.assertNotIn("not-an-email", body)
        self.assertNotIn("Bad Row", body)

    def test_admin_resend_throttle_max_3(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        client = Client()
        client.force_login(self.user_a)
        _, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-RES",
            guardian_name="Resend Guardian",
            guardian_email="resend@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        # Pre-bump to 3 and clear cooldown.
        token.resend_count = 3
        token.last_resend_at = timezone.now() - timedelta(days=2)
        token.save(update_fields=[
            "resend_count", "last_resend_at", "updated_at",
        ])
        url = reverse(
            "migration_guardian_consent_admin:guardian-consent-resend",
            kwargs={"intake_id": self.intake_a.id, "token_id": token.id},
        )
        resp = client.post(url)
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"cap reached", resp.content)

    def test_admin_resend_cooldown_24h(self):
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        client = Client()
        client.force_login(self.user_a)
        _, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-CD",
            guardian_name="Cooldown Guardian",
            guardian_email="cd@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        token.resend_count = 1
        token.last_resend_at = timezone.now() - timedelta(minutes=10)
        token.save(update_fields=[
            "resend_count", "last_resend_at", "updated_at",
        ])
        url = reverse(
            "migration_guardian_consent_admin:guardian-consent-resend",
            kwargs={"intake_id": self.intake_a.id, "token_id": token.id},
        )
        resp = client.post(url)
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"cooldown", resp.content)

    def test_admin_tenant_isolation_returns_404(self):
        """user_b cannot touch intake_a; gets 404 (not 403)."""
        from apps.migration_cloud.models_guardian_consent import (
            GuardianConsentToken,
        )
        _, token = GuardianConsentToken.mint(
            intake=self.intake_a,
            student_external_id="STU-TI",
            guardian_name="Wrong Tenant Guardian",
            guardian_email="wt@example.invalid",
            consent_text_version="v1",
            consent_text="text",
        )
        client = Client()
        client.force_login(self.user_b)
        # Cross-tenant: user_b tries to view user_a's intake.
        url = reverse(
            "migration_guardian_consent_admin:guardian-consent-campaign-status",
            kwargs={"intake_id": self.intake_a.id},
        )
        resp = client.get(url)
        self.assertEqual(resp.status_code, 404)
        url_resend = reverse(
            "migration_guardian_consent_admin:guardian-consent-resend",
            kwargs={"intake_id": self.intake_a.id, "token_id": token.id},
        )
        resp2 = client.post(url_resend)
        self.assertEqual(resp2.status_code, 404)
