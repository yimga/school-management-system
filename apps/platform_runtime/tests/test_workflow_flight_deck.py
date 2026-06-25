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
from apps.platform_runtime.workflow_status_taxonomy import status_meta, status_taxonomy_payload
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

    def test_resolve_upgrades_retry_backoff_to_requeue_for_provision(self):
        self.run.suggested_remediation = {
            "auto_fix_available": True,
            "auto_fix_kind": "retry_once_with_backoff",
            "human_action": "Upstream service did not respond in time.",
            "remediation_key": "upstream_timeout",
        }
        rem = resolve_effective_remediation(self.run)
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
        self.assertTrue(body.get("refresh_deck"), body)
        self.assertEqual(body.get("remediated_run_id"), self.run.pk)
        dispatch_mock.assert_called_once()
        self.run.refresh_from_db()
        self.assertIn("workflow_fix_remediation", self.run.payload_summary)
        self.assertFalse(self.run.suggested_remediation.get("auto_fix_available"))

    @patch("apps.schools.tasks.dispatch_provision_school")
    @override_settings(ALLOWED_HOSTS=["*"])
    def test_apply_fix_removes_remediated_run_from_failure_deck(self, dispatch_mock):
        request = self.factory.post(
            f"/platform-runtime/workflow-progress/apply-fix/{self.run.pk}/",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        apply_response = apply_fix_view(request, run_id=self.run.pk)
        self.assertEqual(apply_response.status_code, 200)
        dispatch_mock.assert_called_once()

        deck_request = self.factory.get(
            "/platform-runtime/workflow-progress/flight-deck.json",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        deck_request.user = self.staff
        deck_response = flight_deck_json_view(deck_request)
        self.assertEqual(deck_response.status_code, 200)
        data = json.loads(deck_response.content)
        failed_ids = {row.get("id") for row in data.get("recent_failed") or []}
        self.assertNotIn(self.run.pk, failed_ids)
        self.assertIn("healing_count", data.get("summary") or {})

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
        self.assertIn("stream", data["endpoints"])
        self.assertIn("summary", data)
        failed = data.get("recent_failed") or []
        self.assertTrue(failed)
        row = failed[0]
        self.assertIn("operator_actions", row)
        self.assertTrue(row["operator_actions"])
        apply_action = next(
            (a for a in row["operator_actions"] if a.get("kind") == "apply_fix"),
            None,
        )
        self.assertIsNotNone(apply_action)
        self.assertTrue(apply_action.get("requires_network"))
        self.assertEqual(apply_action.get("capability", {}).get("mode"), "execute")

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_flight_deck_json_includes_status_taxonomy(self):
        request = self.factory.get(
            "/platform-runtime/workflow-progress/flight-deck.json",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = flight_deck_json_view(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        taxonomy = data.get("status_taxonomy") or {}
        self.assertEqual(taxonomy["stuck"]["color"], "yellow")
        self.assertEqual(taxonomy["failed"]["color"], "red")
        self.assertEqual(taxonomy["cancelled"]["color"], "red")
        self.assertEqual(taxonomy["succeeded"]["color"], "green")
        self.assertIn("recovery_queue", data.get("copilot_context") or {})

    def test_status_taxonomy_matches_recovery_colors(self):
        taxonomy = status_taxonomy_payload()
        self.assertEqual(status_meta("stuck")["color"], "yellow")
        self.assertEqual(taxonomy["stuck"]["css_class"], "rmc-wf-status--stuck")
        self.assertEqual(status_meta("cancelled")["color"], "red")
        self.assertEqual(status_meta("succeeded")["color"], "green")
        self.assertEqual(status_meta("failed", remediated=True)["key"], "superseded")

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_diagnostic_only_fix_returns_explanation(self):
        run = WorkflowRun.objects.create(
            workflow_key="integration_sync",
            workflow_label="Integration sync",
            status="failed",
            tenant_schema="diagnostic_school",
            current_step_name="webhook",
            current_step_ordinal=1,
            total_steps=2,
            suggested_remediation={
                "auto_fix_available": True,
                "auto_fix_kind": "replay_webhook",
                "human_action": "Replay source webhook after checking source metadata.",
            },
        )
        request = self.factory.post(
            f"/platform-runtime/workflow-progress/apply-fix/{run.pk}/",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = apply_fix_view(request, run_id=run.pk)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertFalse(body.get("ok"))
        self.assertEqual(body.get("reason"), "diagnostic_only")
        self.assertEqual(body.get("capability", {}).get("mode"), "diagnostic")

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
        self.assertIn("Recovery intelligence", content)

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
        self.assertTrue(body.get("refresh_deck"))
        self.assertEqual(body.get("healing_poll_ms"), 2500)
        dispatch_mock.assert_called()
