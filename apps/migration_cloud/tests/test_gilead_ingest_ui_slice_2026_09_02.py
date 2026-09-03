"""Gilead ingest + UI slice — subject category, teacher directory, title rows."""

from __future__ import annotations

import io
import types
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, TransactionTestCase

from apps.academics.models import Department, Subject, Specialty
from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.landers.academics_lander import AcademicsLander
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.orchestrator import _xlsx_rows, apply_bundle
from apps.migration_cloud.pipeline import advance_bundle
from apps.migration_cloud.spreadsheet_headers import pick_header_row_index
from apps.people.models import TeacherProfile
from apps.people.views_backend import backend_teacher_list
from apps.schools.models import School

User = get_user_model()
MAMA_NOVI = Path(
    r"c:/Users/yimga/Documents/HY_DOC_MAINPC/Docs for Others_Friends_family/Gilead Tech High/Mama Novi"
)


class SpreadsheetHeaderDetectionTests(TestCase):
    def test_gilead_directory_title_rows_skipped(self):
        title_rows = [
            ("GILEAD TECHNICAL HIGH SCHOOL (GILEAD TECH) SMALL SOPPO - BUEA", None, None, None),
            ("TELEPHONE DIRECTORY FOR 2026/2027SCHOOL YEAR", None, None, None),
            ("NAME", "POST / FUNCTION / Role", "SPECIALTY", "TELEPHONE NUMBER"),
        ]
        self.assertEqual(pick_header_row_index(title_rows), 2)


class AcademicsCategoryLanderTests(TestCase):
    def test_category_lands_and_reimport_respects_deliberate_values(self):
        school = School.objects.create(
            name="Cat School",
            subdomain="cat-school",
            country_code="CM",
        )
        ctx = LanderContext(
            school=school,
            schema_name="",
            bundle_id=1,
            artifact_id=1,
            dry_run=False,
        )
        lander = AcademicsLander()
        lander.land(
            canonical_rows=iter(
                [{"subject_name": "WORKSHOP", "category": "Professional"}]
            ),
            ctx=ctx,
        )
        subj = Subject.objects.get(school=school, name="WORKSHOP")
        self.assertEqual(subj.category, Subject.Category.PROFESSIONAL)

        result = lander.land(
            canonical_rows=iter(
                [{"subject_name": "WORKSHOP", "category": "General"}]
            ),
            ctx=ctx,
        )
        subj.refresh_from_db()
        # Subject carries no provenance column, so the lander cannot tell an
        # import-set category from one a person chose in the UI. The rule that
        # never destroys human work silently is backfill-only-default: a row
        # already OFF the default keeps its category and the disagreement is
        # REPORTED (record_row_note), for the operator to settle.
        self.assertEqual(subj.category, Subject.Category.PROFESSIONAL)
        self.assertTrue(
            any("kept category" in str(n) for n in getattr(result, "notes", []) or []),
            "the disagreement must be reported, not silent",
        )

        # The re-import case that DOES update: a row still at the field default
        # takes the file's category.
        blank = Subject.objects.create(school=school, name="DRAWING")
        self.assertEqual(blank.category, Subject.Category.OTHER)
        lander.land(
            canonical_rows=iter(
                [{"subject_name": "DRAWING", "category": "General"}]
            ),
            ctx=ctx,
        )
        blank.refresh_from_db()
        self.assertEqual(blank.category, Subject.Category.GENERAL)


