"""Workflow Flight Deck — operator actions and provisioning remediation."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings

from apps.platform_runtime.models import WorkflowRun
from apps.platform_runtime.views_workflow_flight_deck import (
    flight_deck_json_view,
    incident_bulk_apply_view,
)
from apps.platform_runtime.workflow_auto_fix import suggest_remediation
from apps.platform_runtime.workflow_flight_deck_actions import (
    enrich_run_payload,
    resolve_effective_remediation,
)
from apps.platform_runtime.views_workflow_progress import apply_fix_view
from apps.schools.models import School

User = get_user_model()
_MANAGER_HOST = "manager.runmycampus.com"


class ProvisionRemediationTests(TestCase):
    def test_provision_database_failure_offers_requeue(self):
        rem = suggest_remediation(
            error_type="OperationalError",
            error_message="relation foo does not exist",
            workflow_key="tenant_school_provision",
        )
        self.assertTrue(rem.get("auto_fix_available"))
        self.assertEqual(rem.get("auto_fix_kind"), "requeue_provision")

    def test_slug_collision_keeps_alternate_slug_fix(self):
        rem = suggest_remediation(
            error_type="IntegrityError",
            error_message="UNIQUE constraint failed: schools.slug",
            workflow_key="tenant_school_provision",
        )
        self.assertEqual(rem.get("auto_fix_kind"), "suggest_alternate_slug")


class FlightDeckEnrichmentTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.staff = User.objects.create_user(
            username="flight_deck_staff",
            email="flight_deck_staff@example.com",
            password="Test1234!long",
            is_staff=True,
            is_superuser=True,
        )
        self.school = School.objects.create(
            name="Flight Deck School",
            slug=f"fd-{uuid.uuid4().hex[:8]}",
            subdomain=f"fd{uuid.uuid4().hex[:6]}",
            is_active=False,
        )
        self.run = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision school",
            status="failed",
            school_id=str(self.school.pk),
            tenant_schema=self.school.subdomain,
            current_step_name="tenant_schema",
            current_step_ordinal=3,
            total_steps=5,
            suggested_remediation={
                "verdict": "match",
                "remediation_key": "database_error_generic",
                "human_action": "Database error",
                "auto_fix_available": False,
            },
            error_summary={"type": "OperationalError", "message": "schema drift"},
        )

    def test_enrich_failed_provision_adds_requeue_actions(self):
        payload = enrich_run_payload(
            {
                "id": self.run.pk,
                "workflow_key": self.run.workflow_key,
                "status": "failed",
                "school_id": str(self.school.pk),
                "suggested_remediation": self.run.suggested_remediation,
            },
            run=self.run,
        )
        self.assertTrue(payload["suggested_remediation"]["auto_fix_available"])
        kinds = [a["kind"] for a in payload["operator_actions"]]
        self.assertIn("apply_fix", kinds)
        self.assertIn("tenant_360", kinds)
        self.assertIn("provision_queue", kinds)
        self.assertIn("detail", kinds)

    def test_resolve_effective_remediation_upgrades_stale_db_row(self):
        rem = resolve_effective_remediation(self.run)
        self.assertTrue(rem.get("auto_fix_available"))
        self.assertEqual(rem.get("auto_fix_kind"), "requeue_provision")

    @patch("apps.schools.tasks.dispatch_provision_school")
    @override_settings(ALLOWED_HOSTS=["*"])
    def test_apply_fix_works_with_stale_db_remediation(self, dispatch_mock):
        """Apply fix must not read only raw DB row when legacy rows lack auto_fix."""
        request = self.factory.post(
            f"/platform-runtime/workflow-progress/apply-fix/{self.run.pk}/",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = apply_fix_view(request, run_id=self.run.pk)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"), body)
        dispatch_mock.assert_called_once()

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_flight_deck_json_includes_operator_actions(self):
        request = self.factory.get(
            "/platform-runtime/workflow-progress/flight-deck.json",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = flight_deck_json_view(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("endpoints", data)
        self.assertIn("labels", data)
        self.assertIn("summary", data)
        failed = data.get("recent_failed") or []
        self.assertTrue(failed)
        row = failed[0]
        self.assertIn("operator_actions", row)
        self.assertTrue(row["operator_actions"])

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_run_detail_renders_html_for_browser(self):
        client = Client()
        client.force_login(self.staff)
        response = client.get(
            f"/platform-runtime/workflow-progress/detail/{self.run.pk}/",
            HTTP_HOST=_MANAGER_HOST,
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("workflow-run-detail", content)
        self.assertIn("Operator actions", content)

    @patch("apps.schools.tasks.dispatch_provision_school")
    @override_settings(ALLOWED_HOSTS=["*"])
    def test_apply_fix_requeue_on_failed_run(self, dispatch_mock):
        self.run.suggested_remediation = {
            "auto_fix_available": True,
            "auto_fix_kind": "requeue_provision",
            "human_action": "Requeue",
        }
        self.run.save(update_fields=["suggested_remediation"])
        request = self.factory.post(
            f"/platform-runtime/workflow-progress/apply-fix/{self.run.pk}/",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = apply_fix_view(request, run_id=self.run.pk)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))
        dispatch_mock.assert_called_once()

    @patch("apps.schools.tasks.dispatch_provision_school")
    @override_settings(ALLOWED_HOSTS=["*"])
    def test_incident_bulk_apply_requeues_eligible_runs(self, dispatch_mock):
        request = self.factory.post(
            "/platform-runtime/workflow-progress/incidents/bulk-apply/",
            data={"remediation_key": "database_error_generic"},
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = incident_bulk_apply_view(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertGreaterEqual(body.get("applied", 0), 1)
        dispatch_mock.assert_called()
