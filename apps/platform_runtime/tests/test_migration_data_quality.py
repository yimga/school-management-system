from django.test import SimpleTestCase

from apps.platform_runtime.migration_center import calculate_data_quality


class MigrationDataQualityTests(SimpleTestCase):
    def test_quality_score_reflects_completeness_duplicates_and_invalids(self):
        score = calculate_data_quality(
            rows=[
                {"first_name": "Ada", "last_name": "N"},
                {"first_name": "", "last_name": "B"},
            ],
            invalid_count=1,
            duplicate_count=1,
            required=["first_name", "last_name"],
        )

        self.assertEqual(score["readiness"], "needs_review")
        self.assertLess(score["score"], 90)
        self.assertEqual(score["duplicates"], 1)
        self.assertEqual(score["invalid_values"], 1)
