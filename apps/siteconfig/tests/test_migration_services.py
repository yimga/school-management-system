from django.test import TestCase

from apps.automation.models import MigrationProfile
from apps.registries.models import (
    EducationLevelRegistry,
    FeeCategoryRegistry,
    GradeScaleRegistry,
)
from apps.siteconfig.migration_services import (
    dry_run_import,
    map_education_level,
    validate_migration_mapping,
)


class MigrationServicesTests(TestCase):
    def setUp(self):
        # These registries are also seeded by data migrations (e.g. GradeScaleRegistry
        # code="0-100"), so update_or_create to avoid a UNIQUE collision while still
        # guaranteeing the exact alias metadata these tests rely on.
        EducationLevelRegistry.objects.update_or_create(
            code="SECONDARY",
            defaults={
                "global_name": "Secondary",
                "metadata": {"aliases": ["sec"]},
                "is_active": True,
            },
        )
        GradeScaleRegistry.objects.update_or_create(
            code="0-100",
            defaults={
                "name": "0-100",
                "family": "numeric",
                "metadata": {"aliases": ["percentage"]},
                "is_active": True,
            },
        )
        FeeCategoryRegistry.objects.update_or_create(
            code="TUITION",
            defaults={
                "name": "Tuition",
                "category": "core",
                "metadata": {"aliases": ["school_fees"]},
                "is_active": True,
            },
        )
        self.profile = MigrationProfile.objects.create(
            slug="students-profile",
            name="Students profile",
            format=MigrationProfile.Format.CSV,
            domain=MigrationProfile.Domain.STUDENTS,
            config={
                "target_fields": ["first_name", "last_name", "education_level"],
                "required": ["first_name", "last_name"],
                "education_levels": ["sec"],
                "grade_scales": ["percentage"],
                "fee_categories": ["school_fees"],
            },
            is_active=True,
        )

    def test_map_education_level_resolves_alias(self):
        self.assertEqual(map_education_level("sec", "CM"), "SECONDARY")

    def test_validate_migration_mapping_reports_unknown_registry_values(self):
        warnings = validate_migration_mapping({"education_level": "unknown-level"})
        self.assertTrue(warnings)
        self.assertIn("Unknown education level", warnings[0])

    def test_dry_run_import_reports_required_field_errors_and_registry_warnings(self):
        result = dry_run_import(
            self.profile,
            {
                "rows": [
                    {
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "education_level": "sec",
                    },
                    {"first_name": "Grace"},
                ]
            },
        )

        self.assertEqual(result["rows_affected"], 2)
        self.assertEqual(result["matched_rows"], 1)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["status"], "partial")
