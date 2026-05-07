from django.test import SimpleTestCase

from apps.platform_runtime.migration_center import build_quarantine


class MigrationQuarantineTests(SimpleTestCase):
    def test_quarantine_rows_require_fix_or_ignored_reason_with_audit(self):
        quarantine = build_quarantine([{"row": 3, "reason": "Missing guardian_email"}])

        self.assertEqual(quarantine[0]["row"], "3")
        self.assertEqual(quarantine[0]["fix_action"], "correct_and_retry")
        self.assertEqual(quarantine[0]["ignore_requires_reason"], "true")
        self.assertEqual(quarantine[0]["audit_required"], "true")
