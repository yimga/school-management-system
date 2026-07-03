"""Transfer Wave B — guardian consent artifact + anonymous consent pages.

Locks the GuardianConsentToken discipline on TransferConsent: raw token
returned once and never persisted (sha256 only, constant-time compare),
immutable consent-text hash, decision FSM with expiry, and the case-FSM
coupling (consent → APPROVED, decline → CANCELLED). The anonymous pages
must be anti-enumeration uniform.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.people.models import StudentProfile
from apps.people.models_transfer import TransferCase
from apps.people.models_transfer_consent import (
    TransferConsent,
    TransferConsentDecision,
    TransferConsentError,
)
from apps.schools.models import School


class TransferConsentModelTests(TestCase):
    def setUp(self):
        self.source = School.objects.create(
            name="Consent Src", slug="consent-src", subdomain="consent-src"
        )
        self.target = School.objects.create(
            name="Consent Tgt", slug="consent-tgt", subdomain="consent-tgt"
        )
        self.profile = StudentProfile.objects.create(
            school=self.source,
            first_name="Con",
            last_name="Sent",
            student_code="CS-001",
        )
        self.case = TransferCase.objects.create(
            source_school=self.source,
            target_school=self.target,
            source_profile_pk=str(self.profile.pk),
        )
        self.case.advance(TransferCase.Status.CONSENT_PENDING)

    def _mint(self, **overrides):
        kwargs = {
            "case": self.case,
            "guardian_name": "Guard Ian",
            "guardian_email": "guardian@example.com",
            "consent_text_version": "v1",
            "consent_text": "consent body v1",
        }
        kwargs.update(overrides)
        return TransferConsent.mint(**kwargs)

    def test_mint_persists_hash_only(self):
        raw, consent = self._mint()
        self.assertEqual(len(consent.token_sha256), 64)
        self.assertNotEqual(consent.token_sha256, raw)
        self.assertTrue(consent.matches(raw))
        self.assertFalse(consent.matches(raw + "x"))
        found = TransferConsent.lookup_by_raw_token(raw)
        self.assertEqual(found.pk, consent.pk)
        self.assertIsNone(TransferConsent.lookup_by_raw_token("not-a-real-token-xx"))

    def test_consent_advances_case_to_approved(self):
        _raw, consent = self._mint()
        consent.consent()
        consent.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(consent.decision, TransferConsentDecision.CONSENTED)
        self.assertEqual(self.case.status, TransferCase.Status.APPROVED)
        self.assertEqual(self.case.consent_reference, str(consent.pk))

    def test_decline_cancels_case(self):
        _raw, consent = self._mint()
        consent.decline()
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, TransferCase.Status.CANCELLED)

    def test_double_decision_refused(self):
        _raw, consent = self._mint()
        consent.consent()
        with self.assertRaises(TransferConsentError):
            consent.decline()

    def test_expired_token_refused_and_marked(self):
        _raw, consent = self._mint()
        consent.expires_at = timezone.now() - timedelta(minutes=1)
        consent.save(update_fields=["expires_at"])
        with self.assertRaises(TransferConsentError):
            consent.consent()
        consent.refresh_from_db()
        self.assertEqual(consent.decision, TransferConsentDecision.EXPIRED)


class TransferConsentPageTests(TestCase):
    def setUp(self):
        self.source = School.objects.create(
            name="Page Src", slug="page-src", subdomain="page-src"
        )
        self.target = School.objects.create(
            name="Page Tgt", slug="page-tgt", subdomain="page-tgt"
        )
        profile = StudentProfile.objects.create(
            school=self.source,
            first_name="Page",
            last_name="Kid",
            student_code="PG-001",
        )
        self.case = TransferCase.objects.create(
            source_school=self.source,
            target_school=self.target,
            source_profile_pk=str(profile.pk),
        )
        self.case.advance(TransferCase.Status.CONSENT_PENDING)
        self.raw, self.consent = TransferConsent.mint(
            case=self.case,
            guardian_name="Guard Ian",
            guardian_email="guardian@example.com",
            consent_text_version="v1",
            consent_text="consent body v1",
        )

    def test_landing_valid_token_shows_form_and_marks_first_seen(self):
        url = reverse("people_transfer_consent_landing")
        response = self.client.get(url, {"token": self.raw})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "I consent")
        self.consent.refresh_from_db()
        self.assertIsNotNone(self.consent.token_first_seen_at)

    def test_token_page_never_cached_and_no_referrer(self):
        """The landing holds the LIVE token — anti-cache + no-referrer are
        the GuardianConsentToken containment discipline."""
        url = reverse("people_transfer_consent_landing")
        response = self.client.get(url, {"token": self.raw})
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertEqual(response["Pragma"], "no-cache")
        decided = self.client.post(
            reverse("people_transfer_consent_decide"),
            {"token": self.raw, "choice": "decline"},
        )
        self.assertIn("no-store", decided["Cache-Control"])

    def test_decision_ip_prefers_x_forwarded_for(self):
        """Behind the proxy REMOTE_ADDR is the load balancer — the consent
        evidence must record the guardian's IP from XFF."""
        url = reverse("people_transfer_consent_decide")
        response = self.client.post(
            url,
            {"token": self.raw, "choice": "consent"},
            HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        self.consent.refresh_from_db()
        self.assertEqual(self.consent.ip_address_decision, "203.0.113.7")

    def test_landing_invalid_token_uniform_200(self):
        url = reverse("people_transfer_consent_landing")
        response = self.client.get(url, {"token": "bogus-token-bogus-token"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "I consent to this transfer")

    def test_decide_consent_approves_case(self):
        url = reverse("people_transfer_consent_decide")
        response = self.client.post(url, {"token": self.raw, "choice": "consent"})
        self.assertEqual(response.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, TransferCase.Status.APPROVED)

    def test_decide_bad_token_uniform_200(self):
        url = reverse("people_transfer_consent_decide")
        response = self.client.post(
            url, {"token": "bogus-token-bogus-token", "choice": "consent"}
        )
        self.assertEqual(response.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, TransferCase.Status.CONSENT_PENDING)
