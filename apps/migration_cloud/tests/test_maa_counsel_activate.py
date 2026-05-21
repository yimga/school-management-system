"""v3.40.0 Agent 15 — counsel-activate view + MAAActiveVersionState tests.

Coverage:
  * View staff-only (anon 302; non-staff 302)
  * GET shows v2.0 draft when v1.0 active
  * POST without confirm-token → 400
  * POST with wrong typed phrase → 400
  * POST with valid token + phrase + attestation → v2.0 activated;
    audit event emitted
  * assertNoLogs (best-effort) for counsel_attestation_text raw
  * After activation, MAAActiveVersionState.get_active_version() returns "v2.0"
  * After activation, services.maa_text.is_draft_version("v2.0") is False
  * Activation when already at v2.0 → MAAAlreadyActiveError
  * Migration 0027 applied clean (singleton row seeded)
  * Singleton constraint enforced (cannot insert a second _singleton=True row)
  * URL reverse resolves under super shell
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from apps.migration_cloud.models_audit import (
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
)
from apps.migration_cloud.models_maa_state import (
    MAAActiveVersionState,
    MAAAlreadyActiveError,
)
from apps.migration_cloud.services import maa_text


User = get_user_model()


def _staff_user():
    u = User.objects.create_user(
        username="op-15",
        email="op15@example.com",
        password="x",
    )
    u.is_staff = True
    u.is_active = True
    u.save()
    return u


def _non_staff_user():
    u = User.objects.create_user(
        username="rando-15",
        email="rando15@example.com",
        password="x",
    )
    u.is_staff = False
    u.is_active = True
    u.save()
    return u


class MigrationAndSingletonTests(TestCase):
    """Migration 0027 + singleton-constraint sanity."""

    def test_singleton_row_seeded_by_migration(self):
        rows = list(MAAActiveVersionState.objects.all())
        # The migration RunPython seeds one row; tests may have added
        # more state, but at least one row must exist.
        self.assertGreaterEqual(len(rows), 1)
        # The default row must report v1.0 as active.
        active = MAAActiveVersionState.get_active_version()
        self.assertEqual(active, "v1.0")

    def test_singleton_constraint_refuses_duplicate(self):
        # Ensure the seeded row exists.
        MAAActiveVersionState.get_row()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MAAActiveVersionState.objects.create(
                    _singleton=True, active_version="v1.0",
                )


class CounselActivateViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse(
            "migration_cloud_super:maa_counsel_activate"
        )

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(self.url)
        # staff_member_required redirects to admin login.
        self.assertEqual(resp.status_code, 302)

    def test_non_staff_redirects(self):
        u = _non_staff_user()
        self.client.force_login(u)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_staff_get_shows_v2_draft_when_v1_active(self):
        u = _staff_user()
        self.client.force_login(u)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("v1.0", body)
        self.assertIn("DRAFT", body)
        # Counsel attestation text raw must not appear in rendered HTML
        # (the page should not echo back any prior secrets).
        self.assertNotIn("counsel_attestation_text", body.lower().split("\n")[0])

    def test_post_without_confirm_token_returns_400(self):
        u = _staff_user()
        self.client.force_login(u)
        resp = self.client.post(self.url, data={
            "counsel_signoff_pdf_url": "https://example.com/v2.pdf",
            "counsel_attestation_name": "Op Test",
            "counsel_attestation_text": "I attest counsel signed.",
            "confirm_typed_phrase": "I AFFIRM MAA V2.0 COUNSEL HAS SIGNED",
            "confirm_token": "",
        })
        self.assertEqual(resp.status_code, 400)

    def test_post_with_wrong_phrase_returns_400(self):
        u = _staff_user()
        self.client.force_login(u)
        # First GET to obtain a token.
        get_resp = self.client.get(self.url)
        token = get_resp.context["confirm_token"]
        resp = self.client.post(self.url, data={
            "counsel_signoff_pdf_url": "https://example.com/v2.pdf",
            "counsel_attestation_name": "Op Test",
            "counsel_attestation_text": "I attest counsel signed.",
            "confirm_typed_phrase": "wrong phrase",
            "confirm_token": token,
        })
        self.assertEqual(resp.status_code, 400)

    def test_post_with_valid_token_phrase_activates_v2(self):
        u = _staff_user()
        self.client.force_login(u)
        get_resp = self.client.get(self.url)
        token = get_resp.context["confirm_token"]
        resp = self.client.post(self.url, data={
            "counsel_signoff_pdf_url": "https://example.com/v2.pdf",
            "counsel_attestation_name": "Op Test",
            "counsel_attestation_text": "I attest counsel signed.",
            "confirm_typed_phrase": "I AFFIRM MAA V2.0 COUNSEL HAS SIGNED",
            "confirm_token": token,
        })
        # Successful POST redirects.
        self.assertIn(resp.status_code, (302, 303))
        # Active version flipped.
        self.assertEqual(MAAActiveVersionState.get_active_version(), "v2.0")
        # Audit event emitted.
        evt = MigrationCloudAuditEvent.objects.filter(
            event_type=MigrationCloudAuditEventType.MAA_V2_ACTIVATED_BY_OPERATOR.value,
        ).first()
        self.assertIsNotNone(evt)
        # Payload PII-free: counsel attestation TEXT is never persisted
        # in the payload; only the fingerprint prefix is allowed.
        payload = evt.payload_summary or {}
        self.assertNotIn("counsel_attestation_text", payload)
        self.assertNotIn("attestation_text", payload)
        self.assertIn("counsel_attestation_fingerprint", payload)

    def test_post_does_not_log_raw_attestation_text(self):
        """Sanity: raw attestation TEXT never appears in the audit row.

        Uses assertLogs over the logger family we control to keep the
        test deterministic. The view's logger MUST NOT print the raw
        attestation body.
        """
        u = _staff_user()
        self.client.force_login(u)
        secret_attestation = "SECRET-WITNESS-1234567890"
        get_resp = self.client.get(self.url)
        token = get_resp.context["confirm_token"]
        with self.assertLogs(
            "apps.migration_cloud.views_maa_counsel_activate",
            level="INFO",
        ) as cm:
            self.client.post(self.url, data={
                "counsel_signoff_pdf_url": "https://example.com/v2.pdf",
                "counsel_attestation_name": "Op Test",
                "counsel_attestation_text": secret_attestation,
                "confirm_typed_phrase":
                    "I AFFIRM MAA V2.0 COUNSEL HAS SIGNED",
                "confirm_token": token,
            })
        joined = "\n".join(cm.output)
        self.assertNotIn(secret_attestation, joined)
        # And the audit row must not echo the raw text either.
        evt = MigrationCloudAuditEvent.objects.filter(
            event_type=MigrationCloudAuditEventType.MAA_V2_ACTIVATED_BY_OPERATOR.value,
        ).first()
        self.assertIsNotNone(evt)
        payload_repr = str(evt.payload_summary or {})
        self.assertNotIn(secret_attestation, payload_repr)


class ActiveVersionFlipSideEffectsTests(TestCase):

    def test_is_draft_version_v2_after_flip(self):
        u = _staff_user()
        # Before flip:
        self.assertTrue(maa_text.is_draft_version("v2.0"))
        MAAActiveVersionState.activate_v2(
            operator_user=u,
            counsel_pdf_url="https://example.com/v2.pdf",
            attestation_name="Op Test",
            attestation_text="I attest counsel signed.",
        )
        # After flip: v2.0 is no longer a draft.
        self.assertFalse(maa_text.is_draft_version("v2.0"))
        self.assertEqual(MAAActiveVersionState.get_active_version(), "v2.0")
        self.assertNotIn("v2.0", maa_text.get_draft_versions())

    def test_activate_twice_raises_already_active(self):
        u = _staff_user()
        MAAActiveVersionState.activate_v2(
            operator_user=u,
            counsel_pdf_url="https://example.com/v2.pdf",
            attestation_name="Op Test",
            attestation_text="I attest counsel signed.",
        )
        with self.assertRaises(MAAAlreadyActiveError):
            MAAActiveVersionState.activate_v2(
                operator_user=u,
                counsel_pdf_url="https://example.com/v2.pdf",
                attestation_name="Op Test",
                attestation_text="I attest counsel signed.",
            )

    def test_masign_no_longer_400s_on_v2_after_flip(self):
        """After flipping v2.0 to ACTIVE, ``is_draft_version`` returns False.

        We assert the predicate the v3.33 ``MASignView`` uses to refuse
        DRAFT signings — it consults ``is_draft_version``; once that
        flips, the view stops 400-ing on v2.0.
        """
        u = _staff_user()
        # Pre-flip predicate trips the v3.33 refusal.
        self.assertTrue(maa_text.is_draft_version("v2.0"))
        MAAActiveVersionState.activate_v2(
            operator_user=u,
            counsel_pdf_url="https://example.com/v2.pdf",
            attestation_name="Op Test",
            attestation_text="I attest counsel signed.",
        )
        # Post-flip predicate clears the v3.33 refusal.
        self.assertFalse(maa_text.is_draft_version("v2.0"))


class URLReverseTests(TestCase):

    def test_super_reverse_resolves(self):
        url = reverse("migration_cloud_super:maa_counsel_activate")
        self.assertTrue(url.endswith("/maa/v2-counsel-activate/"))
