import uuid
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.schools.advancement_services import mint_donor_access_link
from apps.schools.models import AdvancementDonor, AdvancementGift, School


class DonorReceiptPdfTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Receipt School", slug="receipt-school",
            subdomain="receipt-school", is_active=True,
        )
        self.donor = AdvancementDonor.objects.create(
            school=self.school, display_name="Grace Giver", email="grace@example.org"
        )
        self.gift = AdvancementGift.objects.create(
            donor=self.donor, amount=Decimal("250.00"), currency="USD",
            received_at=timezone.now().date(),
        )
        self.link = mint_donor_access_link(self.donor)

    def _url(self, token, gift_id):
        return reverse("accounts:donor_gift_receipt", args=[token, gift_id])

    def test_valid_request_returns_200_and_marks_receipt_sent(self):
        # WeasyPrint may be absent in the test env; the view degrades to HTML, so
        # either way the donor gets a 200 and the gift is flagged receipt_sent.
        resp = self.client.get(self._url(self.link.token, self.gift.pk))
        self.assertEqual(resp.status_code, 200)
        self.gift.refresh_from_db()
        self.assertTrue(self.gift.receipt_sent)

    def test_invalid_token_returns_400(self):
        resp = self.client.get(self._url(uuid.uuid4(), self.gift.pk))
        self.assertEqual(resp.status_code, 400)

    def test_cannot_fetch_another_donors_gift(self):
        other = AdvancementDonor.objects.create(
            school=self.school, display_name="Other Donor"
        )
        other_gift = AdvancementGift.objects.create(
            donor=other, amount=Decimal("99.00"), currency="USD",
            received_at=timezone.now().date(),
        )
        # donor1's token must not be able to pull donor2's gift receipt.
        resp = self.client.get(self._url(self.link.token, other_gift.pk))
        self.assertEqual(resp.status_code, 404)
