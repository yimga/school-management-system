"""Studio rail links + workflow correlation on event detail pages."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Permission
from apps.automation.workflow_graph_models import Workflow
from apps.events.models import DomainEvent
from apps.events.views_console import event_domain_detail
from apps.schools.models import School

User = get_user_model()


def _tenant_host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class EventSystemFinalizationStudioRailTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Finalize School",
            slug="finalize-school",
            subdomain="finalize-school",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="finalize_staff",
            password="pw",
            is_staff=True,
            role=User.Role.IT_ADMIN,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.staff.feature_permissions.add(manage_perm)

    def test_domain_detail_shows_automation_section_when_workflow_trigger_matches(self):
        Workflow.objects.create(
            school=self.school,
            name="Pay listener",
            trigger_event=Workflow.Trigger.PAYMENT_SUCCESS,
            status=Workflow.Status.PUBLISHED,
        )
        ev = DomainEvent.objects.create(
            event_type="payment_success",
            payload={"k": "v"},
            school_id=self.school.pk,
            status=DomainEvent.Status.PROCESSED,
            processed_at=timezone.now(),
        )
        req = self.factory.get(
            reverse("events:event_domain_detail", kwargs={"event_id": ev.pk})
        )
        req.user = self.staff
        req.school = self.school
        resp = event_domain_detail(req, event_id=ev.pk)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Used by automation", body)
        self.assertIn("Pay listener", body)
        self.assertIn("/automation/outcomes/", body)

    @patch(
        "apps.schools.control_plane.user_can_access_studio_on_request",
        return_value=True,
    )
    def test_studio_simulation_lists_domain_event_console_link(self, _mock):
        self.client.force_login(self.staff)
        url = reverse("studio_os:automation_simulation_engine")
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('/domain-events/', body)
        self.assertIn('data-rmc-studio-domain-events-link="1"', body)
