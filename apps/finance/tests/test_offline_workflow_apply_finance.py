"""Finance offline workflow apply (batch 1511)."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.finance.models import ReportRequest
from apps.finance.models_offline_capture import FinanceOfflineCaptureRecord
from apps.finance.offline_workflow_handlers import apply_finance_workflow
from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import enqueue_offline_action, process_offline_queue
from apps.schools.models import School, SchoolMembership


class FinanceOfflineWorkflowApplyTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"FinWF {uid}",
            slug=f"finwf-{uid}",
            subdomain=f"finwf{uid}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"finwf_a_{uid}",
            password="pw",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.get_or_create(
            user=self.admin,
            school=self.school,
            defaults={"role": self.admin.role, "is_primary": True},
        )

    def test_report_request_workflow_apply(self):
        body = json.dumps(
            {
                "workflow": "finance_report_request",
                "fields": {
                    "report_type": "COLLECTION",
                    "description": "Offline collection summary",
                },
            }
        )
        action = enqueue_offline_action(
            user_id=self.admin.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": body, "client_offline_id": f"fr-{uuid.uuid4().hex[:8]}"},
            idempotency_key=f"fr-{uuid.uuid4().hex[:8]}",
        )
        summary = process_offline_queue(school_id=self.school.pk, user_id=self.admin.pk)
        self.assertGreaterEqual(summary.get("synced", 0), 1)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.SYNCED)
        self.assertTrue(ReportRequest.objects.filter(requested_by=self.admin).exists())
        self.assertTrue(
            FinanceOfflineCaptureRecord.objects.filter(
                school_id=self.school.pk,
                workflow="finance_report_request",
            ).exists()
        )

    def test_apply_finance_workflow_direct_report(self):
        result = apply_finance_workflow(
            self.school.pk,
            self.admin.pk,
            "finance_report_request",
            {"report_type": "CUSTOM", "description": "x"},
            {"client_offline_id": f"direct-{uuid.uuid4().hex[:8]}"},
        )
        self.assertTrue(result and result.get("ok"))
        self.assertEqual(result.get("workflow_applied"), "finance_report_request")
