import json

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.global_registries.models import RegionConfig
from apps.observability.models import PlatformIncident
from apps.schools.models import School


class PlatformIncidentConsoleTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(
            code="OPS",
            name="Operations Region",
            default_language="en",
            timezone="UTC",
            date_format="YYYY-MM-DD",
            grading_scale="0-100",
            default_currency="USD",
        )
        self.school = School.objects.create(
            name="Incident School",
            slug="incident-school",
            subdomain="incident-school",
            default_region=self.region,
            is_active=True,
        )
        self.admin_user = User.objects.create_user(
            username="incident_admin",
            email="incident-admin@example.com",
            password="Test1234!",
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )
        self.incident = PlatformIncident.objects.create(
            title="Webhook backlog saturation",
            incident_type=PlatformIncident.IncidentType.INTEGRATION,
            severity=PlatformIncident.Severity.CRITICAL,
            status=PlatformIncident.Status.OPEN,
            summary="Webhook backlog is growing faster than retries are draining.",
            affected_school=self.school,
            affected_schema_name="incident_school",
            source_system="events",
            created_by=self.admin_user,
        )

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_manager_console_renders_platform_incident(self):
        self.client.force_login(self.admin_user)
        response = self.client.get("/ops/incidents/", HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Platform incident console")
        self.assertContains(response, self.incident.title)

    def test_api_returns_incidents_and_allows_status_transition(self):
        self.client.force_login(self.admin_user)

        response = self.client.get("/api/observability/incidents/", HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(len(payload["incidents"]), 1)
        self.assertEqual(payload["incidents"][0]["status"], PlatformIncident.Status.OPEN)

        response = self.client.post(
            f"/api/observability/incidents/{self.incident.id}/status/",
            data=json.dumps({"action": "acknowledge"}),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, PlatformIncident.Status.ACKNOWLEDGED)
        self.assertEqual(self.incident.acknowledged_by, self.admin_user)

    def test_api_requires_observability_auth(self):
        response = self.client.get("/api/observability/incidents/", HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 403)
