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


class ConsentEmailIsActionableTests(BaseAthleticsTestCase):
    """The guardian must be able to ACT on the consent request.

    ``_send_consent_email`` wrote the raw token into the body as a bare
    reference -- "Your one-time consent reference is: <token>" -- and no link.
    The consent pages exist (``athletics:participation_consent_public`` and
    ``:participation_consent_decide``, both mounted on the tenant host and both
    reading ``?token=``), so the flow was fully built and simply had no entry
    point: a guardian receiving that email has a secret and nowhere to put it.

    Nothing catches this class. The URL resolves, the view renders, the email
    sends, and every assertion about token minting passes. Only a person holding
    the email can see that it asks them to do something impossible.
    """

    def setUp(self):
        super().setUp()
        self.membership = self.add_member(
            self.fx, status=TeamMembership.Status.PENDING
        )

    def _send_and_capture(self, request=None):
        from django.core import mail

        mail.outbox = []
        raw = request_participation_consent(
            membership=self.membership,
            guardian_name="Guardian",
            guardian_email="guardian@example.com",
            consent_text="Consent text.",
            request=request,
        )
        return raw, mail.outbox

    def _tenant_request(self):
        from django.test import RequestFactory

        request = RequestFactory().post(
            "/athletics/memberships/1/request-consent/",
            HTTP_HOST=f"{self.fx.school.subdomain}.runmycampus.com",
        )
        request.school = self.fx.school
        return request

    def test_an_email_is_actually_sent(self):
        # Calibration: every assertion below is vacuous if the outbox is empty.
        _raw, outbox = self._send_and_capture(self._tenant_request())
        self.assertEqual(len(outbox), 1)
        self.assertEqual(outbox[0].to, ["guardian@example.com"])

    def test_the_email_carries_a_link_the_guardian_can_open(self):
        raw, outbox = self._send_and_capture(self._tenant_request())
        body = outbox[0].body
        self.assertIn("/athletics/consent/", body)
        self.assertIn(f"token={raw}", body)
        self.assertIn("http", body)

    def test_the_link_is_on_the_tenant_host(self):
        """A consent page served from the wrong host 404s for the guardian."""
        _raw, outbox = self._send_and_capture(self._tenant_request())
        self.assertIn(f"{self.fx.school.subdomain}.", outbox[0].body)

    def test_without_a_request_the_mint_still_succeeds(self):
        """Email is best-effort and must never roll back the mint."""
        raw, _outbox = self._send_and_capture(None)
        self.assertTrue(raw)
        self.assertIsNotNone(ParticipationConsent.lookup_by_raw_token(raw))
