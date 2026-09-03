"""Auto-repair expansion — enrich, catalog reroute, CM TVET catalog repair."""

from __future__ import annotations

import uuid

from django.test import SimpleTestCase, TestCase

from apps.academics.models import Department, Specialty, Subject
from apps.migration_cloud.auto_remediate import _row_is_misrouted_subject_catalog
from apps.migration_cloud.catalog_repair import (
    plan_inverted_catalog_repair,
    school_wants_catalog_autorepair,
)
from apps.migration_cloud.ingestion_lexicon import row_looks_like_subject_catalog_entry
from apps.migration_cloud.landers._helpers import enrich_missing_required_row
from apps.migration_cloud.landers.academics_lander import AcademicsLander
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.specialty_lander import SpecialtyLander
from apps.migration_cloud.landers.student_lander import StudentLander
from apps.schools.models import School


def _school(tag: str, **kwargs) -> School:
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    defaults = {
        "name": f"School {slug}",
        "slug": slug,
        "subdomain": slug,
        "country_code": "CM",
    }
    defaults.update(kwargs)
    return School.objects.create(**defaults)


class EnrichMissingRequiredExpansionTests(SimpleTestCase):
    def test_grades_backfills_subject_and_student_refs(self):
        row = {
            "student_code": "STU-9",
            "subject": "Mathematics",
            "term": "Trimestre 1",
        }
        enriched, evidence = enrich_missing_required_row("grades", row)
        self.assertEqual(enriched["student_external_id"], "STU-9")
        self.assertEqual(enriched["subject_code"], "Mathematics")
        self.assertIn("student_external_id←identity_alias", evidence)
        self.assertIn("subject_code←subject_label", evidence)

    def test_staff_derives_external_id_from_name(self):
        school = School(country_code="CM")
        row = {"first_name": "Jane", "last_name": "Doe"}
        enriched, evidence = enrich_missing_required_row(
            "staff", row, school=school, transformer_options={"name_order": "first_last"}
        )
        self.assertTrue(enriched.get("staff_external_id", "").startswith("auto-staff-"))
        self.assertIn("staff_external_id←identity_hash", evidence)

    def test_students_split_combined_name(self):
        school = School(country_code="CM")
        row = {"full_name": "Jean Paul Mbarga"}
        enriched, evidence = enrich_missing_required_row(
            "students", row, school=school
        )
        self.assertTrue(enriched.get("first_name"))
        self.assertTrue(enriched.get("last_name"))
        self.assertIn("first_name←full_name", evidence)

    def test_structure_backfills_classroom_and_subject_aliases(self):
        row = {
            "classroom_name": "Form 4A",
            "course_name": "Mathematics",
            "stream": "PLUMBING",
            "school_year": "2025/2026",
            "semester": "FIRST",
        }
        enriched, evidence = enrich_missing_required_row("structure", row)
        self.assertEqual(enriched["classroom"], "Form 4A")
        self.assertEqual(enriched["subject"], "Mathematics")
        self.assertEqual(enriched["specialty"], "PLUMBING")
        self.assertEqual(enriched["academic_year"], "2025/2026")
        self.assertEqual(enriched["term"], "FIRST")
        self.assertIn("classroom←class_alias", evidence)

    def test_sections_backfills_name_from_classroom_alias(self):
        row = {"classroom_name": "Form 2B", "code": "F2B"}
        enriched, evidence = enrich_missing_required_row("sections", row)
        self.assertEqual(enriched["name"], "Form 2B")
        self.assertEqual(enriched["section_code"], "F2B")
        self.assertIn("name←section_alias", evidence)

    def test_specialties_code_from_name(self):
        row = {"name": "ELECTRICAL POWER SYSTEMS"}
        enriched, evidence = enrich_missing_required_row("specialties", row)
        self.assertTrue(enriched.get("code"))
        self.assertIn("code←name", evidence)

    def test_schedule_backfills_section_and_times(self):
        row = {
            "section_code": "F2A",
            "day": "Monday",
            "begin_time": "08:30",
            "finish_time": "09:30",
        }
        enriched, evidence = enrich_missing_required_row("schedule", row)
        self.assertEqual(enriched["section_external_id"], "F2A")
        self.assertEqual(enriched["day_of_week"], "Monday")
        self.assertEqual(enriched["start_time"], "08:30")
        self.assertEqual(enriched["end_time"], "09:30")
        self.assertIn("section_external_id←section_alias", evidence)

    def test_enrollment_backfills_section_and_specialty(self):
        row = {
            "pupil_id": "P-77",
            "class_name": "Form 3A",
            "stream": "ELECTRICAL",
        }
        enriched, evidence = enrich_missing_required_row("enrollment", row)
        self.assertEqual(enriched["student_external_id"], "P-77")
        self.assertEqual(enriched["section_code"], "Form 3A")
        self.assertEqual(enriched["specialty"], "ELECTRICAL")
        self.assertIn("student_external_id←identity_alias", evidence)

    def test_transport_assignment_backfills_route_and_pupil_id(self):
        row = {"pupil_id": "STU-12", "bus_route": "Route B"}
        enriched, evidence = enrich_missing_required_row("transport_assignments", row)
        self.assertEqual(enriched["student_external_id"], "STU-12")
        self.assertEqual(enriched["route"], "Route B")
        self.assertIn("route←route_alias", evidence)

    def test_hostel_assignment_backfills_room_alias(self):
        row = {"admission_number": "ADM-1", "hostel_room": "Block A / 12"}
        enriched, evidence = enrich_missing_required_row("hostel_assignments", row)
        self.assertEqual(enriched["student_external_id"], "ADM-1")
        self.assertEqual(enriched["room"], "Block A / 12")
        self.assertIn("room←room_alias", evidence)

    def test_health_backfills_student_date_and_category(self):
        row = {
            "pupil_id": "H-1",
            "date": "2025-09-01",
            "record_type": "immunization",
        }
        enriched, evidence = enrich_missing_required_row("health", row)
        self.assertEqual(enriched["student_external_id"], "H-1")
        self.assertEqual(enriched["record_date"], "2025-09-01")
        self.assertEqual(enriched["category"], "immunization")

    def test_library_backfills_title_and_isbn(self):
        row = {"name": "Physics Vol 1", "barcode": "9780123456789"}
        enriched, evidence = enrich_missing_required_row("library", row)
        self.assertEqual(enriched["title"], "Physics Vol 1")
        self.assertEqual(enriched["isbn"], "9780123456789")

    def test_transport_backfills_route_name(self):
        row = {"bus_route": "Route 7"}
        enriched, evidence = enrich_missing_required_row("transport", row)
        self.assertEqual(enriched["route"], "Route 7")

    def test_payroll_backfills_staff_and_period(self):
        row = {"employee_id": "T-9", "period": "2025-09", "gross": "1000"}
        enriched, evidence = enrich_missing_required_row("payroll", row)
        self.assertEqual(enriched["staff_external_id"], "T-9")
        self.assertEqual(enriched["pay_period"], "2025-09")
        self.assertEqual(enriched["gross_amount"], "1000")

    def test_events_backfills_title_and_start(self):
        row = {"event_name": "Sports Day", "start_date": "2026-04-10"}
        enriched, evidence = enrich_missing_required_row("events", row)
        self.assertEqual(enriched["title"], "Sports Day")
        self.assertEqual(enriched["starts_at"], "2026-04-10")

    def test_athletics_teams_backfills_squad_fields(self):
        row = {"sport_name": "Football", "season_name": "2025 Fall", "squad_name": "1st XI"}
        enriched, evidence = enrich_missing_required_row("athletics_teams", row)
        self.assertEqual(enriched["sport"], "Football")
        self.assertEqual(enriched["team_name"], "1st XI")

    def test_transcripts_backfills_year_and_grade(self):
        row = {"pupil_id": "S-1", "school_year": "2025-2026", "grade": "A"}
        enriched, evidence = enrich_missing_required_row("transcripts", row)
        self.assertEqual(enriched["academic_year"], "2025-2026")
        self.assertEqual(enriched["final_grade"], "A")

    def test_communications_backfills_recipient_and_body(self):
        row = {"to_id": "PS-9", "message": "Permission slip due Friday."}
        enriched, evidence = enrich_missing_required_row("communications", row)
        self.assertEqual(enriched["recipient_external_id"], "PS-9")
        self.assertEqual(enriched["body"], "Permission slip due Friday.")

    def test_athletics_fixtures_backfills_match_fields(self):
        row = {"team": "1st XI", "opponent": "St Mary's", "match_date": "2026-04-10T15:00:00"}
        enriched, evidence = enrich_missing_required_row("athletics_fixtures", row)
        self.assertEqual(enriched["team_name"], "1st XI")
        self.assertEqual(enriched["opponent_name"], "St Mary's")
        self.assertEqual(enriched["scheduled_start"], "2026-04-10T15:00:00")

    def test_academic_sessions_backfills_oneroster_aliases(self):
        row = {
            "title": "Fall 2025",
            "type": "term",
            "startDate": "2025-09-01",
            "sourcedId": "term-1",
            "parentSourcedId": "year-1",
        }
        enriched, evidence = enrich_missing_required_row("academic_sessions", row)
        self.assertEqual(enriched["session_title"], "Fall 2025")
        self.assertEqual(enriched["session_type"], "term")
        self.assertEqual(enriched["session_start"], "2025-09-01")
        self.assertEqual(enriched["session_external_id"], "term-1")

    def test_compliance_backfills_category_and_subject(self):
        row = {"check_type": "immunization", "student_external_id": "PS-2", "due": "2026-04-30"}
        enriched, evidence = enrich_missing_required_row("compliance", row)
        self.assertEqual(enriched["category"], "immunization")
        self.assertEqual(enriched["subject_external_id"], "PS-2")
        self.assertEqual(enriched["due_date"], "2026-04-30")


