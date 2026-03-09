"""
Phase A tests: competitor-first UX, source_system, prebuilt adapters, Veracross marketing.
"""
from django.test import TestCase

from apps.automation.models import MigrationProfile


class MigrationProfileSourceSystemTests(TestCase):
    """MigrationProfile has source_system and competitor profiles exist after seed."""

    def test_source_system_field_exists(self):
        self.assertTrue(hasattr(MigrationProfile, "source_system"))
        self.assertTrue(hasattr(MigrationProfile, "SourceSystem"))

    def test_source_system_choices(self):
        self.assertEqual(MigrationProfile.SourceSystem.POWERSCHOOL, "powerschool")
        self.assertEqual(MigrationProfile.SourceSystem.BLACKBAUD, "blackbaud")
        self.assertEqual(MigrationProfile.SourceSystem.VERACROSS, "veracross")
        self.assertEqual(MigrationProfile.SourceSystem.INFINITE_CAMPUS, "infinite_campus")
        self.assertEqual(MigrationProfile.SourceSystem.OTHER, "other")

    def test_competitor_profiles_have_schema_hints_after_seed(self):
        from django.core.management import call_command
        call_command("seed_migration_profiles")
        ps_students = MigrationProfile.objects.filter(slug="students_from_powerschool").first()
        self.assertIsNotNone(ps_students)
        self.assertEqual(ps_students.source_system, MigrationProfile.SourceSystem.POWERSCHOOL)
        hints = (ps_students.config or {}).get("schema_hints") or {}
        self.assertIn("student_number", hints)
        self.assertEqual(hints.get("student_number"), "admission_number")
        veracross = MigrationProfile.objects.filter(slug="students_from_veracross").first()
        self.assertIsNotNone(veracross)
        self.assertEqual(veracross.source_system, MigrationProfile.SourceSystem.VERACROSS)

    def test_generic_profiles_have_null_source_system(self):
        from django.core.management import call_command
        call_command("seed_migration_profiles")
        generic = MigrationProfile.objects.filter(slug="students").first()
        self.assertIsNotNone(generic)
        self.assertIsNone(generic.source_system)


class SchemaInferenceTests(TestCase):
    """Phase B: infer_schema_mapping suggests mappings from column names."""

    def test_infer_exact_match(self):
        from apps.accounts.migration_services import infer_schema_mapping
        headers = ["first_name", "last_name", "admission_number"]
        target_fields = ["first_name", "last_name", "admission_number", "classroom"]
        out = infer_schema_mapping(headers, target_fields)
        self.assertEqual(out.get("first_name"), "first_name")
        self.assertEqual(out.get("last_name"), "last_name")
        self.assertEqual(out.get("admission_number"), "admission_number")

    def test_infer_normalized_match(self):
        from apps.accounts.migration_services import infer_schema_mapping
        headers = ["FirstName", "LastName", "Student_ID"]
        target_fields = ["first_name", "last_name", "admission_number"]
        out = infer_schema_mapping(headers, target_fields)
        self.assertEqual(out.get("FirstName"), "first_name")
        self.assertEqual(out.get("LastName"), "last_name")
        self.assertEqual(out.get("Student_ID"), "admission_number")

    def test_infer_alias_student_id_to_admission_number(self):
        from apps.accounts.migration_services import infer_schema_mapping
        headers = ["student_id", "student_number"]
        target_fields = ["first_name", "last_name", "admission_number"]
        out = infer_schema_mapping(headers, target_fields)
        self.assertEqual(out.get("student_id"), "admission_number")
        self.assertEqual(out.get("student_number"), "admission_number")


class PreMigrationValidationTests(TestCase):
    """Phase C: run_pre_migration_validation returns categorized issues."""

    def test_students_duplicates_and_missing_required(self):
        from apps.accounts.migration_services import run_pre_migration_validation

        rows = [
            {"first_name": "A", "last_name": "B", "admission_number": "X"},
            {"first_name": "C", "last_name": "D", "admission_number": "X"},
            {"first_name": "", "last_name": "E"},
        ]
        issues = run_pre_migration_validation("students", rows, school=None)
        self.assertIn("duplicates", issues)
        dup = [d for d in issues["duplicates"] if d.get("value") == "X"]
        self.assertEqual(len(dup), 1)
        self.assertEqual(set(dup[0]["row_indices"]), {1, 2})
        self.assertIn("missing_required", issues)
        missing = [m for m in issues["missing_required"] if m.get("row") == 3]
        self.assertEqual(len(missing), 1)
        self.assertIn("first_name", missing[0]["fields"])

    def test_students_no_issues_when_valid(self):
        from apps.accounts.migration_services import run_pre_migration_validation

        rows = [
            {"first_name": "A", "last_name": "B", "admission_number": "1"},
            {"first_name": "C", "last_name": "D", "admission_number": "2"},
        ]
        issues = run_pre_migration_validation("students", rows, school=None)
        self.assertEqual(len(issues["duplicates"]), 0)
        self.assertEqual(len(issues["missing_required"]), 0)

    def test_grades_duplicates_without_school(self):
        from apps.accounts.migration_services import run_pre_migration_validation

        rows = [
            {"student_code": "S1", "subject_assignment_id": 10, "term_id": 1},
            {"student_code": "S1", "subject_assignment_id": 10, "term_id": 1},
        ]
        issues = run_pre_migration_validation("grades", rows, school=None)
        self.assertGreaterEqual(len(issues["duplicates"]), 1)
        self.assertEqual(issues["duplicates"][0]["row_indices"], [1, 2])
