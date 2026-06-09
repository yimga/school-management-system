"""WorkflowRun must be visible to poll APIs while provisioning is in flight."""

from __future__ import annotations

import inspect

from django.test import TestCase, override_settings

from apps.platform_runtime.models import WorkflowRun
from apps.platform_runtime.workflow_tracker import begin_run
from apps.schools.models import School
from apps.schools.provisioning_progress import resolve_provisioning_progress
from apps.schools.tasks import provision_school_sync


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ProvisioningWorkflowVisibilityTests(TestCase):
    def test_begin_run_is_visible_to_progress_api_immediately(self):
        school = School.objects.create(
            name="Visibility Academy",
            slug="visibility-academy",
            subdomain="visibility-academy",
            is_active=False,
        )
        run = begin_run(
            workflow_key="tenant_school_provision",
            steps=("admin_user", "profile", "tenant_schema", "seed_data", "activate"),
            school_id=str(school.id),
        )
        self.assertIsNotNone(run)
        self.assertTrue(WorkflowRun.objects.filter(pk=run.pk).exists())

        progress = resolve_provisioning_progress(school)
        self.assertEqual(progress.get("workflow_run_id"), run.pk)
        self.assertEqual(progress.get("status"), "running")
        self.assertTrue(progress.get("steps"))

    def test_provision_school_sync_not_hidden_by_outer_atomic(self):
        source = inspect.getsource(provision_school_sync)
        before_call = source.split("_do_provision(")[0]
        self.assertNotIn(
            "with transaction.atomic():",
            before_call,
            "outer atomic on provision_school_sync hides WorkflowRun from polls",
        )

    def test_no_fake_five_percent_when_not_started(self):
        school = School.objects.create(
            name="Not Started",
            slug="not-started-yet",
            subdomain="not-started-yet",
            is_active=False,
        )
        progress = resolve_provisioning_progress(school)
        self.assertEqual(progress.get("progress_percent"), 0)
        self.assertIsNone(progress.get("workflow_run_id"))