class PreviewLanderErrorEnrichTests(SimpleTestCase):
    def test_lander_error_with_enrich_evidence_is_auto_replay(self):
        from apps.migration_cloud.auto_remediate import _preview_one

        decision, rule, _note = _preview_one(
            issue_class="lander_error",
            domain="students",
            source_row={"admission_number": "ADM-42", "full_name": "Jean Paul Mbarga"},
            artifact="students.csv",
            reason_source="declared",
            message="missing required fields",
        )
        self.assertEqual(decision, "auto_replay")
        self.assertEqual(rule, "enrich_replay")


class StudentNormalizeAtLandTests(TestCase):
    def test_admission_number_and_full_name_land_without_external_id(self):
        school = _school("student-norm")
        ctx = LanderContext(
            school=school,
            schema_name="public",
            bundle_id=3,
            artifact_id=3,
            transformer_options={"name_order": "last_first"},
        )
        row = {"admission_number": "ADM-99", "full_name": "ANDONGMAD FAVOUR"}
        result = StudentLander().land(canonical_rows=iter([row]), ctx=ctx)
        self.assertEqual(result.quarantined, 0, result.errors)
        self.assertEqual(result.created, 1)


class SpecialtyAutoRerouteTests(TestCase):
    def test_subject_shaped_row_lands_via_academics_not_quarantine(self):
        school = _school(
            "reroute",
            settings={"grading": {"curriculum_tracks": ["vocational_trade"]}},
        )
        ctx = LanderContext(
            school=school,
            schema_name="public",
            bundle_id=1,
            artifact_id=1,
            artifact_path="subjects_misfiled.xlsx",
        )
        row = {
            "name": "WORKSHOP PRACTICE",
            "category": "Professional",
            "coef": "6",
        }
        self.assertTrue(row_looks_like_subject_catalog_entry(row))

        specialty_result = SpecialtyLander().land(canonical_rows=iter([row]), ctx=ctx)
        self.assertEqual(specialty_result.quarantined, 0)
        self.assertGreaterEqual(specialty_result.created + specialty_result.skipped, 1)
        self.assertGreaterEqual(Subject.objects.filter(school=school).count(), 1)

    def test_misroute_detector(self):
        row = {"name": "PHYSICS", "category": "General", "coef": "3"}
        self.assertTrue(
            _row_is_misrouted_subject_catalog(domain="specialties", source_row=row)
        )


