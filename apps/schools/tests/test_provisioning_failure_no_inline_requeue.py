"""Provisioning failure path must NOT re-dispatch provisioning inline.

Root cause (2026-07-16 follow-up to the provisioning self-heal watchdog):
on a provisioning failure, ``finalize_run``'s inline auto-remediation applied
``requeue_provision``, which re-entered provisioning **synchronously**::

    finalize_run(status="failed")
      -> try_auto_apply_on_failure
        -> apply_auto_fix_kind("requeue_provision")
          -> dispatch_provision_school            # inline re-drive
            -> provision_school_task (eager)
              -> _do_provision                    # RE-ENTRY of the failing drive

That inline re-drive is the recursion source, and it does DB work inside the
failing drive's transaction; when the ``_active_provision_drives`` re-entrancy
contextvar did not survive the Celery-eager boundary, the re-entrant drive
poisoned the transaction (``TransactionManagementError``) so the FAILED event /
finalize could not be written -- a real contributor to stuck provisioning runs.

Retry is now owned exclusively by the async provision watchdog + reconcile sweep
(``apps.schools.provision_watchdog`` -- heartbeat-staleness driven,
single-flighted, circuit-broken; its sweep query already picks up
``status="failed"`` runs). So the synchronous failure path must finalize the run
FAILED and record the FAILED event, but must NOT fire an inline requeue. This
test pins that contract so the recursion cannot silently return.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.platform_runtime.models import WorkflowAutopilotPolicy, WorkflowRun
from apps.schools.models import School, SchoolProvisioningEvent


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ProvisioningFailureNoInlineRequeueTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="No Inline Requeue Academy",
            slug="no-inline-requeue",
            subdomain="no-inline-requeue",
            is_active=False,
        )
        # Arm the autopilot policy that WOULD trigger the inline requeue, so this
        # test proves the suppression is behavioral (the fix) rather than an
        # accident of a disabled policy. suggest_remediation() returns
        # auto_fix_kind="requeue_provision" for any unmatched tenant_school_provision
        # error, so with this policy enabled the pre-fix code path reaches
        # dispatch_provision_school on every failure.
        WorkflowAutopilotPolicy.objects.update_or_create(
            workflow_key="tenant_school_provision",
            tenant_schema="",
            defaults={"allowed_auto_fix_kinds": ["requeue_provision"], "enabled": True},
        )

    @patch("apps.schools.tasks._do_provision_tracked")
    @patch("apps.schools.tasks.dispatch_provision_school")
    def test_failure_does_not_redispatch_provisioning_inline(
        self, mock_dispatch, mock_tracked
    ):
        from apps.schools.tasks import provision_school_sync

        mock_tracked.side_effect = RuntimeError("simulated tenant_schema failure")

        with self.assertRaises(RuntimeError):
            provision_school_sync(
                str(self.school.id), contact_email="owner@no-inline-requeue.test"
            )

        # The failing drive must NOT synchronously re-queue itself: that inline
        # re-dispatch is the recursion/transaction-poison source. The async
        # watchdog sweep owns the retry (out of band, once the heartbeat is stale).
        mock_dispatch.assert_not_called()

        # ...but it must still cleanly finalize the run FAILED and record FAILED
        # so polls and the watchdog can see the terminal state.
        run = WorkflowRun.objects.filter(
            workflow_key="tenant_school_provision",
            school_id=str(self.school.pk),
        ).first()
        self.assertIsNotNone(run, "WorkflowRun must exist after begin_run")
        self.assertEqual((run.status or "").lower(), "failed")
        self.assertTrue(
            SchoolProvisioningEvent.objects.filter(
                school=self.school, event_type="FAILED"
            ).exists(),
            "FAILED provisioning event must be recorded on the failure path",
        )
