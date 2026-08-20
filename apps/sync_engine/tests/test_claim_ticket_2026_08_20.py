"""A claim ticket pre-authorises ONE adoption — and is loud when misused.

The case: a technician installs a box at a scheduled visit with nobody holding cloud
admin reachable. Deferred approval plus an emailed nudge covers "nobody is at a console
right now"; it does not cover "the box must be syncing before I leave the site".

A ticket is acceptable only because of what it is NOT. It is not a bearer token for the
sync API — it buys exactly one auto-approved pairing for one named school. These tests
pin every property that claim rests on, and the most important ones are the negatives:
a spent ticket cannot be reused, a ticket for school A cannot adopt a box into school B,
and every refused attempt is COUNTED — because the legitimate box redeems exactly once,
so any second attempt means the ticket is in someone else's hands. That alarm is the
property a long-lived credential in a .env file can never provide.
"""
from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.sync_engine.models_pairing import EdgeClaimTicket, EdgePairingRequest


class ClaimTicketTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.schools.models import School, SchoolMembership

        self.school = School.objects.create(
            name="Gilead Tech", slug="gilead-tech", subdomain="gilead-tech"
        )
        self.other = School.objects.create(
            name="Other", slug="other-school", subdomain="other-school"
        )
        User = get_user_model()
        self.admin = User.objects.create_user(username="gilead_admin", password="x")
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN", is_school_owner=True
        )
        self.nobody = User.objects.create_user(username="nobody", password="x")

    def _mint(self, school=None, minted_by=None, days=14):
        from apps.sync_engine.pairing_service import mint_claim_ticket

        return mint_claim_ticket(
            school=school or self.school, minted_by=minted_by or self.admin, days=days
        )

    def _start(self, ticket="", slug="gilead-tech"):
        from apps.sync_engine.pairing_service import start_pairing

        with mock.patch(
            "apps.sync_engine.pairing_service.notify_admins_of_pending_pairing"
        ):
            return start_pairing(claimed_slug=slug, claim_ticket=ticket)

    # ------------------------------------------------------------------- mint --
    def test_only_the_raw_hash_is_stored(self):
        result = self._mint()
        self.assertTrue(result["ok"])
        row = EdgeClaimTicket.objects.get(pk=result["ticket_id"])
        self.assertNotIn(result["ticket"], row.ticket_hash)
        self.assertEqual(len(row.ticket_hash), 64)

    def test_a_non_admin_cannot_mint(self):
        result = self._mint(minted_by=self.nobody)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "forbidden")

    # ---------------------------------------------------------------- redeem --
    def test_a_valid_ticket_pre_approves_the_request(self):
        ticket = self._mint()["ticket"]
        started = self._start(ticket=ticket)
        self.assertTrue(started["pre_approved"])
        row = EdgePairingRequest.objects.get(pk=started["request_id"])
        self.assertEqual(row.status, EdgePairingRequest.Status.APPROVED)
        self.assertEqual(row.approved_by_id, self.admin.pk)

    def test_a_pre_approved_box_collects_without_any_human_action(self):
        from apps.sync_engine.pairing_service import collect_pairing

        ticket = self._mint()["ticket"]
        started = self._start(ticket=ticket)
        out = collect_pairing(
            request_id=started["request_id"], poll_secret=started["poll_secret"]
        )
        self.assertEqual(out["status"], "approved")
        self.assertTrue(out["credential"])

    def test_a_ticket_is_single_use(self):
        ticket = self._mint()["ticket"]
        first = self._start(ticket=ticket)
        self.assertTrue(first["pre_approved"])
        second = self._start(ticket=ticket)
        self.assertFalse(second["pre_approved"])
        self.assertEqual(second["claim_ticket_error"], "invalid_or_spent")

    def test_reusing_a_spent_ticket_is_counted_as_misuse(self):
        """The legitimate box redeems once; anything more means someone has a copy."""
        result = self._mint()
        ticket, ticket_id = result["ticket"], result["ticket_id"]
        self._start(ticket=ticket)
        for _ in range(3):
            self._start(ticket=ticket)
        row = EdgeClaimTicket.objects.get(pk=ticket_id)
        self.assertEqual(row.misuse_attempts, 3)
        self.assertIsNotNone(row.last_misuse_at)

    def test_a_ticket_cannot_adopt_a_box_into_a_different_school(self):
        ticket = self._mint(school=self.other, minted_by=self.admin)
        # admin does not administer `other`, so minting must have been refused
        self.assertFalse(ticket["ok"])

    def test_a_ticket_presented_against_the_wrong_school_is_refused_and_counted(self):
        from apps.schools.models import SchoolMembership

        SchoolMembership.objects.create(
            user=self.admin, school=self.other, role="ADMIN", is_school_owner=True
        )
        result = self._mint(school=self.other)
        started = self._start(ticket=result["ticket"], slug="gilead-tech")
        self.assertFalse(started["pre_approved"])
        row = EdgeClaimTicket.objects.get(pk=result["ticket_id"])
        self.assertEqual(row.misuse_attempts, 1)
        self.assertIsNone(row.redeemed_at)

    def test_an_expired_ticket_is_refused(self):
        result = self._mint()
        EdgeClaimTicket.objects.filter(pk=result["ticket_id"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        started = self._start(ticket=result["ticket"])
        self.assertFalse(started["pre_approved"])

    def test_a_revoked_ticket_is_refused(self):
        result = self._mint()
        EdgeClaimTicket.objects.filter(pk=result["ticket_id"]).update(
            revoked_at=timezone.now()
        )
        started = self._start(ticket=result["ticket"])
        self.assertFalse(started["pre_approved"])

    def test_an_unknown_ticket_still_opens_an_ordinary_request(self):
        """A bad ticket must degrade to normal pairing, not block the install."""
        started = self._start(ticket="RMC-not-a-real-ticket")
        self.assertTrue(started["ok"])
        self.assertFalse(started["pre_approved"])
        row = EdgePairingRequest.objects.get(pk=started["request_id"])
        self.assertEqual(row.status, EdgePairingRequest.Status.PENDING)

    def test_no_ticket_behaves_exactly_as_before(self):
        started = self._start()
        self.assertFalse(started["pre_approved"])
        self.assertEqual(started["claim_ticket_error"], "")
        row = EdgePairingRequest.objects.get(pk=started["request_id"])
        self.assertEqual(row.status, EdgePairingRequest.Status.PENDING)
