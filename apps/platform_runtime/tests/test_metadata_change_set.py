from django.test import SimpleTestCase

from apps.platform_runtime.metadata_governance import build_metadata_change_set


class MetadataChangeSetTests(SimpleTestCase):
    def test_change_set_records_versions_rollback_and_affected_fields(self):
        change_set = build_metadata_change_set(
            [
                {
                    "entity": "Invoice",
                    "field": "settlement_reference",
                    "owner": "Billing operations",
                    "action": "add",
                }
            ],
            current_version="2.0",
            proposed_version="2.1",
        )

        self.assertTrue(change_set["ok"])
        self.assertEqual(change_set["current_version"], "2.0")
        self.assertEqual(change_set["proposed_version"], "2.1")
        self.assertIn("Invoice.settlement_reference", change_set["affected_fields"])
        self.assertTrue(change_set["rollback_coverage"]["snapshot_required"])
        self.assertTrue(change_set["requires_approval"])
