"""Tests for Cameroon TVET ingestion lexicon + curriculum coefficient wiring."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from apps.academics.models import Specialty, SpecialtySubject, Subject
from apps.migration_cloud.ingestion_lexicon import (
    apply_catalog_shape_adjustments,
    build_ingestion_lexicon,
    compile_offline_ingestion_manifest,
    is_staff_directory_shape,
    is_subject_catalog_shape,
    is_specialty_catalog_shape,
    resolve_school_ingestion_lexicon,
    row_looks_like_subject_catalog_entry,
)
from apps.migration_cloud.landers.academics_lander import AcademicsLander
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.classifiers.domain import DomainCandidate
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


class IngestionLexiconShapeTests(SimpleTestCase):
    def test_specialty_catalog_not_misread_as_subject_via_trade_vocabulary(self):
        headers = {"name", "code", "department"}
        rows = [{"name": "PLUMBING", "code": "PL", "department": "PLUMBING"}]
        self.assertTrue(is_specialty_catalog_shape(headers, rows))
        self.assertFalse(is_subject_catalog_shape(headers, rows))

    def test_bom_prefixed_headers_still_shape_as_specialty_catalog(self):
        headers = {"\ufeffname", "code", "department"}
        self.assertTrue(is_specialty_catalog_shape(headers, None))
        self.assertFalse(is_subject_catalog_shape(headers, None))

    def test_subject_catalog_shape_from_headers(self):
        self.assertTrue(
            is_subject_catalog_shape({"title", "description", "category", "coef"})
        )
        self.assertFalse(is_specialty_catalog_shape({"title", "description", "category", "coef"}))

    def test_specialty_catalog_shape(self):
        self.assertTrue(is_specialty_catalog_shape({"name", "code", "department"}))
        self.assertFalse(is_subject_catalog_shape({"name", "code", "department"}))

    def test_telephone_directory_not_misread_as_subject_catalog(self):
        headers = {"name", "post_function_role", "specialty", "telephone_number"}
        rows = [
            {
                "name": "ROLAND TAZOH NONGNI",
                "post_function_role": "PROPRIETOR",
                "specialty": "ACCOUNTING",
                "telephone_number": None,
            },
            {
                "name": "FONONG REUBEN TEKUM",
                "post_function_role": "PRINCIPAL",
                "specialty": "MATHEMATICS",
                "telephone_number": "6 76 31 98 28",
            },
        ]
        self.assertTrue(is_staff_directory_shape(headers, rows))
        self.assertFalse(is_subject_catalog_shape(headers, rows))

    def test_telephone_directory_staff_stays_above_classifier_threshold(self):
        ranked = [
            DomainCandidate("staff", 0.722, ["name", "role", "phone"], ""),
            DomainCandidate("specialties", 0.525, ["department"], ""),
        ]
        headers = {"name", "post_function_role", "specialty", "telephone_number"}
        rows = [
            {
                "name": "A",
                "post_function_role": "PROPRIETOR",
                "specialty": "PLUMBING",
                "telephone_number": "123",
            },
        ]
        school = School(country_code="CM", settings={})
        adjusted = apply_catalog_shape_adjustments(
            ranked,
            normalized_headers=headers,
            sample_rows=rows,
            school=school,
        )
        self.assertEqual(adjusted[0].domain, "staff")
        self.assertGreaterEqual(adjusted[0].confidence, 0.70)

    def test_catalog_shape_boosts_academics_over_specialties(self):
        ranked = [
            DomainCandidate("specialties", 0.55, ["name"], ""),
            DomainCandidate("academics", 0.50, ["subject_name"], ""),
        ]
        school = School(country_code="CM", settings={"grading": {"curriculum_tracks": ["vocational_trade"]}})
        adjusted = apply_catalog_shape_adjustments(
            ranked,
            normalized_headers={"title", "category", "coef"},
            sample_rows=[{"category": "Professional", "title": "OHADA FINANCIAL ACCOUNTING"}],
            school=school,
        )
        self.assertEqual(adjusted[0].domain, "academics")

    def test_offline_manifest_cm(self):
        manifest = compile_offline_ingestion_manifest("CMR", institution_profile="technical_vocational")
        self.assertEqual(manifest["country_code"], "CM")
        entities = {m["target_entity"] for m in manifest["lexicon_mappings"]}
        self.assertIn("SUBJECT", entities)
        self.assertIn("SPECIALTY", entities)


class SpecialtyLanderGuardTests(SimpleTestCase):
    def test_subject_shaped_row_detected(self):
        row = {"name": "WORKSHOP", "category": "Professional", "coef": "6"}
        self.assertTrue(row_looks_like_subject_catalog_entry(row))

    def test_global_manifests_ng_fr_uses_coefficient_or_credit(self):
        ng = build_ingestion_lexicon("NG")
        fr = build_ingestion_lexicon("FR", institution_profile="technical_vocational")
        self.assertEqual(ng.country_code, "NG")
        self.assertEqual(fr.country_code, "FR")
        self.assertTrue(fr.uses_coefficients)
        manifest_ng = compile_offline_ingestion_manifest("NG")
        self.assertIn("weight_type", manifest_ng)
        self.assertIn("lexicon_mappings", manifest_ng)


class AcademicsCoefficientLanderTests(TestCase):
    def test_coef_links_specialty_subject_for_general_broadcast(self):
        school = _school(
            "coef",
            settings={"grading": {"curriculum_tracks": ["vocational_trade"]}},
        )
        sp_a = Specialty.objects.create(
            school=school,
            name="PLUMBING",
            code="PL",
            department_id=self._dept(school, "PLUMBING DEPT"),
        )
        sp_b = Specialty.objects.create(
            school=school,
            name="ACCOUNTING",
            code="ACCOUNTX",
            department_id=self._dept(school, "ACCOUNTING DEPT"),
        )
        ctx = LanderContext(
            school=school,
            schema_name="",
            bundle_id=1,
            artifact_id=1,
            dry_run=False,
        )
        AcademicsLander().land(
            canonical_rows=iter(
                [{"title": "MATHEMATICS", "category": "General", "coef": "3"}]
            ),
            ctx=ctx,
        )
        subj = Subject.objects.get(school=school, name="MATHEMATICS")
        links = SpecialtySubject.objects.filter(subject=subj, specialty__in=[sp_a, sp_b])
        self.assertEqual(links.count(), 2)
        self.assertEqual(links.first().coefficient, Decimal("3"))

    @staticmethod
    def _dept(school, name):
        from apps.academics.models import Department

        return Department.objects.create(school=school, name=name, code=name[:8]).pk

    def test_professional_subject_heuristic_links_plumbing(self):
        school = _school("heur")
        dept = self._dept(school, "PL DEPT")
        sp = Specialty.objects.create(school=school, name="PLUMBING", code="PL", department_id=dept)
        ctx = LanderContext(
            school=school,
            schema_name="",
            bundle_id=2,
            artifact_id=2,
            dry_run=False,
        )
        AcademicsLander().land(
            canonical_rows=iter(
                [
                    {
                        "title": "WATER SUPPLY AND DISTRIBUTION",
                        "category": "Professional",
                        "coef": "2",
                    }
                ]
            ),
            ctx=ctx,
        )
        subj = Subject.objects.get(school=school, name="WATER SUPPLY AND DISTRIBUTION")
        self.assertTrue(
            SpecialtySubject.objects.filter(specialty=sp, subject=subj, coefficient=Decimal("2")).exists()
        )

    def test_school_lexicon_resolves_cm(self):
        school = _school(
            "lex",
            settings={"grading": {"curriculum_tracks": ["vocational_trade"]}},
        )
        lex = resolve_school_ingestion_lexicon(school)
        self.assertEqual(lex.country_code, "CM")
        self.assertTrue(lex.header_targets_entity("filiere", "specialty"))
