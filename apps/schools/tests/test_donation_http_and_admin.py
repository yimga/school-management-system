"""HTTP-layer + admin coverage for the donation/advancement surface (gap closeout).

Complements test_advancement_services.py (service-layer) with the paths the gap
analysis flagged as untested:
  * the public donor magic-link portal view (valid / invalid / expired / isolation),
  * the staff donation_capture POST view (auth + happy path + validation),
  * the DonorGiftAccessLink admin "revoke" action.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.schools.admin import DonorGiftAccessLinkAdmin
from apps.schools.advancement_services import mint_donor_access_link
from apps.schools.models import (
    AdvancementDonor,
    AdvancementGift,
    DonorGiftAccessLink,
    School,
)
from apps.schools.views_advancement import donation_capture

User = get_user_model()


def _attach_session_and_messages(request):
    SessionMiddleware(lambda req: HttpResponse()).process_request(request)
    request.session.save()
    MessageMiddleware(lambda req: HttpResponse()).process_request(request)


class DonorPortalHttpTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(
            name="Alpha Academy", slug="alpha-academy",
            subdomain="alpha-academy", is_active=True,
        )
        self.school_b = School.objects.create(
            name="Beta Academy", slug="beta-academy",
            subdomain="beta-academy", is_active=True,
        )
        self.donor_a = AdvancementDonor.objects.create(
            school=self.school_a, display_name="Alice Alpha-Donor",
        )
        self.donor_b = AdvancementDonor.objects.create(
            school=self.school_b, display_name="Bob Beta-Donor",
        )
        AdvancementGift.objects.create(
            donor=self.donor_a, amount=Decimal("111.11"), currency="USD",
            received_at=timezone.now().date(),
        )
        AdvancementGift.objects.create(
            donor=self.donor_b, amount=Decimal("222.22"), currency="USD",
            received_at=timezone.now().date(),
        )

    def _url(self, token):
        return reverse("accounts:donor_portal", args=[str(token)])

    def test_valid_token_renders_own_donor(self):
        link = mint_donor_access_link(self.donor_a)
        resp = self.client.get(self._url(link.token))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Alice Alpha-Donor")

    def test_valid_token_does_not_leak_other_tenant_donor(self):
        # The token is the only key and resolves to exactly one donor/school, so
        # the portal can never surface another tenant's donor or gifts.
        link = mint_donor_access_link(self.donor_a)
        resp = self.client.get(self._url(link.token))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Bob Beta-Donor")
        self.assertNotContains(resp, "Beta Academy")

    def test_unknown_token_is_rejected(self):
        import uuid

        resp = self.client.get(self._url(uuid.uuid4()))
        self.assertEqual(resp.status_code, 400)

    def test_expired_token_is_rejected(self):
        link = mint_donor_access_link(self.donor_a)
        DonorGiftAccessLink.objects.filter(pk=link.pk).update(
            expires_at=timezone.now() - timedelta(days=1)
        )
        resp = self.client.get(self._url(link.token))
        self.assertEqual(resp.status_code, 400)


class DonationCaptureHttpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Capture School", slug="capture-school",
            subdomain="capture-school", is_active=True,
        )
        self.staff = User.objects.create_user(
            username="capstaff", email="cap@example.com", password="x", is_staff=True,
        )

    def _post(self, data, *, with_school=True):
        r = self.factory.post("/backend/advancement/donations/capture/", data)
        r.user = self.staff
        if with_school:
            r.school = self.school
        _attach_session_and_messages(r)
        return r

    def test_staff_post_creates_gift(self):
        resp = donation_capture(
            self._post({"donor_name": "Walk-in Donor", "amount": "75.00", "currency": "USD"})
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            AdvancementGift.objects.filter(donor__school=self.school).count(), 1
        )
        gift = AdvancementGift.objects.get(donor__school=self.school)
        self.assertEqual(gift.amount, Decimal("75.00"))

    def test_missing_school_is_forbidden(self):
        resp = donation_capture(
            self._post(
                {"donor_name": "X", "amount": "5.00"}, with_school=False
            )
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(AdvancementGift.objects.count(), 0)

    def test_invalid_amount_records_nothing(self):
        resp = donation_capture(
            self._post({"donor_name": "Bad Amount", "amount": "-5"})
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AdvancementGift.objects.count(), 0)


class DonorAccessLinkAdminRevokeTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Revoke School", slug="revoke-school",
            subdomain="revoke-school", is_active=True,
        )
        self.donor = AdvancementDonor.objects.create(
            school=self.school, display_name="Linked Donor",
        )
        self.admin = DonorGiftAccessLinkAdmin(DonorGiftAccessLink, None)

    def _request(self):
        r = self.factory.post("/admin/")
        r.user = User.objects.create_user(
            username="adm", email="adm@example.com", password="x",
            is_staff=True, is_superuser=True,
        )
        _attach_session_and_messages(r)
        return r

    def test_revoke_expires_valid_link(self):
        link = mint_donor_access_link(self.donor)
        self.assertTrue(link.is_valid)
        self.admin.revoke_links(self._request(), DonorGiftAccessLink.objects.filter(pk=link.pk))
        link.refresh_from_db()
        self.assertFalse(link.is_valid)
        # Row is preserved (revoke != delete) so the access audit trail survives.
        self.assertTrue(DonorGiftAccessLink.objects.filter(pk=link.pk).exists())

    def test_revoke_skips_already_expired(self):
        link = mint_donor_access_link(self.donor)
        DonorGiftAccessLink.objects.filter(pk=link.pk).update(
            expires_at=timezone.now() - timedelta(days=2)
        )
        before = DonorGiftAccessLink.objects.get(pk=link.pk).expires_at
        self.admin.revoke_links(self._request(), DonorGiftAccessLink.objects.filter(pk=link.pk))
        after = DonorGiftAccessLink.objects.get(pk=link.pk).expires_at
        self.assertEqual(before, after)
