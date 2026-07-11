"""Wave: Migration Cloud lander correctness — model contracts + status mappers.

DB-free (SimpleTestCase). These lock in the fixes for the landers that were
writing to non-existent fields / never setting required FKs (health, events,
compliance, payroll → full quarantine) and silently dropping data (student /
enrollment enrollment_status, attendance status corruption). If a target model's
shape drifts back to what the landers used to assume, these fail loudly instead
of the domain silently migrating nothing.
"""

from __future__ import annotations

import inspect

from django.test import SimpleTestCase

from apps.migration_cloud.landers._helpers import (
    map_attendance_status,
    map_enrollment_status,
)


class EnrollmentStatusMapTests(SimpleTestCase):
    def test_known_tokens_map_to_valid_choices(self):
        from apps.people.models import StudentProfile

        valid = {c for c, _ in StudentProfile.Status.choices}
        for token in ("active", "enrolled", "new", "graduated", "withdrawn", "probation"):
            mapped = map_enrollment_status(token)
            self.assertIn(mapped, valid, f"{token!r} → {mapped!r} not a Status choice")

    def test_specific_mappings(self):
        self.assertEqual(map_enrollment_status("graduated"), "ALUMNI")
        self.assertEqual(map_enrollment_status("withdrawn"), "TRANSFERRED")
        self.assertEqual(map_enrollment_status("active"), "RETURNING")
        self.assertEqual(map_enrollment_status("new"), "NEW")

    def test_unknown_and_empty_return_blank(self):
        self.assertEqual(map_enrollment_status("wibble"), "")
        self.assertEqual(map_enrollment_status(""), "")
        self.assertEqual(map_enrollment_status(None), "")


class AttendanceStatusMapTests(SimpleTestCase):
    def test_canonical_values_pass_through_and_are_valid(self):
        from apps.academics.models import Attendance

        valid = {c for c, _ in Attendance.Status.choices}
        # The canonical present/absent/late/excused ARE the choices — never P/A/L/E.
        for token in ("present", "absent", "late", "excused"):
            mapped = map_attendance_status(token, valid=valid, default="present")
            self.assertEqual(mapped, token)
            self.assertIn(mapped, valid)

    def test_aliases_and_unknown_fold_into_valid_choices(self):
        valid = {"present", "absent", "late", "excused"}
        self.assertEqual(map_attendance_status("tardy", valid=valid, default="present"), "late")
        self.assertEqual(map_attendance_status("holiday", valid=valid, default="present"), "excused")
        self.assertEqual(map_attendance_status("suspended", valid=valid, default="present"), "absent")
        # Unknown → the model default, never an invalid single-letter code.
        self.assertEqual(map_attendance_status("???", valid=valid, default="present"), "present")


