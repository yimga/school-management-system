from django.test import SimpleTestCase

from apps.payroll.models import PayrollRun
from apps.payroll.views import disbursement_export_allowed


class DisbursementApprovalGateTests(SimpleTestCase):
    def test_preapproval_states_cannot_export_money_out_file(self):
        for status in (
            PayrollRun.Status.DRAFT,
            PayrollRun.Status.PROCESSED,
            PayrollRun.Status.REVIEWED,
        ):
            with self.subTest(status=status):
                self.assertFalse(disbursement_export_allowed(status))

    def test_final_approval_states_can_export(self):
        self.assertTrue(disbursement_export_allowed(PayrollRun.Status.APPROVED))
        self.assertTrue(disbursement_export_allowed(PayrollRun.Status.PAID))
