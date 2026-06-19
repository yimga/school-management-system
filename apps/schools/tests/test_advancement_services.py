from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from datetime import timedelta

from apps.finance.models import AidAuditLog, AwardSource
from apps.schoolops.models import InventoryItem
from apps.schools.advancement_services import (
    accept_in_kind_donation,
    campaign_progress,
    designate_and_credit_gift,
    donations_overview,
    fulfill_pledge,
    mint_donor_access_link,
    pledge_aging,
    reject_in_kind_donation,
    resolve_donor_access_link,
)
from apps.schools.models import (
    AdvancementDonor,
    AdvancementGift,
    DonationPledge,
    DonorGiftAccessLink,
    FundraisingCampaign,
    InKindDonation,
    School,
)


class GiftToFundCreditTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Advancement School",
            slug="advancement-school",
            subdomain="advancement-school",
            is_active=True,
        )
        self.donor = AdvancementDonor.objects.create(
            school=self.school, display_name="Acme NGO", email="ngo@example.org"
        )
        self.source = AwardSource.objects.create(
            school=self.school,
            name="Scholarship Fund",
            total_budget=Decimal("0.00"),
            remaining_funds=Decimal("0.00"),
            currency="USD",
        )

    def _gift(self, amount="500.00", currency="USD", campaign=""):
        return AdvancementGift.objects.create(
            donor=self.donor,
            amount=Decimal(amount),
            currency=currency,
            received_at=timezone.now().date(),
            campaign_name=campaign,
        )

    def test_gift_credits_fund_once(self):
        gift = self._gift("500.00", campaign="Annual Fund")
        res = designate_and_credit_gift(gift, self.source.id)
        self.assertTrue(res["ok"])
        self.source.refresh_from_db()
        self.assertEqual(self.source.remaining_funds, Decimal("500.00"))
        gift.refresh_from_db()
        self.assertIsNotNone(gift.credited_to_fund_at)
        self.assertEqual(gift.award_source_id, self.source.id)
        self.assertEqual(
            AidAuditLog.objects.filter(source=self.source, action="donation").count(), 1
        )

        # Idempotent: re-running does nothing.
        res2 = designate_and_credit_gift(gift, self.source.id)
        self.assertIsNone(res2)
        self.source.refresh_from_db()
        self.assertEqual(self.source.remaining_funds, Decimal("500.00"))

    def test_currency_mismatch_does_not_credit_or_link(self):
        gift = self._gift("100.00", currency="EUR")
        res = designate_and_credit_gift(gift, self.source.id)
        self.assertFalse(res["ok"])
        self.source.refresh_from_db()
        self.assertEqual(self.source.remaining_funds, Decimal("0.00"))
        gift.refresh_from_db()
        self.assertIsNone(gift.credited_to_fund_at)
        self.assertIsNone(gift.award_source_id)

    def test_unknown_source_for_school_is_rejected(self):
        other = School.objects.create(
            name="Other", slug="other", subdomain="other", is_active=True
        )
        foreign_source = AwardSource.objects.create(
            school=other,
            name="Foreign Fund",
            total_budget=Decimal("0.00"),
            remaining_funds=Decimal("0.00"),
            currency="USD",
        )
        gift = self._gift("100.00")
        res = designate_and_credit_gift(gift, foreign_source.id)
        self.assertFalse(res["ok"])
        foreign_source.refresh_from_db()
        self.assertEqual(foreign_source.remaining_funds, Decimal("0.00"))


class InKindDonationInventoryTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="In-Kind School",
            slug="in-kind-school",
            subdomain="in-kind-school",
            is_active=True,
        )
        self.donor = AdvancementDonor.objects.create(
            school=self.school, display_name="Books For All"
        )

    def _donation(self, description="Reading textbooks", quantity=10):
        return InKindDonation.objects.create(
            school=self.school,
            donor=self.donor,
            description=description,
            category=InKindDonation.Category.BOOKS,
            quantity=quantity,
            received_at=timezone.now().date(),
        )

    def test_accept_creates_inventory_item(self):
        donation = self._donation(quantity=10)
        res = accept_in_kind_donation(donation, location="Library")
        self.assertTrue(res["ok"])
        donation.refresh_from_db()
        self.assertEqual(donation.status, InKindDonation.Status.ACCEPTED)
        self.assertIsNotNone(donation.inventory_item_id)
        item = InventoryItem.objects.get(pk=donation.inventory_item_id)
        self.assertEqual(item.school_id, self.school.id)
        self.assertEqual(item.quantity, 10)
        self.assertEqual(item.location, "Library")

    def test_accept_increments_existing_same_named_item(self):
        InventoryItem.objects.create(
            school=self.school, name="Reading textbooks", quantity=5
        )
        donation = self._donation(quantity=3)
        res = accept_in_kind_donation(donation)
        self.assertTrue(res["ok"])
        item = InventoryItem.objects.get(school=self.school, name="Reading textbooks")
        self.assertEqual(item.quantity, 8)

    def test_accept_is_idempotent(self):
        donation = self._donation(quantity=4)
        accept_in_kind_donation(donation)
        res2 = accept_in_kind_donation(donation)
        self.assertFalse(res2["ok"])
        self.assertEqual(
            InventoryItem.objects.filter(school=self.school).count(), 1
        )

    def test_reject_does_not_touch_inventory(self):
        donation = self._donation()
        res = reject_in_kind_donation(donation, reason="Damaged")
        self.assertTrue(res["ok"])
        donation.refresh_from_db()
        self.assertEqual(donation.status, InKindDonation.Status.REJECTED)
        self.assertEqual(InventoryItem.objects.filter(school=self.school).count(), 0)

    def test_cannot_reject_accepted_donation(self):
        donation = self._donation()
        accept_in_kind_donation(donation)
        res = reject_in_kind_donation(donation)
        self.assertFalse(res["ok"])


class CampaignProgressTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Campaign School", slug="campaign-school",
            subdomain="campaign-school", is_active=True,
        )
        self.donor = AdvancementDonor.objects.create(
            school=self.school, display_name="Donor One"
        )
        self.campaign = FundraisingCampaign.objects.create(
            school=self.school, name="Library Drive",
            goal_amount=Decimal("1000.00"), currency="USD",
            status=FundraisingCampaign.Status.ACTIVE,
        )

    def test_progress_aggregates_cash_and_in_kind(self):
        AdvancementGift.objects.create(
            donor=self.donor, amount=Decimal("300.00"), currency="USD",
            received_at=timezone.now().date(), campaign=self.campaign,
        )
        AdvancementGift.objects.create(
            donor=self.donor, amount=Decimal("200.00"), currency="USD",
            received_at=timezone.now().date(), campaign=self.campaign,
        )
        InKindDonation.objects.create(
            school=self.school, donor=self.donor, description="Books",
            quantity=5, estimated_value=Decimal("100.00"), campaign=self.campaign,
        )
        p = campaign_progress(self.campaign)
        self.assertEqual(p["cash_raised"], Decimal("500.00"))
        self.assertEqual(p["in_kind_value"], Decimal("100.00"))
        self.assertEqual(p["raised"], Decimal("600.00"))
        self.assertEqual(p["pct_to_goal"], 60)
        self.assertEqual(p["gift_count"], 2)
        self.assertEqual(p["in_kind_count"], 1)

    def test_progress_pct_caps_at_100(self):
        AdvancementGift.objects.create(
            donor=self.donor, amount=Decimal("5000.00"), currency="USD",
            received_at=timezone.now().date(), campaign=self.campaign,
        )
        p = campaign_progress(self.campaign)
        self.assertEqual(p["pct_to_goal"], 100)
        self.assertTrue(p["over_goal"])

    def test_donations_overview_shape(self):
        AdvancementGift.objects.create(
            donor=self.donor, amount=Decimal("50.00"), currency="USD",
            received_at=timezone.now().date(),
        )
        ov = donations_overview(self.school.pk)
        self.assertEqual(ov["total_cash_raised"], Decimal("50.00"))
        self.assertIn("campaigns", ov)
        self.assertIn("endowment", ov)
        self.assertEqual(len(ov["campaigns"]), 1)


class DonorAccessLinkTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Link School", slug="link-school",
            subdomain="link-school", is_active=True,
        )
        self.donor = AdvancementDonor.objects.create(
            school=self.school, display_name="Magic Donor", email="d@example.org"
        )

    def test_mint_and_resolve_bumps_access(self):
        link = mint_donor_access_link(self.donor)
        self.assertTrue(link.is_valid)
        resolved = resolve_donor_access_link(link.token)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.donor_id, self.donor.pk)
        resolved.refresh_from_db()
        self.assertEqual(resolved.access_count, 1)

    def test_expired_link_does_not_resolve(self):
        link = mint_donor_access_link(self.donor)
        DonorGiftAccessLink.objects.filter(pk=link.pk).update(
            expires_at=timezone.now() - timedelta(days=1)
        )
        self.assertIsNone(resolve_donor_access_link(link.token))


class AdvancementAiDraftTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Draft School", slug="draft-school",
            subdomain="draft-school", is_active=True,
        )

    def test_acknowledgment_always_returns_text(self):
        from services.advancement_ai import draft_donor_acknowledgment

        text, meta = draft_donor_acknowledgment(
            school=self.school, donor_name="Jane Doe",
            amount=Decimal("250.00"), currency="USD", campaign_name="Annual Fund",
        )
        self.assertTrue(text)
        self.assertIn("Jane Doe", text)

    def test_grant_draft_always_returns_text(self):
        from services.advancement_ai import draft_grant_application

        text, meta = draft_grant_application(
            school=self.school, funder_name="Acme Foundation",
            program="STEM lab", amount=Decimal("10000.00"),
        )
        self.assertTrue(text)
        self.assertIn("STEM lab", text)


class OfflineDonationIntakeTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.school = School.objects.create(
            name="Offline School", slug="offline-school",
            subdomain="offline-school", is_active=True,
        )
        self.user = get_user_model().objects.create_user(
            username="offline_staff", password="x"
        )

    def test_offline_donation_intake_creates_gift(self):
        from apps.platform_runtime.offline_queue import (
            enqueue_offline_action,
            process_offline_queue,
        )

        enqueue_offline_action(
            user_id=self.user.pk, school_id=self.school.pk,
            action_type="donation.intake",
            payload={"donor_name": "Field Donor", "amount": "75.00", "currency": "USD"},
            idempotency_key="off-don-1",
        )
        result = process_offline_queue(school_id=self.school.pk)
        self.assertGreaterEqual(result.get("synced", 0), 1)
        donor = AdvancementDonor.objects.get(school=self.school, display_name="Field Donor")
        self.assertEqual(donor.gifts.count(), 1)
        self.assertEqual(donor.gifts.first().amount, Decimal("75.00"))

    def test_offline_in_kind_intake_creates_pending_donation(self):
        from apps.platform_runtime.offline_queue import (
            enqueue_offline_action,
            process_offline_queue,
        )

        enqueue_offline_action(
            user_id=self.user.pk, school_id=self.school.pk,
            action_type="in_kind.intake",
            payload={"description": "Donated tablets", "quantity": 12, "category": "equipment"},
            idempotency_key="off-ink-1",
        )
        result = process_offline_queue(school_id=self.school.pk)
        self.assertGreaterEqual(result.get("synced", 0), 1)
        d = InKindDonation.objects.get(school=self.school, description="Donated tablets")
        self.assertEqual(d.quantity, 12)
        self.assertEqual(d.status, InKindDonation.Status.PENDING)

    def test_donation_intake_is_idempotent_on_client_offline_id(self):
        from apps.platform_runtime.offline_queue import (
            enqueue_offline_action,
            process_offline_queue,
        )

        # Same captured gift replayed under two DIFFERENT queue keys (the client
        # re-queued after a flaky sync). The queue-level (school, idempotency_key)
        # dedup does NOT catch a re-keyed replay — only the record-level
        # client_offline_id guard does. A second gift here would double-credit
        # the gift's fund, so it must fold onto the first.
        for queue_key in ("off-don-A", "off-don-B"):
            enqueue_offline_action(
                user_id=self.user.pk, school_id=self.school.pk,
                action_type="donation.intake",
                payload={
                    "donor_name": "Repeat Donor", "amount": "120.00",
                    "currency": "USD", "client_offline_id": "cid-don-1",
                },
                idempotency_key=queue_key,
            )
        process_offline_queue(school_id=self.school.pk)
        donor = AdvancementDonor.objects.get(school=self.school, display_name="Repeat Donor")
        self.assertEqual(donor.gifts.count(), 1)
        self.assertEqual(donor.gifts.first().client_offline_id, "cid-don-1")

    def test_in_kind_intake_is_idempotent_on_client_offline_id(self):
        from apps.platform_runtime.offline_queue import (
            enqueue_offline_action,
            process_offline_queue,
        )

        for queue_key in ("off-ink-A", "off-ink-B"):
            enqueue_offline_action(
                user_id=self.user.pk, school_id=self.school.pk,
                action_type="in_kind.intake",
                payload={
                    "description": "Replayed crate of books", "quantity": 5,
                    "category": "equipment", "client_offline_id": "cid-ink-1",
                },
                idempotency_key=queue_key,
            )
        process_offline_queue(school_id=self.school.pk)
        self.assertEqual(
            InKindDonation.objects.filter(
                school=self.school, description="Replayed crate of books"
            ).count(),
            1,
        )

    def test_keyless_offline_donations_are_never_folded_together(self):
        from apps.platform_runtime.offline_queue import (
            enqueue_offline_action,
            process_offline_queue,
        )

        # No client_offline_id -> the partial-unique index skips blank keys, so two
        # genuinely distinct keyless captures from the same donor must BOTH land
        # (the dedup must never silently swallow real offline work).
        for queue_key in ("off-keyless-1", "off-keyless-2"):
            enqueue_offline_action(
                user_id=self.user.pk, school_id=self.school.pk,
                action_type="donation.intake",
                payload={"donor_name": "Keyless Donor", "amount": "10.00", "currency": "USD"},
                idempotency_key=queue_key,
            )
        process_offline_queue(school_id=self.school.pk)
        donor = AdvancementDonor.objects.get(school=self.school, display_name="Keyless Donor")
        self.assertEqual(donor.gifts.count(), 2)


class DonationPledgeTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Pledge School", slug="pledge-school",
            subdomain="pledge-school", is_active=True,
        )
        self.donor = AdvancementDonor.objects.create(
            school=self.school, display_name="Pledging Donor"
        )

    def _pledge(self, amount="1000.00", due_offset_days=None):
        due = None
        if due_offset_days is not None:
            due = timezone.now().date() + timedelta(days=due_offset_days)
        return DonationPledge.objects.create(
            school=self.school, donor=self.donor,
            amount=Decimal(amount), currency="USD", due_date=due,
        )

    def test_partial_then_full_fulfillment(self):
        p = self._pledge("1000.00")
        r1 = fulfill_pledge(p, Decimal("400.00"))
        self.assertTrue(r1["ok"])
        p.refresh_from_db()
        self.assertEqual(p.status, DonationPledge.Status.PARTIAL)
        self.assertEqual(p.outstanding_amount, Decimal("600.00"))
        fulfill_pledge(p, Decimal("600.00"))
        p.refresh_from_db()
        self.assertEqual(p.status, DonationPledge.Status.FULFILLED)
        self.assertIsNotNone(p.fulfilled_at)
        self.assertEqual(p.outstanding_amount, Decimal("0.00"))

    def test_cancelled_pledge_rejects_fulfillment(self):
        p = self._pledge("100.00")
        p.status = DonationPledge.Status.CANCELLED
        p.save(update_fields=["status"])
        self.assertFalse(fulfill_pledge(p, Decimal("50.00"))["ok"])

    def test_aging_buckets(self):
        self._pledge("100.00", due_offset_days=10)    # current (future due)
        self._pledge("200.00", due_offset_days=-15)   # 1-30 overdue
        self._pledge("300.00", due_offset_days=-45)   # 31-60 overdue
        self._pledge("400.00", due_offset_days=-90)   # 60+ overdue
        aging = pledge_aging(self.school.pk)
        self.assertEqual(aging["buckets"]["current"], Decimal("100.00"))
        self.assertEqual(aging["buckets"]["d1_30"], Decimal("200.00"))
        self.assertEqual(aging["buckets"]["d31_60"], Decimal("300.00"))
        self.assertEqual(aging["buckets"]["d60_plus"], Decimal("400.00"))
        self.assertEqual(aging["total_outstanding"], Decimal("1000.00"))

    def test_fulfilled_pledge_excluded_from_aging(self):
        p = self._pledge("500.00", due_offset_days=-30)
        fulfill_pledge(p, Decimal("500.00"))
        aging = pledge_aging(self.school.pk)
        self.assertEqual(aging["total_outstanding"], Decimal("0.00"))
