"""Fast end-to-end verifier for Workflow Recovery Command Center."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from apps.platform_runtime.models import PlatformEventLog, WorkflowRun
from apps.platform_runtime.views_workflow_flight_deck import flight_deck_json_view
from apps.platform_runtime.views_workflow_progress import apply_fix_view
from apps.schools.models import School


class Command(BaseCommand):
    help = "Verify workflow recovery fix buttons, deck refresh contracts, and coverage."

    def handle(self, *args, **options):
        user = self._staff_user()
        factory = RequestFactory()
        created_runs: list[int] = []
        school = School.objects.create(
            name="Workflow Recovery Verify School",
            slug=f"wrv-{uuid.uuid4().hex[:8]}",
            subdomain=f"wrv{uuid.uuid4().hex[:6]}",
            is_active=False,
        )
        try:
            provision = WorkflowRun.objects.create(
                workflow_key="tenant_school_provision",
                workflow_label="Provision school",
                status="failed",
                school_id=str(school.pk),
                tenant_schema=school.subdomain,
                current_step_name="tenant_schema",
                current_step_ordinal=3,
                total_steps=5,
                suggested_remediation={
                    "auto_fix_available": True,
                    "auto_fix_kind": "resume_from_checkpoint",
                },
            )
            created_runs.append(provision.pk)
            with patch("apps.schools.tasks.dispatch_provision_school") as dispatch_mock:
                body = self._post_apply(factory, user, provision.pk)
                self._require(
                    body.get("delegated_from") == "resume_from_checkpoint",
                    f"resume_from_checkpoint did not delegate correctly: {body}",
                )
                self._require(dispatch_mock.called, "provision requeue was not dispatched")

            event = PlatformEventLog.objects.create(
                event_type="bus.test_ping",
                payload={"msg": "verify"},
            )
            replay = WorkflowRun.objects.create(
                workflow_key="operator-platform-events",
                workflow_label="Platform event replay",
                status="failed",
                payload_summary={"platform_event_id": event.pk},
                suggested_remediation={
                    "auto_fix_available": True,
                    "auto_fix_kind": "replay_webhook",
                },
            )
            created_runs.append(replay.pk)
            body = self._post_apply(factory, user, replay.pk)
            self._require(body.get("ok") is True, f"event replay failed: {body}")
            self._require(
                PlatformEventLog.objects.filter(
                    event_type="platform_event_replayed",
                    payload__source_event_id=str(event.pk),
                ).exists(),
                "event replay audit row was not written",
            )

            lock_key = "workflow:verify:lock"
            cache.set(lock_key, "held", 60)
            lock_run = WorkflowRun.objects.create(
                workflow_key="orchestration_process_due",
                workflow_label="Clear lock",
                status="failed",
                payload_summary={"lock_key": lock_key},
                suggested_remediation={
                    "auto_fix_available": True,
                    "auto_fix_kind": "clear_stale_lock",
                },
            )
            created_runs.append(lock_run.pk)
            body = self._post_apply(factory, user, lock_run.pk)
            self._require(body.get("ok") is True, f"clear lock failed: {body}")
            self._require(cache.get(lock_key) is None, "cache lock was not cleared")

            duplicate = WorkflowRun.objects.create(
                workflow_key="automation-workflow-create",
                workflow_label="Duplicate active",
                status="running",
                idempotency_key="workflow-verify-dupe",
            )
            created_runs.append(duplicate.pk)
            controller = WorkflowRun.objects.create(
                workflow_key="automation-workflow-create",
                workflow_label="Cancel duplicate",
                status="failed",
                idempotency_key="workflow-verify-dupe",
                suggested_remediation={
                    "auto_fix_available": True,
                    "auto_fix_kind": "cancel_duplicate_run",
                },
            )
            created_runs.append(controller.pk)
            body = self._post_apply(factory, user, controller.pk)
            self._require(
                duplicate.pk in (body.get("cancelled_run_ids") or []),
                f"duplicate was not cancelled: {body}",
            )

            deck_request = factory.get(
                "/platform-runtime/workflow-progress/flight-deck.json",
                HTTP_ACCEPT="application/json",
                HTTP_HOST="manager.runmycampus.com",
            )
            deck_request.user = user
            deck = json.loads(flight_deck_json_view(deck_request).content)
            coverage = deck.get("copilot_context", {}).get("recovery_coverage", {})
            self._require(coverage.get("gap_count") == 0, f"coverage gaps: {coverage}")
            self.stdout.write("WORKFLOW_RECOVERY_VERIFY_PASS")
        finally:
            WorkflowRun.objects.filter(pk__in=created_runs).delete()
            school.delete()

    def _staff_user(self):
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="workflow_recovery_verify_staff",
            defaults={
                "email": "workflow_recovery_verify_staff@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if not user.is_staff or not user.is_superuser:
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])
        return user

    def _post_apply(self, factory: RequestFactory, user, run_id: int) -> dict:
        request = factory.post(
            f"/platform-runtime/workflow-progress/apply-fix/{run_id}/",
            HTTP_ACCEPT="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = user
        response = apply_fix_view(request, run_id=run_id)
        body = json.loads(response.content)
        if response.status_code >= 400:
            raise CommandError(f"apply_fix failed status={response.status_code} body={body}")
        return body

    def _require(self, condition: bool, message: str) -> None:
        if not condition:
            raise CommandError(message)
