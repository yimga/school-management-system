from django.test import SimpleTestCase

from apps.platform_runtime.migration_center import build_field_mapping


class MigrationFieldMappingTests(SimpleTestCase):
    def test_field_mapping_marks_required_optional_and_unmapped_fields(self):
        mapping = build_field_mapping(
            ["admission_number", "first_name", "legacy_house"],
            entity="students",
            transforms={"first_name": "strip_titlecase"},
        )

        self.assertEqual(mapping[0]["validation_status"], "mapped")
        self.assertEqual(mapping[0]["required"], "true")
        self.assertEqual(mapping[1]["transformation"], "strip_titlecase")
        self.assertEqual(mapping[2]["validation_status"], "unmapped")