def _xlsx_bytes(rows: list[tuple]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _payload(data: bytes):
    return types.SimpleNamespace(content_opener=lambda: io.BytesIO(data))


class TelephoneDirectoryImportTests(TestCase):
    def test_title_row_directory_lands_phone_specialty_role(self):
        data = _xlsx_bytes(
            [
                ("GILEAD TECHNICAL HIGH SCHOOL", None, None, None),
                ("TELEPHONE DIRECTORY 2026/2027", None, None, None),
                ("NAME", "POST / FUNCTION / Role", "SPECIALTY", "TELEPHONE NUMBER"),
                ("ROLAND TAZOH NONGNI", "PROPRIETOR", "ACCOUNTING", None),
                ("FONONG REUBEN TEKUM", "PRINCIPAL", "MATHEMATICS", "6 76 31 98 28"),
            ]
        )
        header, _ = _xlsx_rows(data)
        self.assertEqual(
            [str(h).strip() if h else "" for h in header],
            ["NAME", "POST / FUNCTION / Role", "SPECIALTY", "TELEPHONE NUMBER"],
        )

        school = School.objects.create(
            name="Gilead Directory",
            subdomain="gilead-directory",
            country_code="CM",
            settings={"migration_gap_fill_provisioning": True},
        )
        bundle = MigrationBundle.objects.create(
            label="tel-dir",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="tel-dir-e2e",
            status=BundleStatus.INGESTING,
            school=school,
        )
        art = MigrationArtifact.objects.create(
            bundle=bundle,
            path_within_bundle="telephone_directory.xlsx",
            filename="telephone_directory.xlsx",
            detected_format=ArtifactFormat.XLSX,
            byte_size=len(data),
            sha256="c" * 64,
        )
        store.capture_artifact_blob(art, _payload(data))

        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        bundle.refresh_from_db()
        domain = (
            ((bundle.discovery_summary or {}).get("per_artifact_domain") or {})
            .get("telephone_directory.xlsx", {})
            .get("domain")
        )
        self.assertEqual(domain, "staff", bundle.discovery_summary)

        apply_bundle(bundle_id=bundle.pk, workers=1)
        principal = (
            TeacherProfile.objects.filter(
                school=school, user__last_name__icontains="TEKUM"
            )
            .select_related("user", "department")
            .first()
        )
        self.assertIsNotNone(principal)
        self.assertEqual(principal.user.role, User.Role.PRINCIPAL)
        self.assertIn("76 31 98 28", principal.phone or "")
        self.assertIsNotNone(principal.department)
        self.assertEqual(principal.department.name, "MATHEMATICS")


class MamaNoviSubjectsCategoryTests(TestCase):
    def test_subjects_file_categories_land(self):
        src = MAMA_NOVI / "subjects_2026.xlsx"
        if not src.is_file():
            self.skipTest("Mama Novi subjects fixture not on this machine")

        raw = src.read_bytes()
        school = School.objects.create(
            name="Gilead Subjects",
            subdomain="gilead-subjects-cat",
            country_code="CM",
        )
        bundle = MigrationBundle.objects.create(
            label="subjects-cat",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="subjects-cat-e2e",
            status=BundleStatus.INGESTING,
            school=school,
        )
        art = MigrationArtifact.objects.create(
            bundle=bundle,
            path_within_bundle="subjects_2026.xlsx",
            filename="subjects_2026.xlsx",
            detected_format=ArtifactFormat.XLSX,
            byte_size=len(raw),
            sha256="d" * 64,
        )
        store.capture_artifact_blob(art, _payload(raw))
        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        apply_bundle(bundle_id=bundle.pk, workers=1)

        workshop = Subject.objects.filter(school=school, name="WORKSHOP").first()
        health = Subject.objects.filter(
            school=school, name__icontains="HEALTH, SAFETY"
        ).first()
        self.assertIsNotNone(workshop)
        self.assertEqual(workshop.category, Subject.Category.PROFESSIONAL)
        self.assertIsNotNone(health)
        self.assertEqual(health.category, Subject.Category.GENERAL)


class BackendTeacherListPhoneRoleTests(TestCase):
    def test_csv_export_includes_phone_and_role(self):
        school = School.objects.create(
            name="Teacher CSV",
            subdomain="teacher-csv",
            country_code="CM",
        )
        dept = Department.objects.create(school=school, name="MATHEMATICS", code="DPT-M")
        user = User.objects.create_user(
            username="principal1",
            email="principal1@example.com",
            password="x",
            first_name="Reuben",
            last_name="Tekum",
            role=User.Role.PRINCIPAL,
        )
        TeacherProfile.objects.create(
            school=school,
            user=user,
            staff_id="T-001",
            phone="676319828",
            department=dept,
        )
        admin = User.objects.create_superuser(
            username="csv-admin", email="csv-admin@example.com", password="x"
        )
        req = RequestFactory().get("/backend/teachers/?format=csv")
        req.user = admin
        req.school = school
        resp = backend_teacher_list(req)
        body = resp.content.decode()
        self.assertIn("676319828", body)
        self.assertIn("Principal", body)
        self.assertIn("MATHEMATICS", body)


# Stays a TransactionTestCase, deliberately. This class drives a real bundle
# apply, and apps/migration_cloud/orchestrator.py runs its waves in a
# ThreadPoolExecutor (line ~576, collected at ~588). Under TestCase the outer
# test holds an open transaction on its connection while the worker threads
# open their own, and _create_audit_run dies with
#   sqlite3.OperationalError: database is locked
# Measured 2026-09-03: converted -> that failure; reverted -> 6 passed.
# It therefore FLUSHES the seeded catalog at teardown; order this module last.
# See docs/audits/TRANSACTION_TESTCASE_FLUSH_2026_09_03.md
class MamaNoviFullBundleTests(TransactionTestCase):
    """End-to-end proof for all four Mama Novi fixtures when present locally."""

    _FILES: tuple[tuple[str, str], ...] = (
        ("specialties_2026.xlsx", "specialties"),
        ("subjects_2026.xlsx", "academics"),
        ("student_2026.xlsx", "students"),
        (
            "GILEAD TECHNICAL HIGH SCHOOL 2026-20297 TELEPHONE DIRECTORY.xlsx",
            "staff",
        ),
    )

    def test_four_file_bundle_lands_core_tier1_fields(self):
        missing = [name for name, _domain in self._FILES if not (MAMA_NOVI / name).is_file()]
        if missing:
            self.skipTest(f"Mama Novi fixtures missing: {', '.join(missing)}")

        school = School.objects.create(
            name="Gilead Full Bundle",
            subdomain="gilead-full-bundle",
            country_code="CM",
            settings={"migration_gap_fill_provisioning": True},
        )
        bundle = MigrationBundle.objects.create(
            label="mama-novi-full",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="mama-novi-full-e2e",
            status=BundleStatus.INGESTING,
            school=school,
        )
        for idx, (filename, _expected_domain) in enumerate(self._FILES):
            raw = (MAMA_NOVI / filename).read_bytes()
            art = MigrationArtifact.objects.create(
                bundle=bundle,
                path_within_bundle=filename,
                filename=filename,
                detected_format=ArtifactFormat.XLSX,
                byte_size=len(raw),
                sha256=f"{idx:064d}",
            )
            store.capture_artifact_blob(art, _payload(raw))

        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        apply_bundle(bundle_id=bundle.pk, workers=2)

        self.assertGreater(
            Subject.objects.filter(school=school).count(),
            0,
            "subjects should land from subjects_2026.xlsx",
        )
        prof_count = Subject.objects.filter(
            school=school, category=Subject.Category.PROFESSIONAL
        ).count()
        gen_count = Subject.objects.filter(
            school=school, category=Subject.Category.GENERAL
        ).count()
        self.assertGreater(prof_count, 0, "professional categories should land")
        self.assertGreater(gen_count, 0, "general categories should land")

        self.assertGreater(
            TeacherProfile.objects.filter(school=school).count(),
            0,
            "staff directory should land teachers",
        )
        with_phone = TeacherProfile.objects.filter(
            school=school, phone__isnull=False
        ).exclude(phone="").count()
        self.assertGreater(with_phone, 0, "directory phone numbers should land")

        self.assertGreater(
            TeacherProfile.objects.filter(school=school, department__isnull=False).count(),
            0,
            "specialty/department should land on teachers",
        )
        self.assertGreater(
            Specialty.objects.filter(school=school).count(),
            0,
            "specialties file should land specialty catalog rows",
        )
