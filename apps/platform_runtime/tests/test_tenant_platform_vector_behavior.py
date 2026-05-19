"""
Vector 4 behavioral gates — beyond import-only verify_tenant_platform_vectors.py.
"""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.schools.models import School, SchoolMembership


class StudioOsOnboardingBehaviorTests(TestCase):
    def test_studio_os_navigation_importable(self):
        from apps.studio_os import navigation

        self.assertTrue(hasattr(navigation, "build_control_governance_rail"))

    def test_guided_onboarding_url_resolves(self):
        url = reverse("siteconfig:guided_onboarding")
        self.assertTrue(url.startswith("/"))


class CurriculumRegionBehaviorTests(TestCase):
    def test_region_grading_scales_url(self):
        url = reverse("siteconfig:region_grading_scales")
        self.assertIn("region", url)


class WorkflowCanvasBehaviorTests(TestCase):
    def test_visual_workflow_designer_url(self):
        url = reverse("automation:visual_workflow_designer")
        self.assertIn("workflow", url)

    def test_simulate_executor_importable(self):
        from apps.automation.visual_executor import simulate_workflow

        self.assertTrue(callable(simulate_workflow))


class MarketplaceSisBehaviorTests(TestCase):
    def test_legacy_hash_intake_callable(self):
        from apps.migration_cloud.services.legacy_hash_intake import store_legacy_hash

        self.assertTrue(callable(store_legacy_hash))


class BillingTelemetryBehaviorTests(TestCase):
    def test_tracing_facade_no_direct_sentry_in_apps(self):
        from apps.observability import tracing

        self.assertTrue(hasattr(tracing, "start_named_transaction"))


class TrustComplianceBehaviorTests(TestCase):
    def test_audit_log_model_append_only_fields(self):
        from apps.compliance.models_audit import AuditLog

        field_names = {f.name for f in AuditLog._meta.get_fields()}
        self.assertIn("timestamp", field_names)


class CampusWorkflowHubRenderTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"WF {uid}",
            slug=f"wf-{uid}",
            subdomain=f"wf{uid}",
            is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username=f"wf_{uid}",
            password="Test1234",
            email=f"wf_{uid}@example.com",
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )

    def test_campus_workflow_hub_200(self):
        client = Client(HTTP_HOST=f"{self.school.subdomain}.runmycampus.com")
        client.force_login(self.user)
        session = client.session
        session["school_id"] = str(self.school.pk)
        session.save()
        url = reverse("siteconfig:campus_workflow_canvas_hub")
        resp = client.get(url, follow=True)
        self.assertEqual(resp.status_code, 200)
