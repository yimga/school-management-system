"""M32 increment 1 — Government/Ministry reporting translation engine tests.

Fail-before: prior to this increment the ``emis.translation`` package does not
exist, so every ``from emis.translation import ...`` / ``import
emis.translation.edfi_json`` below raises ``ModuleNotFoundError`` (an
``ImportError`` subclass) and all tests in this module error out. After the
increment the package imports, registers the Ed-Fi serializer on import, and the
assertions below hold.

Registry behaviour is exercised with ``SimpleTestCase`` (no DB). The Ed-Fi
serializer is exercised with ``TestCase`` (DB) — it asserts the *assembly +
serialization* (resource arrays present, student identity round-trips, stable
JSON), NOT the interop mapper internals (already tested with the adapter).
"""

from __future__ import annotations

import json
from datetime import date

from django.test import SimpleTestCase, TestCase

from emis.translation import (
    available_ministry_formats,
    get_ministry_format,
    translate_school_to_ministry_format,
)
from emis.translation.base import UnknownMinistryFormat
from emis.translation.edfi_json import EdFiJsonSerializer


class MinistryFormatRegistryTests(SimpleTestCase):
    """The outbound registry mirrors the accelerator registry shape."""

    def test_edfi_registered_after_import(self):
        keys = {entry["format_key"] for entry in available_ministry_formats()}
        self.assertIn("us-edfi-json", keys)

    def test_get_returns_the_serializer_class(self):
        self.assertIs(get_ministry_format("us-edfi-json"), EdFiJsonSerializer)

    def test_unknown_key_raises_unknown_ministry_format(self):
        with self.assertRaises(UnknownMinistryFormat):
            get_ministry_format("no-such-format")
        # It is a KeyError subclass, so existing KeyError handlers still catch it.
        self.assertTrue(issubclass(UnknownMinistryFormat, KeyError))

    def test_available_includes_edfi_entry_with_metadata(self):
        entry = next(
            e for e in available_ministry_formats() if e["format_key"] == "us-edfi-json"
        )
        self.assertEqual(entry["country_code"], "US")
        self.assertEqual(entry["content_type"], "application/json")
        self.assertEqual(entry["file_extension"], "json")
        self.assertTrue(entry["description"])

    def test_translate_unknown_format_raises(self):
        with self.assertRaises(UnknownMinistryFormat):
            translate_school_to_ministry_format(None, None, "no-such-format")


class EdFiJsonSerializerTests(TestCase):
    """End-to-end: canonical rows -> reused Ed-Fi mappers -> stable JSON document."""

    @classmethod
    def setUpTestData(cls):
        from apps.academics.models import AcademicYear
        from apps.people.models import StudentProfile
        from apps.schools.models import School

        cls.school = School.objects.create(
            name="M32 Ed-Fi Academy",
            slug="m32-edfi-academy",
            subdomain="m32-edfi-academy",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        cls.student_one = StudentProfile.objects.create(
            school=cls.school,
            academic_year=cls.year,
            first_name="Ada",
            last_name="Lovelace",
            student_code="STU-M32-001",
            gender="MALE",
            date_of_birth=date(2010, 3, 3),
            is_active=True,
        )
        cls.student_two = StudentProfile.objects.create(
            school=cls.school,
            academic_year=cls.year,
            first_name="Alan",
            last_name="Turing",
            student_code="STU-M32-002",
            is_active=True,
        )

    def _serialize(self):
        result = translate_school_to_ministry_format(
            self.school, self.year, "us-edfi-json"
        )
        return result, json.loads(result["content"])

    def test_content_parses_as_json_with_edfi_resource_arrays(self):
        _result, doc = self._serialize()
        self.assertIsInstance(doc, dict)
        for key in ("students", "studentSchoolAssociations", "grades"):
            self.assertIn(key, doc)
            self.assertIsInstance(doc[key], list)

    def test_students_and_associations_assembled_for_the_year(self):
        _result, doc = self._serialize()
        self.assertEqual(len(doc["students"]), 2)
        self.assertEqual(len(doc["studentSchoolAssociations"]), 2)
        # No evaluations seeded -> grades resource is a valid empty array.
        self.assertEqual(doc["grades"], [])

    def test_student_identity_field_maps_and_round_trips(self):
        _result, doc = self._serialize()
        unique_ids = {row["studentUniqueId"] for row in doc["students"]}
        self.assertEqual(unique_ids, {"STU-M32-001", "STU-M32-002"})
        # The same identity anchors the studentSchoolAssociation reference.
        assoc_ids = {
            row["studentReference"]["studentUniqueId"]
            for row in doc["studentSchoolAssociations"]
        }
        self.assertEqual(assoc_ids, unique_ids)

    def test_result_carries_transport_metadata(self):
        result, _doc = self._serialize()
        self.assertEqual(result["format_key"], "us-edfi-json")
        self.assertEqual(result["content_type"], "application/json")
        self.assertEqual(result["file_extension"], "json")
        self.assertEqual(
            result["filename"], "m32-edfi-academy_2025-2026_us-edfi-json.json"
        )

    def test_serialization_is_deterministic(self):
        # sort_keys => byte-stable output across identical inputs.
        first = translate_school_to_ministry_format(self.school, self.year, "us-edfi-json")
        second = translate_school_to_ministry_format(self.school, self.year, "us-edfi-json")
        self.assertEqual(first["content"], second["content"])