class CatalogRepairServiceTests(TestCase):
    def test_detects_phantom_specialty_matching_subject(self):
        school = _school("catalog-repair")
        Subject.objects.create(school=school, name="MATHEMATICS", code="MATH")
        dept = Department.objects.create(school=school, name="MATHEMATICS", code="D-MATH")
        Specialty.objects.create(
            school=school, name="MATHEMATICS", code="S-MATH", department=dept
        )
        plan = plan_inverted_catalog_repair(school)
        self.assertTrue(plan["actionable"])
        self.assertIn("MATHEMATICS", plan["phantom_specialties_removed"])

    def test_cm_tvet_school_flag(self):
        school = School(
            country_code="CM",
            settings={"grading": {"curriculum_tracks": ["vocational_trade"]}},
        )
        self.assertTrue(school_wants_catalog_autorepair(school))


class NormalizeCanonicalRowTests(SimpleTestCase):
    def test_normalize_canonical_row_matches_enrich(self):
        from apps.migration_cloud.landers._helpers import normalize_canonical_row

        school = School(country_code="CM")
        ctx = LanderContext(
            school=school,
            schema_name="public",
            bundle_id=1,
            artifact_id=1,
            transformer_options={"name_order": "first_last"},
        )
        row = {"student_code": "X-1", "subject": "Physics", "term": "T2"}
        normalized = normalize_canonical_row("grades", row, ctx)
        self.assertEqual(normalized["student_external_id"], "X-1")
        self.assertEqual(normalized["subject_code"], "Physics")


class AcademicsLanderStillAcceptsSubjectShapeTests(TestCase):
    def test_direct_academics_lands_coef_row(self):
        school = _school(
            "direct-academics",
            settings={"grading": {"curriculum_tracks": ["vocational_trade"]}},
        )
        ctx = LanderContext(
            school=school,
            schema_name="public",
            bundle_id=2,
            artifact_id=2,
        )
        row = {"title": "OHADA FINANCIAL ACCOUNTING", "category": "Professional", "coef": "4"}
        result = AcademicsLander().land(canonical_rows=iter([row]), ctx=ctx)
        self.assertEqual(result.quarantined, 0)
        self.assertGreaterEqual(Subject.objects.filter(school=school).count(), 1)
