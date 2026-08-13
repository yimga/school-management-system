"""Teacher roster classifies as ``staff`` (not ``students``) + maps its ids.

A real African / TVET SIS ``teachers_<timestamp>.csv`` carries the SAME
person-shaped columns as a student roster — NAME, GENDER, DATE OF BIRTH,
EMAIL, ADDRESS — so raw header overlap scores it ``students`` and every
teacher quarantines in the student lander (0 of 39 real teachers landed).

The columns genuinely cannot distinguish a student roster from a teacher
roster; the FILENAME can. These tests pin:

  * ``reconcile_domain_with_filename`` prefers the filename entity-token over
    the content guess ONLY between person-roster domains (students/staff/
    guardians/alumni), and never overrides non-roster content (grades);
  * a ``teachers.*`` file routes to ``staff`` through BOTH the accelerator path
    and the universal classifier; and
  * ``TEACHER UNIQUE ID`` maps to ``staff_external_id`` and ``NUMBER`` to
    ``phone`` so the staff lander has the id it requires to land the row.
"""

from __future__ import annotations

import io
import types

from django.test import TestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.accelerators.runmycampus_canonical import (
    PERSON_ROSTER_DOMAINS,
    reconcile_domain_with_filename,
)
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.ontology.catalog import all_synonyms


# Real header row of FILES FROM SITE/teachers_2026-01-18 22_42_32.778115.csv
# (BOM on NAME, leading space on " TEACHER UNIQUE ID").
_TEACHER_HEADERS = [
    "﻿NAME", " TEACHER UNIQUE ID", "USERNAME", "GIVEN PASSWORD",
    "USER PROFILE", "TEACHER IMAGE", "TEACHER IMAGE ID", "GENDER",
    "SUBJECTS", "CLASSROOMS", "DATE OF BIRTH", "NUMBER", "EMAIL", "ADDRESS",
]
_TEACHER_ROWS = [
    ["Esakenong Abel", "abel.esakenong", "abel.esakenong", "abel.esakenong_c17b",
     "", "", "", "Male", "96_98_106_229_", "1_2_3_4_5_6_7_", "", "", "", ""],
    ["Ekeke David", "david.ekeke", "david.ekeke", "david.ekeke_3507",
     "", "", "", "Male", "50_73_", "1_2_3_4_5_6_7_", "", "", "", ""],
]


class ReconcileDomainWithFilenameTests(TestCase):
    def test_teacher_filename_beats_student_content(self):
        # teachers_*.csv scored as students -> staff.
        self.assertEqual(
            reconcile_domain_with_filename("teachers_2026-01-18.csv", "students"),
            "staff",
        )

    def test_non_roster_content_is_never_overridden(self):
        # student_grades.csv: filename hint 'students', content 'grades' -> grades.
        self.assertEqual(
            reconcile_domain_with_filename("student_grades.csv", "grades"),
            "grades",
        )

    def test_agreement_is_left_untouched(self):
        self.assertEqual(
            reconcile_domain_with_filename("students_2026.csv", "students"),
            "students",
        )

    def test_none_content_passes_through(self):
        self.assertIsNone(reconcile_domain_with_filename("teachers.csv", None))

    def test_person_roster_set_shape(self):
        self.assertEqual(
            PERSON_ROSTER_DOMAINS, {"students", "staff", "guardians", "alumni"}
        )


class StaffOntologyIdAndPhoneTests(TestCase):
    def test_teacher_unique_id_aliases_staff_external_id(self):
        syns = {s.lower() for s in all_synonyms("staff_external_id", domain="staff")}
        self.assertIn("teacher_unique_id", syns)
        self.assertIn("matricule", syns)  # fr

    def test_number_aliases_staff_phone(self):
        syns = {s.lower() for s in all_synonyms("phone", domain="staff")}
        self.assertIn("number", syns)
        self.assertIn("phone", syns)


def _xlsx_bytes(headers, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _payload(data: bytes):
    return types.SimpleNamespace(content_opener=lambda: io.BytesIO(data))


def _make_teacher_bundle(filename: str, *, idem: str) -> MigrationBundle:
    data = _xlsx_bytes(_TEACHER_HEADERS, _TEACHER_ROWS)
    bundle = MigrationBundle.objects.create(
        label="teachers",
        intake_method=IntakeMethod.FILE_UPLOAD,
        idempotency_key=idem,
        status=BundleStatus.INGESTING,
        school=None,
    )
    art = MigrationArtifact.objects.create(
        bundle=bundle,
        path_within_bundle=filename,
        filename=filename,
        detected_format=ArtifactFormat.XLSX,
        byte_size=len(data),
        sha256="0" * 64,
    )
    store.capture_artifact_blob(art, _payload(data))
    return bundle


class TeacherRosterEndToEndTests(TestCase):
    def _assert_staff_and_ids(self, bundle):
        domain = (
            ((bundle.discovery_summary or {}).get("per_artifact_domain") or {})
            .get("teachers.xlsx", {})
            .get("domain")
        )
        self.assertEqual(
            domain, "staff",
            f"teacher roster must classify as staff, got {domain!r}",
        )
        per_artifact = (bundle.mapping_summary or {}).get("per_artifact") or {}
        mappings = {
            m["source_column"]: m["canonical_field"]
            for m in per_artifact.get("teachers.xlsx", [])
        }
        self.assertEqual(mappings.get("﻿NAME"), "full_name")
        self.assertEqual(mappings.get(" TEACHER UNIQUE ID"), "staff_external_id")
        self.assertEqual(mappings.get("NUMBER"), "phone")

    def test_accelerator_path_routes_to_staff(self):
        from apps.migration_cloud.pipeline import advance_bundle

        bundle = _make_teacher_bundle("teachers.xlsx", idem="teacher-accel")
        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        bundle.refresh_from_db()
        self._assert_staff_and_ids(bundle)

    def test_universal_classifier_routes_to_staff(self):
        from apps.migration_cloud.pipeline import advance_bundle

        bundle = _make_teacher_bundle("teachers.xlsx", idem="teacher-universal")
        advance_bundle(bundle_id=bundle.pk, use_accelerator=False)
        bundle.refresh_from_db()
        self._assert_staff_and_ids(bundle)
