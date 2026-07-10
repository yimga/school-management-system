"""Participation-consent token discipline + membership transitions.

Mirrors the people.TransferConsent discipline: the raw token is returned once
from ``mint`` and only its sha256 is persisted; a wrong token never resolves;
``.consent()`` activates a PENDING membership; ``.decline()`` marks it LEFT; an
expired/decided token cannot be re-decided.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.athletics.models import (
    ParticipationConsent,
    ParticipationConsentDecision,
    ParticipationConsentError,
    TeamMembership,
)
from apps.athletics.services.consent import (
    record_consent_decision,
    request_participation_consent,
)
from apps.athletics.services.eligibility import resolve_eligibility
from apps.athletics.tests.base import BaseAthleticsTestCase


class ConsentTokenTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.membership = self.add_member(
            self.fx, status=TeamMembership.Status.PENDING
        )

    def _mint(self):
        return ParticipationConsent.mint(
            membership=self.membership,
            guardian_name="Parent",
            guardian_email="parent@example.com",
            consent_text="I consent to participation.",
        )

    def test_raw_token_returned_once_only_sha_persisted(self):
        import hashlib

        raw, consent = self._mint()
        self.assertTrue(raw)
        self.assertEqual(
            consent.token_sha256, hashlib.sha256(raw.encode("utf-8")).hexdigest()
        )
        # The raw token is not stored in any persisted string field.
        consent.refresh_from_db()
        self.assertNotEqual(consent.token_sha256, raw)
        self.assertNotIn(raw, (consent.guardian_name, consent.guardian_email))

    def test_lookup_by_raw_token_finds_and_rejects(self):
        raw, consent = self._mint()
        found = ParticipationConsent.lookup_by_raw_token(raw)
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, consent.pk)
        self.assertTrue(found.matches(raw))
        # A wrong token does not resolve.
        self.assertIsNone(
            ParticipationConsent.lookup_by_raw_token("not-the-real-token-value-xyz")
        )
        self.assertFalse(consent.matches("wrong-token-value-abcdef"))

    def test_consent_activates_pending_membership(self):
        raw, consent = self._mint()
        consent.consent()
        consent.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertEqual(consent.decision, ParticipationConsentDecision.CONSENTED)
        self.assertEqual(self.membership.status, TeamMembership.Status.ACTIVE)
        self.assertIsNotNone(self.membership.joined_at)

    def test_decline_marks_membership_left(self):
        raw, consent = self._mint()
        consent.decline()
        consent.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertEqual(consent.decision, ParticipationConsentDecision.DECLINED)
        self.assertEqual(self.membership.status, TeamMembership.Status.LEFT)
        self.assertIsNotNone(self.membership.left_at)

    def test_cannot_redecide_a_decided_token(self):
        raw, consent = self._mint()
        consent.consent()
        with self.assertRaises(ParticipationConsentError):
            consent.decline()

    def test_expired_token_cannot_be_consented_and_marks_expired(self):
        raw, consent = self._mint()
        consent.expires_at = timezone.now() - timedelta(days=1)
        consent.save(update_fields=["expires_at"])
        with self.assertRaises(ParticipationConsentError):
            consent.consent()
        consent.refresh_from_db()
        self.assertEqual(consent.decision, ParticipationConsentDecision.EXPIRED)
        # Membership stays PENDING (never activated).
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, TeamMembership.Status.PENDING)

    def test_expired_undecided_consent_does_not_satisfy_eligibility(self):
        # An expired, undecided consent leaves decision=PENDING, so the
        # eligibility CONSENTED predicate returns False.
        raw, consent = self._mint()
        consent.expires_at = timezone.now() - timedelta(days=1)
        consent.save(update_fields=["expires_at"])
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertFalse(outcome.record.consent_ok)


class ConsentServiceTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.membership = self.add_member(
            self.fx, status=TeamMembership.Status.PENDING
        )

    def test_request_participation_consent_returns_raw_token(self):
        raw = request_participation_consent(
            membership=self.membership,
            guardian_name="Guardian",
            guardian_email="guardian@example.com",
            consent_text="Consent text.",
        )
        self.assertTrue(raw)
        # The service persisted a consent resolvable by the returned raw token.
        found = ParticipationConsent.lookup_by_raw_token(raw)
        self.assertIsNotNone(found)
        self.assertEqual(found.membership_id, self.membership.pk)

    def test_record_consent_decision_consented(self):
        raw = request_participation_consent(
            membership=self.membership,
            guardian_name="Guardian",
            guardian_email="guardian@example.com",
            consent_text="Consent text.",
        )
        consent = record_consent_decision(raw_token=raw, consented=True)
        self.assertEqual(consent.decision, ParticipationConsentDecision.CONSENTED)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, TeamMembership.Status.ACTIVE)

    def test_record_consent_decision_declined(self):
        raw = request_participation_consent(
            membership=self.membership,
            guardian_name="Guardian",
            guardian_email="guardian@example.com",
            consent_text="Consent text.",
        )
        consent = record_consent_decision(raw_token=raw, consented=False)
        self.assertEqual(consent.decision, ParticipationConsentDecision.DECLINED)

    def test_record_consent_decision_unknown_token_raises(self):
        with self.assertRaises(ParticipationConsentError):
            record_consent_decision(raw_token="totally-unknown-token", consented=True)

    def test_record_consent_decision_expired_token_raises(self):
        raw = request_participation_consent(
            membership=self.membership,
            guardian_name="Guardian",
            guardian_email="guardian@example.com",
            consent_text="Consent text.",
        )
        consent = ParticipationConsent.lookup_by_raw_token(raw)
        consent.expires_at = timezone.now() - timedelta(days=1)
        consent.save(update_fields=["expires_at"])
        with self.assertRaises(ParticipationConsentError):
            record_consent_decision(raw_token=raw, consented=True)
        # The membership was never activated.
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, TeamMembership.Status.PENDING)
