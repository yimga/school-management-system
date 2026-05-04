"""First 100 schools tracker — lightweight acquisition view."""

from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.sales.models import Lead, PipelineStage

_MANAGER = "config.manager_urls"


@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ALLOWED_HOSTS=[
        "testserver",
        "127.0.0.1",
        "localhost",
        "manager.runmycampus.com",
    ],
)
class First100SchoolsDashboardTests(TestCase):
    _HOST = "manager.runmycampus.com"

    _SCHOOL = "Pilot Academy F100DM"

    @classmethod
    def setUpTestData(cls):
        Lead.objects.filter(school_name=cls._SCHOOL).delete()
        User.objects.filter(username__in=("f100_mer", "f100_owner")).delete()
        User.objects.create_user(
            username="f100_mer",
            password="p" * 8,
            is_superuser=True,
        )
        stage, _ = PipelineStage.objects.get_or_create(
            key="lead",
            defaults={"label": "Lead", "sort_order": 1},
        )
        owner = User.objects.create_user(
            username="f100_owner",
            password="p" * 8,
            is_staff=True,
        )
        lead = Lead.objects.create(
            school_name=cls._SCHOOL,
            stage=stage,
            notes="[region:CM] [type:private] [pilot:yes] [package:growth] [blocker:psp]",
            decision_maker="Head of school (test)",
            deal_owner=owner,
        )
        # Dashboard lists last 100 by -updated_at; other tests may create leads — stay on top.
        Lead.objects.filter(pk=lead.pk).update(
            updated_at=timezone.now() + timedelta(seconds=5)
        )

    def setUp(self):
        super().setUp()
        Lead.objects.filter(school_name=self._SCHOOL).update(
            updated_at=timezone.now() + timedelta(days=1)
        )

    def test_dashboard_200_and_pilot_column(self):
        c = Client(HTTP_HOST=self._HOST)
        self.assertTrue(c.login(username="f100_mer", password="p" * 8))
        url = reverse("sales:first_100_schools_dashboard", urlconf=_MANAGER)
        r = c.get(url)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn(self._SCHOOL, body)
        self.assertIn("First 100", body)
        self.assertIn("Open lead", body)
        self.assertIn("Head of school (test)", body)
        self.assertIn("f100_owner", body)
