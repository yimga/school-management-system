"""Canonical /super/wedge/<id>/ surfaces (45 wedges)."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class SuperWedgeCanonicalUrlTests(TestCase):
    host = "manager.runmycampus.com"

    def setUp(self):
        self.user = User.objects.create_user(
            username="wedge_canon",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        cache.clear()

    def test_wedge_index_200(self):
        url = reverse("super:wedge_index")
        r = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Operator page")

    def test_wedge_detail_1_and_44_and_404(self):
        r1 = self.client.get(
            reverse("super:wedge_operator_detail", kwargs={"wedge_id": 1}),
            HTTP_HOST=self.host,
        )
        self.assertEqual(r1.status_code, 200)
        self.assertContains(r1, "International")
        r44 = self.client.get(
            reverse("super:wedge_operator_detail", kwargs={"wedge_id": 44}),
            HTTP_HOST=self.host,
        )
        self.assertEqual(r44.status_code, 200)
        self.assertContains(r44, "Native Clever")
        r0 = self.client.get(
            reverse("super:wedge_operator_detail", kwargs={"wedge_id": 0}),
            HTTP_HOST=self.host,
        )
        self.assertEqual(r0.status_code, 404)

    def test_native_roster_console_get_200(self):
        url = reverse("super:native_roster_connectors")
        r = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
