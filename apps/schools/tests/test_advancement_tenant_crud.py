"""Tenant advancement donor/gift CRUD (Wave 8 / wedge 5)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase

from apps.schools.models import AdvancementDonor, AdvancementGift, School
from apps.schools.views_advancement import (
    advancement_donor_create,
    advancement_donor_detail,
    advancement_donor_list,
)

User = get_user_model()


class AdvancementTenantCrudTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school_a = School.objects.create(
            name="School A",
            slug="school-a",
            subdomain="school-a",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="School B",
            slug="school-b",
            subdomain="school-b",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="advstaff",
            email="a@example.com",
            password="x",
            is_staff=True,
        )

    @staticmethod
    def _attach_session_and_messages(request):
        """RequestFactory requests lack session/messages; views using messages need this."""
        SessionMiddleware(lambda req: HttpResponse()).process_request(request)
        request.session.save()
        MessageMiddleware(lambda req: HttpResponse()).process_request(request)

    def _req(self, method, path, data=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = self.staff
        r.school = self.school_a
        self._attach_session_and_messages(r)
        return r

    def test_list_requires_school(self):
        r = self.factory.get("/backend/advancement/donors/")
        r.user = self.staff
        resp = advancement_donor_list(r)
        self.assertEqual(resp.status_code, 403)

    def test_create_and_list(self):
        resp = advancement_donor_create(
            self._req(
                "POST",
                "/add/",
                {
                    "display_name": "Jane Donor",
                    "email": "jane@example.org",
                },
            )
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            AdvancementDonor.objects.filter(school=self.school_a).count(), 1
        )
        d = AdvancementDonor.objects.get(school=self.school_a)
        self.assertEqual(d.display_name, "Jane Donor")

        resp = advancement_donor_list(self._req("GET", "/"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jane Donor")

    def test_cannot_access_other_school_donor(self):
        other = AdvancementDonor.objects.create(
            school=self.school_b,
            display_name="Other",
        )
        with self.assertRaises(Http404):
            advancement_donor_detail(
                self._req("GET", f"/{other.pk}/"), donor_id=other.pk
            )

    def test_add_gift(self):
        d = AdvancementDonor.objects.create(
            school=self.school_a,
            display_name="G",
        )
        resp = advancement_donor_detail(
            self._req(
                "POST",
                f"/{d.pk}/",
                {
                    "action": "add_gift",
                    "amount": "100.50",
                    "currency": "USD",
                    "campaign_name": "Spring Gala",
                },
            ),
            donor_id=d.pk,
        )
        self.assertEqual(resp.status_code, 302)
        g = AdvancementGift.objects.get(donor=d)
        self.assertEqual(g.amount, Decimal("100.50"))
        self.assertEqual(g.campaign_name, "Spring Gala")
