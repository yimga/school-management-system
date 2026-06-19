from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.finance.models import AidAuditLog, AwardSource
from apps.schoolops.models import InventoryItem
from apps.schools.advancement_services import (
    accept_in_kind_donation,
    designate_and_credit_gift,
    reject_in_kind_donation,
)
from apps.schools.models import AdvancementDonor, AdvancementGift, InKindDonation, School


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
