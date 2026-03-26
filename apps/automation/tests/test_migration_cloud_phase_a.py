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
        self.assertEqual(
            MigrationProfile.SourceSystem.INFINITE_CAMPUS, "infinite_campus"
        )
        self.assertEqual(MigrationProfile.SourceSystem.FACTS, "facts")
        self.assertEqual(MigrationProfile.SourceSystem.SKYWARD, "skyward")
        self.assertEqual(MigrationProfile.SourceSystem.ALMA, "alma")
        self.assertEqual(MigrationProfile.SourceSystem.SQL_DUMP, "sql_dump")
        self.assertEqual(MigrationProfile.SourceSystem.API_SIS, "api_sis")
        self.assertEqual(MigrationProfile.SourceSystem.OTHER, "other")

    def test_profile_category_field_exists(self):
        self.assertTrue(hasattr(MigrationProfile, "profile_category"))
        self.assertTrue(hasattr(MigrationProfile, "ProfileCategory"))

    def test_competitor_profiles_have_schema_hints_after_seed(self):
        from django.core.management import call_command

        call_command("seed_migration_profiles")
        ps_students = MigrationProfile.objects.filter(
            slug="students_from_powerschool"
        ).first()
        self.assertIsNotNone(ps_students)
        self.assertEqual(
            ps_students.source_system, MigrationProfile.SourceSystem.POWERSCHOOL
        )
        hints = (ps_students.config or {}).get("schema_hints") or {}
        self.assertIn("student_number", hints)
        self.assertEqual(hints.get("student_number"), "admission_number")
        veracross = MigrationProfile.objects.filter(
            slug="students_from_veracross"
        ).first()
        self.assertIsNotNone(veracross)
        self.assertEqual(
            veracross.source_system, MigrationProfile.SourceSystem.VERACROSS
        )

    def test_generic_profiles_have_null_source_system(self):
        from django.core.management import call_command

        call_command("seed_migration_profiles")
        generic = MigrationProfile.objects.filter(slug="students").first()
        self.assertIsNotNone(generic)
        self.assertIsNone(generic.source_system)

    def test_facts_profile_after_seed(self):
        from django.core.management import call_command

        call_command("seed_migration_profiles")
        facts = MigrationProfile.objects.filter(slug="students_from_facts").first()
        self.assertIsNotNone(facts)
        self.assertEqual(facts.source_system, MigrationProfile.SourceSystem.FACTS)
        self.assertEqual(
            facts.profile_category, MigrationProfile.ProfileCategory.VENDOR
        )

    def test_phased_migration_strategy_profile_after_seed(self):
        from django.core.management import call_command

        call_command("seed_migration_profiles")
        phased = MigrationProfile.objects.filter(slug="phased_migration").first()
        self.assertIsNotNone(phased)
        self.assertEqual(
            phased.profile_category, MigrationProfile.ProfileCategory.STRATEGY
        )


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


class MigrationPlaybookTests(TestCase):
    """MigrationPlaybook: ordered profile_slugs, get_profiles()."""

    def test_playbook_get_profiles_returns_ordered(self):
        from django.core.management import call_command
        from apps.automation.models import MigrationPlaybook

        call_command("seed_migration_profiles")
        playbook = MigrationPlaybook.objects.create(
            slug="test_students_then_grades",
            name="Students then Grades",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        profiles = playbook.get_profiles()
        self.assertEqual(len(profiles), 2)
        self.assertEqual(profiles[0].slug, "students_from_powerschool")
        self.assertEqual(profiles[1].slug, "grades_from_powerschool")

    def test_playbook_get_profiles_empty_when_no_slugs(self):
        from apps.automation.models import MigrationPlaybook

        playbook = MigrationPlaybook(slug="empty", name="Empty", profile_slugs=[])
        self.assertEqual(playbook.get_profiles(), [])


class SchemaFingerprintTests(TestCase):
    """Schema fingerprint: suggest_profiles_from_headers returns best-matching profiles."""

    def test_suggest_profiles_powerschool_headers(self):
        from django.core.management import call_command
        from apps.automation.schema_fingerprint import suggest_profiles_from_headers

        call_command("seed_migration_profiles")
        headers = [
            "student_number",
            "first_name",
            "last_name",
            "grade_level",
            "homeroom",
        ]
        scored = suggest_profiles_from_headers(headers)
        self.assertGreater(len(scored), 0)
        top_profile, confidence = scored[0]
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)
        # PowerSchool hints include student_number, first_name, last_name, grade_level, homeroom
        ps = next((p for p, _ in scored if p.slug == "students_from_powerschool"), None)
        self.assertIsNotNone(
            ps,
            "students_from_powerschool should be suggested for PowerSchool-like headers",
        )

    def test_suggest_profiles_empty_headers_returns_empty(self):
        from apps.automation.schema_fingerprint import suggest_profiles_from_headers

        self.assertEqual(suggest_profiles_from_headers([]), [])


class QuarantineTests(TestCase):
    """Repair and quarantine: add_to_quarantine, mark_repaired, get_repaired_rows."""

    def test_add_to_quarantine_and_mark_repaired(self):
        from apps.automation.quarantine_services import (
            add_to_quarantine,
            mark_repaired,
            get_repaired_rows,
        )
        from apps.automation.models import MigrationQuarantineRecord

        rec = add_to_quarantine(
            domain="students",
            row_index=5,
            payload={"first_name": "A", "last_name": "B"},
            issue_class="missing_required",
        )
        self.assertEqual(rec.status, MigrationQuarantineRecord.Status.PENDING)
        mark_repaired(
            rec, {"first_name": "A", "last_name": "B", "admission_number": "123"}
        )
        rec.refresh_from_db()
        self.assertEqual(rec.status, MigrationQuarantineRecord.Status.REPAIRED)
        self.assertIn("admission_number", rec.resolution_payload)
        rows = get_repaired_rows(domain="students")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["admission_number"], "123")

    def test_get_repaired_rows_empty_when_none_repaired(self):
        from apps.automation.quarantine_services import get_repaired_rows

        self.assertEqual(get_repaired_rows(domain="grades"), [])


class PlaybookExecutorTests(TestCase):
    """execute_playbook: runs steps in sequence, returns runs and status."""

    def test_execute_playbook_dry_run_empty_payload_creates_runs(self):
        from django.core.management import call_command
        from apps.automation.models import MigrationPlaybook
        from apps.automation.playbook_executor import execute_playbook

        call_command("seed_migration_profiles")
        playbook = MigrationPlaybook.objects.create(
            slug="exec_test",
            name="Exec test",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        result = execute_playbook(
            playbook, school=None, user=None, dry_run=True, steps_payload=None
        )
        self.assertIn("runs", result)
        self.assertIn("status", result)
        self.assertEqual(len(result["runs"]), 2)
        self.assertEqual(result["status"], "SUCCESS")
        for run in result["runs"]:
            self.assertTrue(run.execution_summary.get("playbook_slug") == "exec_test")
            self.assertIn("step_index", run.execution_summary)
            self.assertIn("profile_slug", run.execution_summary)
        from apps.automation.models import AutomationExecutionLog

        logs = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        )
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().status, AutomationExecutionLog.Status.SUCCESS)
