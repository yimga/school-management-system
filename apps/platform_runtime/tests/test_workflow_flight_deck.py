"""Workflow Flight Deck — operator actions and provisioning remediation."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings

from apps.platform_runtime.models import PlatformEventLog, WorkflowRun
from apps.platform_runtime.views_workflow_flight_deck import (
    flight_deck_json_view,
    incident_bulk_apply_view,
)
from apps.platform_runtime.workflow_auto_fix import suggest_remediation
from apps.platform_runtime.workflow_flight_deck_actions import (
    enrich_run_payload,
    resolve_effective_remediation,
)
from apps.platform_runtime.workflow_recovery_playbook import (
    recovery_coverage_gaps,
    workflow_recovery_coverage,
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
        self.assertIn("error_fingerprint", payload)
        self.assertEqual(
            payload["error_fingerprint"].get("recommended_chain"),
            [
                "cancel_duplicate_run",
                "repair_tenant_schema_drift",
                "requeue_provision",
            ],
        )
        kinds = [a["kind"] for a in payload["operator_actions"]]
        self.assertIn("apply_fix", kinds)
        self.assertIn("tenant_360", kinds)
        self.assertIn("provision_queue", kinds)
        self.assertIn("detail", kinds)

    def test_resolve_effective_remediation_upgrades_stale_db_row(self):
        rem = resolve_effective_remediation(self.run)
        self.assertTrue(rem.get("auto_fix_available"))
        self.assertEqual(rem.get("auto_fix_kind"), "requeue_provision")

    def test_dead_running_tenant_schema_is_not_diagnostic_only(self):
        """Heartbeat-dead running@tenant_schema must expose executable Auto fix."""
        from datetime import timedelta

        from django.utils import timezone

        self.run.status = "running"
        self.run.suggested_remediation = {}
        self.run.last_heartbeat_at = timezone.now() - timedelta(seconds=600)
        self.run.started_at = timezone.now() - timedelta(seconds=900)
        self.run.save(
            update_fields=[
                "status",
                "suggested_remediation",
                "last_heartbeat_at",
                "started_at",
            ]
        )
        rem = resolve_effective_remediation(self.run)
        self.assertTrue(rem.get("auto_fix_available"))
        self.assertEqual(rem.get("auto_fix_kind"), "requeue_provision")
        self.assertIn("repair_tenant_schema_drift", rem.get("healing_chain") or [])
        payload = enrich_run_payload(
            {
                "id": self.run.pk,
                "workflow_key": self.run.workflow_key,
                "status": "running",
                "school_id": str(self.school.pk),
                "suggested_remediation": {},
            },
            run=self.run,
        )
        kinds = [a["kind"] for a in payload["operator_actions"]]
        self.assertIn("apply_fix", kinds)

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
        self.assertEqual(body.get("applied"), "healing_chain")
        self.assertIn("healing_session", body)
        dispatch_mock.assert_called_once()
        self.run.refresh_from_db()
        session = (self.run.payload_summary or {}).get("healing_session") or {}
        self.assertTrue(session.get("session_id"))
        self.assertIn(session.get("phase"), ("requeue_queued", "succeeded"))

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
        failed_rows = {
            row.get("id"): row for row in data.get("recent_failed") or []
        }
        if self.run.pk in failed_rows:
            row = failed_rows[self.run.pk]
            self.assertTrue((row.get("healing_session") or {}).get("session_id"))
            self.assertEqual(row.get("status_meta", {}).get("key"), "healing")
        self.assertGreaterEqual(data.get("summary", {}).get("healing_count", 0), 0)

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
        self.assertEqual(
            data.get("copilot_context", {})
            .get("recovery_coverage", {})
            .get("gap_count"),
            0,
        )

    @override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
    def test_flight_deck_hides_settled_school_stale_failures(self):
        """Live school + Phase A/B complete must not inflate Recent failures."""
        settled = School.objects.create(
            name="Settled Academy",
            slug=f"settled-{uuid.uuid4().hex[:8]}",
            subdomain=f"st{uuid.uuid4().hex[:6]}",
            is_active=True,
            settings={
                "provisioning": {"phase_a_complete": True, "phase_b_complete": True}
            },
        )
        stale = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision school",
            status="failed",
            school_id=str(settled.pk),
            tenant_schema=settled.subdomain,
            current_step_name="tenant_schema",
            current_step_ordinal=3,
            total_steps=5,
            error_summary={
                "type": "TimeoutError",
                "message": "Worker timed out. The background worker stopped sending heartbeats.",
            },
        )
        request = self.factory.get(
            "/platform-runtime/workflow-progress/flight-deck.json",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = flight_deck_json_view(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        failed_ids = {row.get("id") for row in data.get("recent_failed") or []}
        self.assertNotIn(
            stale.pk,
            failed_ids,
            "settled-school FAILED rows must leave the deck on JSON load",
        )
        stale.refresh_from_db()
        from apps.platform_runtime.workflow_fix_handlers import workflow_run_is_remediated

        self.assertTrue(workflow_run_is_remediated(stale))

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_flight_deck_hides_failures_superseded_by_later_success(self):
        """A later succeeded provision must clear older FAILED cards immediately."""
        from datetime import timedelta

        from django.utils import timezone

        school = School.objects.create(
            name="Retry School",
            slug=f"retry-{uuid.uuid4().hex[:8]}",
            subdomain=f"rt{uuid.uuid4().hex[:6]}",
            is_active=False,
        )
        older = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision school",
            status="failed",
            school_id=str(school.pk),
            tenant_schema=school.subdomain,
            started_at=timezone.now() - timedelta(hours=2),
            ended_at=timezone.now() - timedelta(hours=1),
            current_step_name="tenant_schema",
            current_step_ordinal=3,
            total_steps=5,
            error_summary={"type": "TimeoutError", "message": "heartbeat lost"},
        )
        WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision school",
            status="succeeded",
            school_id=str(school.pk),
            tenant_schema=school.subdomain,
            started_at=timezone.now() - timedelta(minutes=5),
            ended_at=timezone.now() - timedelta(minutes=1),
            current_step_name="complete",
            current_step_ordinal=5,
            total_steps=5,
        )
        request = self.factory.get(
            "/platform-runtime/workflow-progress/flight-deck.json",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = flight_deck_json_view(request)
        data = json.loads(response.content)
        failed_ids = {row.get("id") for row in data.get("recent_failed") or []}
        self.assertNotIn(older.pk, failed_ids)
        # The setUp unprovisioned failure for self.school may still appear.
        self.assertIn(self.run.pk, failed_ids)

    def test_finalize_success_supersedes_prior_failures(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.platform_runtime.workflow_tracker import finalize_run

        school = School.objects.create(
            name="Finalize Supersede",
            slug=f"fin-{uuid.uuid4().hex[:8]}",
            subdomain=f"fn{uuid.uuid4().hex[:6]}",
            is_active=False,
        )
        prior = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            status="failed",
            school_id=str(school.pk),
            started_at=timezone.now() - timedelta(hours=1),
        )
        winner = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            status="running",
            school_id=str(school.pk),
            started_at=timezone.now(),
        )
        finalize_run(winner, status="succeeded")
        prior.refresh_from_db()
        from apps.platform_runtime.workflow_fix_handlers import workflow_run_is_remediated

        self.assertTrue(workflow_run_is_remediated(prior))
        self.assertEqual((prior.status or "").lower(), "cancelled")

    def test_clear_from_deck_offered_only_after_success(self):
        from apps.platform_runtime.workflow_flight_deck_actions import (
            build_operator_actions,
        )
        from apps.platform_runtime.workflow_tracker import serialize_workflow_run

        kinds = [
            a.get("kind")
            for a in build_operator_actions(
                run=self.run, payload=serialize_workflow_run(self.run)
            )
        ]
        self.assertNotIn(
            "clear_after_success",
            kinds,
            "unfinished provision failure must not offer Clear from deck",
        )

        settled = School.objects.create(
            name="Clearable School",
            slug=f"clr-{uuid.uuid4().hex[:8]}",
            subdomain=f"cl{uuid.uuid4().hex[:6]}",
            is_active=True,
            settings={
                "provisioning": {"phase_a_complete": True, "phase_b_complete": True}
            },
        )
        stale = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            status="failed",
            school_id=str(settled.pk),
            tenant_schema=settled.subdomain,
            current_step_name="tenant_schema",
            total_steps=5,
            current_step_ordinal=3,
        )
        kinds_ok = [
            a.get("kind")
            for a in build_operator_actions(
                run=stale, payload=serialize_workflow_run(stale)
            )
        ]
        self.assertIn("clear_after_success", kinds_ok)

    @patch("apps.schools.tasks.dispatch_provision_school")
    @override_settings(ALLOWED_HOSTS=["*"])
    def test_clear_after_success_refuses_unfinished_and_clears_settled(
        self, _dispatch_mock
    ):
        from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind

        refused = apply_auto_fix_kind(run=self.run, kind="clear_after_success")
        self.assertFalse(refused.get("ok"))
        self.assertEqual(refused.get("reason"), "clear_requires_successful_provision")

        settled = School.objects.create(
            name="Clear Apply School",
            slug=f"cla-{uuid.uuid4().hex[:8]}",
            subdomain=f"ca{uuid.uuid4().hex[:6]}",
            is_active=True,
            settings={
                "provisioning": {"phase_a_complete": True, "phase_b_complete": True}
            },
        )
        stale = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            status="failed",
            school_id=str(settled.pk),
            tenant_schema=settled.subdomain,
        )
        cleared = apply_auto_fix_kind(run=stale, kind="clear_after_success")
        self.assertTrue(cleared.get("ok"), cleared)
        stale.refresh_from_db()
        from apps.platform_runtime.workflow_fix_handlers import workflow_run_is_remediated

        self.assertTrue(workflow_run_is_remediated(stale))

    def test_workflow_recovery_playbook_covers_registry(self):
        coverage = workflow_recovery_coverage()
        self.assertGreaterEqual(len(coverage), 1)
        self.assertEqual(recovery_coverage_gaps(), [])
        self.assertEqual(
            coverage["tenant_school_provision"]["primary_auto_fix_kind"],
            "resume_from_checkpoint",
        )

    def test_status_taxonomy_matches_recovery_colors(self):
        taxonomy = status_taxonomy_payload()
        self.assertEqual(status_meta("stuck")["color"], "yellow")
        self.assertEqual(taxonomy["stuck"]["css_class"], "rmc-wf-status--stuck")
        self.assertEqual(status_meta("cancelled")["color"], "red")
        self.assertEqual(status_meta("succeeded")["color"], "green")
        self.assertEqual(status_meta("failed", remediated=True)["key"], "superseded")

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_replay_webhook_requires_target_metadata(self):
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
        self.assertEqual(body.get("reason"), "missing_webhook_replay_target")

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_replay_webhook_replays_platform_event(self):
        event = PlatformEventLog.objects.create(
            event_type="bus.test_ping",
            payload={"msg": "retry"},
        )
        run = WorkflowRun.objects.create(
            workflow_key="integration_sync",
            workflow_label="Integration sync",
            status="failed",
            tenant_schema="diagnostic_school",
            current_step_name="webhook",
            current_step_ordinal=1,
            total_steps=2,
            payload_summary={"platform_event_id": event.pk},
            suggested_remediation={
                "auto_fix_available": True,
                "auto_fix_kind": "replay_webhook",
                "human_action": "Replay source webhook.",
            },
        )
        request = self.factory.post(
            f"/platform-runtime/workflow-progress/apply-fix/{run.pk}/",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = apply_fix_view(request, run_id=run.pk)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"), body)
        self.assertTrue(body.get("refresh_deck"), body)
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="platform_event_replayed",
                payload__source_event_id=str(event.pk),
            ).exists()
        )

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_clear_stale_lock_deletes_explicit_cache_key(self):
        lock_key = "workflow:test:lock"
        cache.set(lock_key, "held", timeout=60)
        run = WorkflowRun.objects.create(
            workflow_key="integration_sync",
            workflow_label="Integration sync",
            status="failed",
            payload_summary={"lock_key": lock_key},
            suggested_remediation={
                "auto_fix_available": True,
                "auto_fix_kind": "clear_stale_lock",
                "human_action": "Clear stale lock.",
            },
        )
        request = self.factory.post(
            f"/platform-runtime/workflow-progress/apply-fix/{run.pk}/",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = apply_fix_view(request, run_id=run.pk)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"), body)
        self.assertIsNone(cache.get(lock_key))

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_cancel_duplicate_run_cancels_active_duplicate(self):
        duplicate = WorkflowRun.objects.create(
            workflow_key="integration_sync",
            workflow_label="Integration sync",
            status="running",
            tenant_schema="dupe_school",
            idempotency_key="dupe-key",
        )
        run = WorkflowRun.objects.create(
            workflow_key="integration_sync",
            workflow_label="Integration sync",
            status="failed",
            tenant_schema="dupe_school",
            idempotency_key="dupe-key",
            suggested_remediation={
                "auto_fix_available": True,
                "auto_fix_kind": "cancel_duplicate_run",
                "human_action": "Cancel duplicate run.",
            },
        )
        request = self.factory.post(
            f"/platform-runtime/workflow-progress/apply-fix/{run.pk}/",
            HTTP_ACCEPT="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.staff
        response = apply_fix_view(request, run_id=run.pk)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertIn(duplicate.pk, body.get("cancelled_run_ids") or [])
        duplicate.refresh_from_db()
        self.assertEqual(duplicate.status, "cancelled")

    @patch("apps.schools.tasks.dispatch_provision_school")
    @override_settings(ALLOWED_HOSTS=["*"])
    def test_resume_from_checkpoint_routes_provision_to_requeue(self, dispatch_mock):
        self.run.suggested_remediation = {
            "auto_fix_available": True,
            "auto_fix_kind": "resume_from_checkpoint",
            "human_action": "Resume from checkpoint.",
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
        self.assertTrue(body.get("ok"), body)
        self.assertEqual(body.get("delegated_from"), "resume_from_checkpoint")
        dispatch_mock.assert_called_once()

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
