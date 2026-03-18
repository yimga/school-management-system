import os
from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.observability.models import PlatformIncident
from apps.schools.models import School, SchoolProvisioningEvent
from apps.siteconfig.models_feature_controls import GlobalSupportTicket


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class PublicExecutionPlanPagesTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_phase1_public_pages_render(self):
        pages = [
            "/product/",
            "/solutions/",
            "/pricing/",
            "/compare/",
            "/case-studies/",
            "/security-compliance/",
            "/integrations/",
            "/book-demo/",
            "/solutions/k12-school-management-system/",
            "/solutions/multi-campus-school-software/",
            "/solutions/student-passport-transcript-portability/",
        ]
        for path in pages:
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_HOST="runmycampus.com")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "RunMyCampus")

    def test_discovery_and_find_show_role_based_quick_start(self):
        discover = self.client.get("/discover/", HTTP_HOST="runmycampus.com")
        finder = self.client.get("/find/", HTTP_HOST="runmycampus.com")
        self.assertEqual(discover.status_code, 200)
        self.assertEqual(finder.status_code, 200)
        self.assertContains(discover, "Role-based quick start")
        self.assertContains(finder, "Role-based quick start")

    def test_sitemap_contains_new_marketing_routes(self):
        response = self.client.get("/sitemap.xml", HTTP_HOST="runmycampus.com")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("/product/", body)
        self.assertIn("/book-demo/", body)
        self.assertIn("/solutions/k12-school-management-system/", body)


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class SuperCommandCenterTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self.superuser = User.objects.create_superuser(
            username="root-admin",
            email="root-admin@example.com",
            password="pass1234",
        )
        self.client.force_login(self.superuser)

        school = School.objects.create(
            name="Mission Control School",
            slug="mission-control-school",
            subdomain="mission-control-school",
            is_active=True,
        )

        SchoolProvisioningEvent.objects.create(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
            status=SchoolProvisioningEvent.Status.INFO,
        )
        completed = SchoolProvisioningEvent.objects.create(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.COMPLETED,
            status=SchoolProvisioningEvent.Status.SUCCESS,
        )
        SchoolProvisioningEvent.objects.filter(id=completed.id).update(
            created_at=timezone.now() + timedelta(hours=2)
        )

        stale = GlobalSupportTicket.objects.create(
            school=school,
            user=self.superuser,
            subject="Critical tenant issue",
            body="Need urgent help",
            priority=GlobalSupportTicket.Priority.URGENT,
            status=GlobalSupportTicket.Status.OPEN,
        )
        GlobalSupportTicket.objects.filter(id=stale.id).update(
            created_at=timezone.now() - timedelta(hours=72)
        )

        PlatformIncident.objects.create(
            title="Queue test incident",
            incident_type=PlatformIncident.IncidentType.AVAILABILITY,
            severity=PlatformIncident.Severity.HIGH,
            status=PlatformIncident.Status.OPEN,
            summary="Manager console should surface unresolved incidents.",
            affected_school=school,
            created_by=self.superuser,
        )

    def tearDown(self):
        self.env.stop()

    def test_super_dashboard_contains_control_plane_surface(self):
        response = self.client.get("/super/", HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Control Plane")
        self.assertContains(response, "Operator queues")
        self.assertContains(response, "School registry")
        self.assertContains(response, "Control modules")

    def test_super_command_center_route_renders(self):
        response = self.client.get(
            "/super/command-center/", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operational queues")
        self.assertContains(response, "Platform incidents")
        self.assertContains(response, "Schools needing intervention")

    def test_super_metadata_catalog_route_renders(self):
        response = self.client.get(
            "/super/metadata-catalog/", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Metadata Catalog")
        self.assertContains(response, "Platform catalog")

    def test_super_tenant_studio_route_renders(self):
        response = self.client.get(
            "/super/create/", HTTP_HOST="manager.runmycampus.com"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tenant Studio")
        self.assertContains(response, "Create Tenant")

    def test_super_scroll_sensitive_routes_render(self):
        surfaces = [
            ("/super/marketplace/", "Marketplace governance"),
            ("/super/workflow-packs/", "Workflow Packs"),
            ("/super/dashboard-packs/", "Dashboard Packs"),
            ("/super/marketplace/blueprints/", "Blueprint marketplace"),
        ]
        for path, marker in surfaces:
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_HOST="manager.runmycampus.com")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, marker)
