from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.platform_runtime.governance_queue import process_due_configuration_changes
from apps.platform_runtime.models import ConfigurationChangeRequest


class ScheduledChangeExecutionContractTests(TestCase):
    def test_processes_due_scheduled_only_and_keeps_external_blocked_changes_blocked(self):
        due = ConfigurationChangeRequest.objects.create(
            request_type=ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_type="workflow_pack",
            target_key="attendance-recovery",
            status=ConfigurationChangeRequest.Status.SCHEDULED,
            scheduled_at=timezone.now() - timedelta(minutes=5),
        )
        ConfigurationChangeRequest.objects.create(
            request_type=ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_type="workflow_pack",
            target_key="payments",
            status=ConfigurationChangeRequest.Status.SCHEDULED,
            scheduled_at=timezone.now() - timedelta(minutes=5),
            external_blockers=["psp_live_proof"],
        )
        ConfigurationChangeRequest.objects.create(
            request_type=ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_type="workflow_pack",
            target_key="future",
            status=ConfigurationChangeRequest.Status.SCHEDULED,
            scheduled_at=timezone.now() + timedelta(days=1),
        )

        with patch(
            "apps.platform_runtime.governance_queue.apply_approved_change_request",
            return_value={"ok": True, "audit_id": 123},
        ) as mocked:
            result = process_due_configuration_changes()

        self.assertEqual(result["processed"], 2)
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0].pk, due.pk)
        self.assertEqual(result["results"][1]["blocked"], "external_required")
