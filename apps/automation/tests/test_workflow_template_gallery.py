"""Workflow template gallery — eight curated templates."""

import json

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.automation.views_workflow_gallery import (
    workflow_template_dry_run,
    workflow_template_gallery,
)
from apps.automation.workflow_template_gallery import (
    REQUIRED_TEMPLATE_IDS,
    WORKFLOW_TEMPLATE_GALLERY,
)
from apps.schools.models import School


class WorkflowTemplateGalleryTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="WF Gallery",
            slug="wf-gallery",
            subdomain="wf-gallery",
            country_code="CM",
            is_active=True,
        )
        cls.user = User.objects.create_user(
            username="wf_gal_staff",
            password="p" * 8,
            is_staff=True,
        )

    def test_all_templates_present(self):
        self.assertEqual(len(WORKFLOW_TEMPLATE_GALLERY), 8)
        self.assertEqual(len(REQUIRED_TEMPLATE_IDS), 8)
        for t in WORKFLOW_TEMPLATE_GALLERY:
            self.assertTrue(t.get("trigger"))
            self.assertTrue(t.get("condition"))
            self.assertTrue(t.get("action"))

    def test_route_returns_200(self):
        req = RequestFactory().get("/automation/workflow-template-gallery/")
        req.user = self.user
        req.school = self.school
        resp = workflow_template_gallery(req)
        self.assertEqual(resp.status_code, 200)

    def test_dry_run_returns_synthetic_when_no_published_workflow(self):
        req = RequestFactory().get(
            "/automation/workflow-template-gallery/missing_attendance_reminder/dry-run/"
        )
        req.user = self.user
        req.school = self.school
        resp = workflow_template_dry_run(req, "missing_attendance_reminder")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("mode"), "synthetic_dry_run")
        self.assertEqual(data.get("trigger_key"), "attendance_saved")