class LanderModelContractTests(SimpleTestCase):
    """Assert each target model still has the shape the fixed landers rely on."""

    def test_healthrecord_contract(self):
        from apps.schoolops.models import HealthRecord

        school = HealthRecord._meta.get_field("school")
        self.assertFalse(school.null, "HealthRecord.school must be required (lander sets it)")
        self.assertEqual(HealthRecord._meta.get_field("record_type").max_length, 32)
        self.assertTrue(HealthRecord._meta.get_field("recorded_at").auto_now_add)
        self.assertIn("notes", {f.name for f in HealthRecord._meta.get_fields()})

    def test_schoolevent_contract(self):
        from apps.school_events.models import SchoolEvent

        fields = {f.name for f in SchoolEvent._meta.get_fields()}
        self.assertFalse(SchoolEvent._meta.get_field("school").null)
        self.assertIn("start_at", fields)  # NOT starts_at / start_date
        self.assertFalse(SchoolEvent._meta.get_field("start_at").null)
        self.assertIn("metadata", fields)
        self.assertIn("slug", fields)
        # venue is a relation (FK) — assigning it a location string crashes.
        self.assertTrue(SchoolEvent._meta.get_field("venue").is_relation)

    def test_attendance_contract(self):
        from apps.academics.models import Attendance

        self.assertEqual(
            {c for c, _ in Attendance.Status.choices},
            {"present", "absent", "late", "excused"},
        )
        fields = {f.name for f in Attendance._meta.get_fields()}
        self.assertIn("remarks", fields)  # model column is remarks; canonical key is notes
        self.assertIn("school", fields)  # lander binds it when present (nullable here)
        self.assertIn("date", fields)

    def test_studentprofile_status_contract(self):
        from apps.people.models import StudentProfile

        fields = {f.name for f in StudentProfile._meta.get_fields()}
        self.assertIn("status", fields)
        self.assertNotIn("enrollment_status", fields)  # the phantom the landers wrote
        choices = {c for c, _ in StudentProfile.Status.choices}
        self.assertTrue({"NEW", "ALUMNI", "TRANSFERRED"} <= choices)

    def test_compliance_and_payroll_targets_are_mismatched_so_landers_use_dfv(self):
        """Documents WHY compliance/payroll preserve via DFV instead of first-class rows."""
        from apps.compliance.models import ComplianceCheck
        from apps.payroll.models import Payslip

        # ComplianceCheck is region/requirement-scoped with no school column.
        self.assertFalse(ComplianceCheck._meta.get_field("region").null)
        self.assertFalse(ComplianceCheck._meta.get_field("requirement").null)
        self.assertNotIn("school", {f.name for f in ComplianceCheck._meta.get_fields()})
        # Payslip needs a payroll_run + a PayrollEmployee (not TeacherProfile).
        self.assertFalse(Payslip._meta.get_field("payroll_run").null)
        self.assertEqual(
            Payslip._meta.get_field("employee").related_model.__name__, "PayrollEmployee"
        )
        # And the landers must no longer TARGET those first-class models — they
        # preserve rows via DFV instead (no import of the mismatched model).
        from apps.migration_cloud.landers import compliance_lander, payroll_lander

        src_c = inspect.getsource(compliance_lander)
        src_p = inspect.getsource(payroll_lander)
        self.assertNotIn("apps.compliance.models", src_c)
        self.assertNotIn("apps.payroll.models", src_p)
        self.assertIn("persist_dfv_extras", src_c)
        self.assertIn("persist_dfv_extras", src_p)


class OrchestratorWaveOrderingTests(SimpleTestCase):
    def test_athletics_teams_precedes_its_roster_and_fixtures(self):
        from apps.migration_cloud.orchestrator import _DEPENDENCY_WAVES

        def wave_index(domain):
            for i, w in enumerate(_DEPENDENCY_WAVES):
                if domain in w:
                    return i
            return len(_DEPENDENCY_WAVES) - 1  # catch-all (unlisted) runs last

        teams = wave_index("athletics_teams")
        memberships = wave_index("athletics_memberships")
        fixtures = wave_index("athletics_fixtures")
        self.assertLess(teams, memberships, "teams must land before roster")
        self.assertLess(teams, fixtures, "teams must land before fixtures")

    def test_students_and_academics_precede_their_dependents(self):
        from apps.migration_cloud.orchestrator import _DEPENDENCY_WAVES

        def wave_index(domain):
            for i, w in enumerate(_DEPENDENCY_WAVES):
                if domain in w:
                    return i
            return len(_DEPENDENCY_WAVES) - 1

        self.assertLess(wave_index("students"), wave_index("enrollment"))
        self.assertLess(wave_index("academics"), wave_index("grades"))


class BundleActionTenantScopingTests(SimpleTestCase):
    """The bundle action POSTs must tenant-scope the bundle before running the
    pipeline (cross-tenant IDOR guard). Source-level so it's DB-free."""

    def test_action_posts_call_tenant_scoped_bundle(self):
        from apps.migration_cloud import views

        for cls_name in (
            "MigrationCloudAdvanceView",
            "MigrationCloudApplyView",
            "MigrationCloudReconcileView",
            "MigrationCloudConflictsView",
        ):
            view_cls = getattr(views, cls_name)
            src = inspect.getsource(view_cls.post)
            self.assertIn(
                "_tenant_scoped_bundle",
                src,
                f"{cls_name}.post must resolve the bundle via _tenant_scoped_bundle",
            )
