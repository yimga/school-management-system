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
