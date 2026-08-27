"""Kit-fee invoicing and away-fixture transport must actually run.

Both services were fully written, tested in isolation, and reachable from
nothing. ``raise_kit_fee_invoice`` and ``link_away_fixture_transport`` had no
view, form, signal, management command or task calling them anywhere in the
repo -- yet ``TeamKitFee`` and ``FixtureTravel`` are first-class models
registered on the mounted ``tenant_admin_site``, with ``is_mandatory``
defaulting to True. So an operator configures a mandatory kit fee for a team,
sees it saved, and no family is ever invoiced; and scheduling an AWAY fixture
never books transport.

The producers wired here:

* roster activation -- ``record_consent_decision`` is the single production path
  a ``TeamMembership`` takes out of PENDING (``ParticipationConsent.consent()``
  is the only thing that sets ACTIVE). That is the right moment to bill: at
  ``coach_add_member`` the membership is PENDING and the guardian has not
  consented, so invoicing there would bill a family for a place they may refuse.
* ``schedule_fixture`` -- an AWAY fixture gets its ``FixtureTravel`` row (route
  still unset; the service documents ``route=None`` as a valid state) so the
  fixture shows up in transport planning instead of being invisible to it.

Both hooks are best-effort: a finance/transport problem must never roll back the
consent or the fixture.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.athletics.models import (
    Fixture,
    FixtureTravel,
    ParticipationConsent,
    TeamKitFee,
    TeamMembership,
)
from apps.athletics.services.consent import record_consent_decision
from apps.athletics.services.scheduling import schedule_fixture
from apps.athletics.tests.base import BaseAthleticsTestCase
from apps.finance.models import ComplianceProfile, Invoice


class KitFeeIsRaisedOnRosterActivationTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.profile = ComplianceProfile.objects.create(
            name="Athletics Fees Wiring", country_code="CM", is_active=True
        )
        self.membership = self.add_member(
            self.fx, status=TeamMembership.Status.PENDING
        )
        self.fee = TeamKitFee.objects.create(
            school=self.fx.school,
            team=self.fx.team,
            label="Home + away kit",
            amount=Decimal("120.00"),
            is_mandatory=True,
            is_active=True,
        )

    def _mint(self):
        return ParticipationConsent.mint(
            membership=self.membership,
            guardian_name="Parent",
            guardian_email="parent@example.com",
            consent_text="I consent to participation.",
        )

    def test_guardian_consent_activates_and_invoices_the_kit_fee(self):
        raw, _consent = self._mint()

        record_consent_decision(raw_token=raw, consented=True)

        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, TeamMembership.Status.ACTIVE)
        invoice = Invoice.objects.get(
            school=self.fx.school, student_id=self.membership.student_id
        )
        self.assertEqual(invoice.total_amount, Decimal("120.00"))
        self.assertEqual(invoice.invoice_type, Invoice.InvoiceType.AR)

    def test_a_declined_consent_bills_nobody(self):
        raw, _consent = self._mint()

        record_consent_decision(raw_token=raw, consented=False)

        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, TeamMembership.Status.LEFT)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_no_kit_fee_configured_still_activates_the_membership(self):
        """The hook is best-effort: no fee is the normal case, not an error."""
        self.fee.delete()
        raw, _consent = self._mint()

        record_consent_decision(raw_token=raw, consented=True)

        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, TeamMembership.Status.ACTIVE)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_a_finance_failure_never_rolls_back_the_consent(self):
        from unittest.mock import patch

        raw, _consent = self._mint()
        with patch(
            "apps.athletics.services.fees.raise_kit_fee_invoice",
            side_effect=RuntimeError("finance is down"),
        ):
            record_consent_decision(raw_token=raw, consented=True)

        self.membership.refresh_from_db()
        self.assertEqual(
            self.membership.status,
            TeamMembership.Status.ACTIVE,
            "a billing outage must not cost the athlete their roster place",
        )
        self.assertEqual(Invoice.objects.count(), 0)

    def test_activating_twice_bills_once(self):
        raw, _consent = self._mint()
        record_consent_decision(raw_token=raw, consented=True)

        # A second consent on the same membership (a re-minted token) must not
        # produce a second invoice.
        self.membership.status = TeamMembership.Status.PENDING
        self.membership.save(update_fields=["status"])
        raw2, _c2 = self._mint()
        record_consent_decision(raw_token=raw2, consented=True)

        self.assertEqual(
            Invoice.objects.filter(school=self.fx.school).count(),
            1,
            "kit-fee invoicing must stay idempotent per team+student",
        )


class AwayFixtureBooksTransportTests(BaseAthleticsTestCase):
    def _schedule(self, fixture_type):
        start = timezone.now() + timedelta(days=3)
        return schedule_fixture(
            team=self.fx.team,
            opponent_name="Rival College",
            fixture_type=fixture_type,
            venue=None,
            start=start,
            end=start + timedelta(hours=2),
            book_venue=False,
        )

    def test_an_away_fixture_gets_a_travel_row(self):
        fixture = self._schedule(Fixture.FixtureType.AWAY)

        travel = FixtureTravel.objects.get(fixture=fixture)
        self.assertEqual(travel.school_id, self.fx.school.id)
        self.assertEqual(travel.status, FixtureTravel.Status.PLANNED)
        self.assertIsNone(travel.route_id)

    def test_a_home_fixture_does_not(self):
        fixture = self._schedule(Fixture.FixtureType.HOME)

        self.assertFalse(FixtureTravel.objects.filter(fixture=fixture).exists())

    def test_a_transport_failure_never_rolls_back_the_fixture(self):
        from unittest.mock import patch

        with patch(
            "apps.athletics.services.transport.link_away_fixture_transport",
            side_effect=RuntimeError("transport is down"),
        ):
            fixture = self._schedule(Fixture.FixtureType.AWAY)

        self.assertIsNotNone(fixture.pk)
        self.assertTrue(Fixture.objects.filter(pk=fixture.pk).exists())
