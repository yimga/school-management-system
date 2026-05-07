from django.test import SimpleTestCase

from apps.platform_runtime.migration_center import preview_migration, sample_template


class MigrationCenterPreviewTests(SimpleTestCase):
    def test_preview_reports_required_columns_duplicates_quarantine_and_quality(self):
        preview = preview_migration(
            entity="students",
            tenant_id="school-a",
            rows=[
                {"admission_number": "A1", "first_name": "Ada", "last_name": "N"},
                {"admission_number": "A1", "first_name": "", "last_name": "B"},
            ],
        )

        template = sample_template("students")
        self.assertEqual(template["required"], ["admission_number", "first_name", "last_name"])
        self.assertEqual(preview["entity_count"], 2)
        self.assertEqual(len(preview["duplicate_candidates"]), 1)
        self.assertEqual(len(preview["invalid_rows"]), 1)
        self.assertEqual(preview["quarantine"][0]["fix_action"], "correct_and_retry")
        self.assertLess(preview["data_quality_score"]["score"], 90)
