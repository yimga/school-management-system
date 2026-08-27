"""The recorded consent decision IP must not be a value the decider chose.

``ParticipationConsent._stamp_request`` read ``HTTP_X_FORWARDED_FOR`` and stored
its LEFTMOST element as ``ip_address_decision``. ``X-Forwarded-For`` is
client-controlled to the left -- a reverse proxy appends its own observation on
the RIGHT -- so anyone holding the token could send ``X-Forwarded-For: 1.2.3.4``
and have that written as the recorded consent IP.

That defeats the only reason the column exists. The module docstring calls the
decision IP/UA "server-captured" forensic evidence for a CHILD-participation
consent, and ``services/gdpr.py::athletics_scrub_student`` treats it as
re-identifying PII -- i.e. it is relied upon downstream as if it were real.

``apps.api.rate_limit.client_ip`` is this repo's trusted-proxy-depth parse
(``XFF[-RATE_LIMIT_TRUSTED_PROXY_COUNT]``); this pins the consent stamp onto it,
the same way ``apps/compliance/tests/test_client_ip_trust_boundary.py`` pins the
compliance readers.

The header shape is ``"<forged>, <real>"`` with ``RATE_LIMIT_TRUSTED_PROXY_COUNT=1``
-- one load balancer, which appended the real peer address on the right.
"""

from __future__ import annotations

from django.test import RequestFactory, override_settings

from apps.athletics.models import (
    ParticipationConsent,
    ParticipationConsentDecision,
    TeamMembership,
)
from apps.athletics.tests.base import BaseAthleticsTestCase

FORGED = "198.51.100.42"
REAL = "203.0.113.9"
SPOOFED_XFF = f"{FORGED}, {REAL}"


@override_settings(RATE_LIMIT_TRUSTED_PROXY_COUNT=1)
class ConsentDecisionIPTrustBoundaryTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.membership = self.add_member(
            self.fx, status=TeamMembership.Status.PENDING
        )
        self.factory = RequestFactory()

    def _mint(self):
        return ParticipationConsent.mint(
            membership=self.membership,
            guardian_name="Parent",
            guardian_email="parent@example.com",
            consent_text="I consent to participation.",
        )

    def _spoofed_request(self):
        return self.factory.post(
            "/athletics/consent/decide/",
            HTTP_X_FORWARDED_FOR=SPOOFED_XFF,
            REMOTE_ADDR="10.0.0.1",
            HTTP_USER_AGENT="Mozilla/5.0 (guardian)",
        )

    def test_consent_records_the_trusted_hop_not_the_forged_one(self):
        _raw, consent = self._mint()

        consent.consent(self._spoofed_request())

        consent.refresh_from_db()
        self.assertEqual(consent.decision, ParticipationConsentDecision.CONSENTED)
        self.assertNotEqual(
            consent.ip_address_decision,
            FORGED,
            "the guardian chose this value; it is not evidence of anything",
        )
        self.assertEqual(consent.ip_address_decision, REAL)

    def test_decline_records_the_trusted_hop_too(self):
        _raw, consent = self._mint()

        consent.decline(self._spoofed_request())

        consent.refresh_from_db()
        self.assertEqual(consent.decision, ParticipationConsentDecision.DECLINED)
        self.assertNotEqual(consent.ip_address_decision, FORGED)
        self.assertEqual(consent.ip_address_decision, REAL)

    def test_a_deeper_forged_chain_still_resolves_to_the_lb_hop(self):
        """Padding the header with extra hops must not move the trusted index."""
        _raw, consent = self._mint()
        request = self.factory.post(
            "/athletics/consent/decide/",
            HTTP_X_FORWARDED_FOR=f"9.9.9.9, 8.8.8.8, {FORGED}, {REAL}",
            REMOTE_ADDR="10.0.0.1",
        )

        consent.consent(request)

        consent.refresh_from_db()
        self.assertEqual(consent.ip_address_decision, REAL)

    def test_no_forwarded_header_falls_back_to_remote_addr(self):
        _raw, consent = self._mint()
        request = self.factory.post(
            "/athletics/consent/decide/", REMOTE_ADDR="192.0.2.55"
        )

        consent.consent(request)

        consent.refresh_from_db()
        self.assertEqual(consent.ip_address_decision, "192.0.2.55")

    def test_the_public_decide_view_stamps_the_trusted_hop(self):
        """End to end through the anonymous POST the guardian actually makes."""
        from apps.athletics.views.consent_public import participation_consent_decide

        raw, consent = self._mint()
        request = self.factory.post(
            "/athletics/consent/decide/",
            {"token": raw, "choice": "consent"},
            HTTP_X_FORWARDED_FOR=SPOOFED_XFF,
            REMOTE_ADDR="10.0.0.1",
        )

        response = participation_consent_decide(request)

        self.assertEqual(response.status_code, 200)
        consent.refresh_from_db()
        self.assertEqual(consent.decision, ParticipationConsentDecision.CONSENTED)
        self.assertEqual(consent.ip_address_decision, REAL)
