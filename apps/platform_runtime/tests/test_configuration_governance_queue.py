from django.test import TestCase

from apps.platform_runtime.governance_queue import governance_queue_snapshot
from apps.platform_runtime.models import ConfigurationChangeRequest


class ConfigurationGovernanceQueueTests(TestCase):
    def test_queue_counts_pending_failed_external_blocked_and_rollback_needed(self):
        ConfigurationChangeRequest.objects.create(
            request_type=ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_type="workflow_pack",
            target_key="attendance-recovery",
            status=ConfigurationChangeRequest.Status.PENDING_APPROVAL,
        )
        ConfigurationChangeRequest.objects.create(
            request_type=ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_type="workflow_pack",
            target_key="payments",
            status=ConfigurationChangeRequest.Status.FAILED,
            external_blockers=["psp_live_proof"],
        )
        ConfigurationChangeRequest.objects.create(
            request_type=ConfigurationChangeRequest.RequestType.PACK_ROLLBACK,
            target_type="workflow_pack",
            target_key="old-pack",
            status=ConfigurationChangeRequest.Status.APPROVED,
        )

        snapshot = governance_queue_snapshot()

        self.assertEqual(snapshot["pending_approvals"], 1)
        self.assertEqual(snapshot["failed_changes"], 1)
        self.assertEqual(snapshot["external_blocked_changes"], 1)
        self.assertEqual(snapshot["rollback_needed_changes"], 1)
