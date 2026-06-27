"""Real capture -> restore round-trip for tenant immutable DR snapshots.

These tests prove the snapshot payload (schema 2.1) carries *restorable row data*
(not counts-only) and that ``restore_from_snapshot`` MATERIALIZES those rows into
a fresh target school — verifying the HMAC signature first and failing closed on
tamper. Schema 2.1 extends the restorable surface from the academic config core
to also include staff identities (``accounts.User`` + ``people.TeacherProfile``)
and the finance ledger (``finance.ComplianceProfile`` + ``finance.Invoice`` +
``finance.Payment``).

Tagged ``requires_postgres`` + ``@tag("dr_snapshot_restore")`` and wired into
``.github/workflows/django-tests-postgres.yml`` so the round-trip runs against
the same Postgres engine production uses. The restore path is ORM-only and also
passes on SQLite, but Postgres is the contract-of-record per the project's
Postgres-test convention (mirrors
``apps/schoolops/tests/test_resource_booking.py``).
"""

from __future__ import annotations

import unittest
import uuid
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings, tag

from apps.academics.models import AcademicYear, Classroom, Department, Term
from apps.finance.models import ComplianceProfile, Invoice, Payment
from apps.lifecycle.tenant_dr_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    capture_daily_snapshot,
    restore_from_snapshot,
    verify_signature,
)
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School

User = get_user_model()

requires_postgres = unittest.skipUnless(
    connection.vendor == "postgresql",
    "DR snapshot restore round-trip is contract-tested on PostgreSQL "
    "(matches the production engine; ORM path also runs on SQLite).",
)


@override_settings(SECRET_KEY="test-dr-restore-roundtrip-signing-key")
@tag("dr_snapshot_restore")
class DrSnapshotRestoreRoundTripBaseTests(TestCase):
    """Backend-agnostic round-trip assertions (run on every engine)."""

    def _seed_source_school(self):
        slug = f"src-{uuid.uuid4().hex[:10]}"
        school = School.objects.create(
            name="Source Academy",
            slug=slug,
            subdomain=slug,
        )
        year = AcademicYear.objects.create(
            school=school,
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-07-15",
            is_active=True,
        )
        dept = Department.objects.create(
            school=school,
            name="Sciences",
            code=f"SCI-{uuid.uuid4().hex[:6]}",
        )
        Term.objects.create(
            school=school,
            academic_year=year,
            name="FIRST",
            position=1,
            start_date="2025-09-01",
            end_date="2025-12-20",
            is_active=True,
        )
        Classroom.objects.create(
            school=school,
            academic_year=year,
            department=dept,
            name="Form 1A",
            code=f"F1A-{uuid.uuid4().hex[:6]}",
        )
        StudentProfile.objects.create(
            school=school,
            first_name="Ada",
            last_name="Lovelace",
            student_code=f"STU-{uuid.uuid4().hex[:8]}",
            date_of_birth="2013-05-10",
        )
        return school

    def _seed_source_school_with_staff_and_finance(self):
        """Config core + a teacher (with required User) + an invoice + a payment.

        This exercises the schema-2.1 surface: the non-null ``TeacherProfile.user``
        OneToOne, the PROTECT ``Invoice.profile`` parent, and the
        ``Payment``→``Invoice`` intra-snapshot FK.
        """
        school = self._seed_source_school()

        # Staff identity behind the teacher (non-null OneToOne).
        teacher_user = User.objects.create_user(
            username=f"teacher-{uuid.uuid4().hex[:8]}",
            email="grace.hopper@example.test",
            first_name="Grace",
            last_name="Hopper",
            role=User.Role.TEACHER,
        )
        dept = Department.objects.get(school=school)
        teacher = TeacherProfile.objects.create(
            school=school,
            user=teacher_user,
            staff_id=f"STAFF-{uuid.uuid4().hex[:6]}",
            position_title="Mathematics Lead",
            department=dept,
            salary_amount=Decimal("4200.00"),
        )

        # PROTECT parent for the invoice (platform/region config, not school-scoped).
        profile = ComplianceProfile.objects.create(
            name=f"Profile {uuid.uuid4().hex[:6]}",
            country_code="CM",
            currency_code="XAF",
        )
        student = StudentProfile.objects.get(school=school)
        year = AcademicYear.objects.get(school=school)
        invoice = Invoice.objects.create(
            school=school,
            profile=profile,
            student=student,
            academic_year=year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            total_amount=Decimal("500.00"),
            reference=f"REF-{uuid.uuid4().hex[:6]}",
        )
        payment = Payment.objects.create(
            school=school,
            invoice=invoice,
            student=student,
            amount=Decimal("200.00"),
            method="BANK",
            reference_number=f"PAY-{uuid.uuid4().hex[:8]}",
            currency_code="XAF",
        )
        return {
            "school": school,
            "teacher_user": teacher_user,
            "teacher": teacher,
            "profile": profile,
            "invoice": invoice,
            "payment": payment,
        }

    def test_payload_carries_real_rows_not_just_counts(self):
        school = self._seed_source_school()
        meta = capture_daily_snapshot(school)
        # Snapshot blob is non-trivial now (real rows, not an all-zero counts blob).
        self.assertGreater(meta["byte_size"], 200)

        restored = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(school.pk),
            expected_sig=meta["signature_hex"],
            target_school=school,  # idempotent re-apply onto the same tenant
        )
        self.assertEqual(restored["schema_version"], SNAPSHOT_SCHEMA_VERSION)
        tables = restored["tables"]
        self.assertEqual(len(tables["academics.AcademicYear"]), 1)
        self.assertEqual(len(tables["academics.Term"]), 1)
        self.assertEqual(len(tables["academics.Classroom"]), 1)
        self.assertEqual(len(tables["people.StudentProfile"]), 1)
        # The student row carries real field data, not a count.
        student_fields = tables["people.StudentProfile"][0]["fields"]
        self.assertEqual(student_fields["first_name"], "Ada")
        self.assertEqual(student_fields["last_name"], "Lovelace")

    def test_restore_materializes_rows_into_fresh_target(self):
        source = self._seed_source_school()
        src_year = AcademicYear.objects.get(school=source)
        src_classroom = Classroom.objects.get(school=source)
        src_student = StudentProfile.objects.get(school=source)

        meta = capture_daily_snapshot(source)

        # Fresh, EMPTY target tenant — the real self-host shape.
        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="Recovered Academy",
            slug=target_slug,
            subdomain=target_slug,
        )
        self.assertEqual(AcademicYear.objects.filter(school=target).count(), 0)
        self.assertEqual(StudentProfile.objects.filter(school=target).count(), 0)

        result = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(source.pk),
            expected_sig=meta["signature_hex"],
            target_school=target,
        )

        # Rows now EXIST under the target school (materialized, not counted).
        self.assertEqual(AcademicYear.objects.filter(school=target).count(), 1)
        self.assertEqual(Department.objects.filter(school=target).count(), 1)
        self.assertEqual(Term.objects.filter(school=target).count(), 1)
        self.assertEqual(Classroom.objects.filter(school=target).count(), 1)
        self.assertEqual(StudentProfile.objects.filter(school=target).count(), 1)

        # Field-level fidelity: values match the source, with fresh pks.
        tgt_year = AcademicYear.objects.get(school=target)
        self.assertEqual(tgt_year.name, src_year.name)
        self.assertEqual(str(tgt_year.start_date), str(src_year.start_date))
        self.assertNotEqual(tgt_year.pk, src_year.pk)

        tgt_student = StudentProfile.objects.get(school=target)
        self.assertEqual(tgt_student.first_name, src_student.first_name)
        self.assertEqual(tgt_student.last_name, src_student.last_name)
        self.assertEqual(tgt_student.student_code, src_student.student_code)
        # Out-of-scope FK is deliberately cleared on restore.
        self.assertIsNone(tgt_student.user_id)

        # Intra-snapshot FK was remapped to the freshly restored parent.
        tgt_classroom = Classroom.objects.get(school=target)
        self.assertEqual(tgt_classroom.academic_year_id, tgt_year.pk)
        self.assertNotEqual(tgt_classroom.pk, src_classroom.pk)

        # Restore report is honest about what it created.
        rep = result["restored"]["tables"]
        self.assertEqual(rep["academics.AcademicYear"]["created"], 1)
        self.assertEqual(rep["people.StudentProfile"]["created"], 1)

    def test_restore_is_idempotent(self):
        source = self._seed_source_school()
        meta = capture_daily_snapshot(source)
        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="Recovered Twice", slug=target_slug, subdomain=target_slug
        )
        kwargs = dict(
            school_id=str(source.pk),
            expected_sig=meta["signature_hex"],
            target_school=target,
        )
        restore_from_snapshot(Path(meta["primary_uri"]), **kwargs)
        # Second apply must not duplicate rows.
        second = restore_from_snapshot(Path(meta["primary_uri"]), **kwargs)
        self.assertEqual(StudentProfile.objects.filter(school=target).count(), 1)
        self.assertEqual(AcademicYear.objects.filter(school=target).count(), 1)
        self.assertEqual(
            second["restored"]["tables"]["people.StudentProfile"]["updated"], 1
        )
        self.assertEqual(
            second["restored"]["tables"]["people.StudentProfile"]["created"], 0
        )

    # ------------------------------------------------------------------ #
    # Schema 2.1: TeacherProfile + Invoice + Payment round-trip          #
    # ------------------------------------------------------------------ #
    def test_payload_carries_teacher_invoice_payment_rows(self):
        seed = self._seed_source_school_with_staff_and_finance()
        meta = capture_daily_snapshot(seed["school"])
        restored = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(seed["school"].pk),
            expected_sig=meta["signature_hex"],
            target_school=seed["school"],  # idempotent re-apply onto same tenant
        )
        self.assertEqual(restored["schema_version"], SNAPSHOT_SCHEMA_VERSION)
        tables = restored["tables"]
        # The shared parents and the three new child tables all carry real rows.
        self.assertEqual(len(tables["accounts.User"]), 1)
        self.assertEqual(len(tables["finance.ComplianceProfile"]), 1)
        self.assertEqual(len(tables["people.TeacherProfile"]), 1)
        self.assertEqual(len(tables["finance.Invoice"]), 1)
        self.assertEqual(len(tables["finance.Payment"]), 1)
        # Real field data, not a count.
        self.assertEqual(
            tables["finance.Invoice"][0]["fields"]["total_amount"], "500.00"
        )
        self.assertEqual(tables["finance.Payment"][0]["fields"]["amount"], "200.00")

    def test_restore_materializes_teacher_invoice_payment_into_fresh_target(self):
        """Restore the staff + finance ledger onto a fresh, EMPTY target tenant —
        the real self-host shape.

        Note: ``Invoice.payment_code`` / ``Payment.reference_number`` are GLOBALLY
        unique. A genuine self-host DR restores onto a *fresh database* where the
        source rows do not exist, so there is no collision. To model that "empty
        destination, no pre-existing finance rows" shape inside a single test DB,
        the source ledger rows are deleted after the signed snapshot is captured;
        the snapshot blob is the sole source of truth for the restore, exactly as
        on a clean instance.
        """
        seed = self._seed_source_school_with_staff_and_finance()
        source = seed["school"]
        src_invoice_code = seed["invoice"].payment_code
        src_invoice_total = seed["invoice"].total_amount
        src_invoice_status = seed["invoice"].status
        src_payment_amount = seed["payment"].amount
        src_payment_ref = seed["payment"].reference_number
        src_teacher_title = seed["teacher"].position_title
        src_teacher_staff_id = seed["teacher"].staff_id
        src_user = seed["teacher_user"]

        meta = capture_daily_snapshot(source)

        # Drop the globally-unique-coded ledger rows so the destination is empty
        # of them (a fresh-instance restore never has the source rows present).
        Payment.objects.filter(school=source).delete()
        Invoice.objects.filter(school=source).delete()
        TeacherProfile.objects.filter(school=source).delete()

        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="Recovered Finance", slug=target_slug, subdomain=target_slug
        )
        self.assertEqual(TeacherProfile.objects.filter(school=target).count(), 0)
        self.assertEqual(Invoice.objects.filter(school=target).count(), 0)
        self.assertEqual(Payment.objects.filter(school=target).count(), 0)

        result = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(source.pk),
            expected_sig=meta["signature_hex"],
            target_school=target,
        )

        # Rows now exist under the target school (materialized, not counted).
        self.assertEqual(TeacherProfile.objects.filter(school=target).count(), 1)
        self.assertEqual(Invoice.objects.filter(school=target).count(), 1)
        self.assertEqual(Payment.objects.filter(school=target).count(), 1)

        # Teacher: required OneToOne user reconstituted by username (upsert), not
        # nulled. The User is keyed by the GLOBAL username, so it resolves to the
        # one existing source user (exactly one user per username).
        tgt_teacher = TeacherProfile.objects.get(school=target)
        self.assertEqual(tgt_teacher.position_title, src_teacher_title)
        self.assertEqual(tgt_teacher.staff_id, src_teacher_staff_id)
        self.assertIsNotNone(tgt_teacher.user_id)
        self.assertEqual(tgt_teacher.user.username, src_user.username)
        self.assertEqual(tgt_teacher.user_id, src_user.pk)
        # User identity restored faithfully, including the password hash.
        self.assertEqual(tgt_teacher.user.password, src_user.password)
        self.assertEqual(tgt_teacher.user.email, src_user.email)
        # Department FK remapped to the restored parent under the target school.
        self.assertIsNotNone(tgt_teacher.department_id)
        self.assertEqual(tgt_teacher.department, Department.objects.get(school=target))

        # Invoice: PROTECT profile parent restored + remapped; values faithful.
        tgt_invoice = Invoice.objects.get(school=target)
        self.assertEqual(tgt_invoice.total_amount, src_invoice_total)
        self.assertEqual(tgt_invoice.payment_code, src_invoice_code)
        self.assertEqual(tgt_invoice.status, src_invoice_status)
        self.assertIsNotNone(tgt_invoice.profile_id)
        self.assertEqual(tgt_invoice.profile.country_code, "CM")
        # In-scope student FK remapped to the restored student under target.
        self.assertEqual(tgt_invoice.student, StudentProfile.objects.get(school=target))
        # Out-of-scope optional FKs cleared.
        self.assertIsNone(tgt_invoice.counterparty_id)
        self.assertIsNone(tgt_invoice.created_by_id)

        # Payment: intra-snapshot invoice FK remapped to the restored invoice.
        tgt_payment = Payment.objects.get(school=target)
        self.assertEqual(tgt_payment.amount, src_payment_amount)
        self.assertEqual(tgt_payment.reference_number, src_payment_ref)
        self.assertEqual(tgt_payment.invoice_id, tgt_invoice.pk)

        # Restore report is honest. Teacher / invoice / payment are NEW under the
        # target. The shared parents (User by global username, ComplianceProfile by
        # name+country_code) already exist from the source, so they UPDATE in place.
        rep = result["restored"]["tables"]
        self.assertEqual(rep["people.TeacherProfile"]["created"], 1)
        self.assertEqual(rep["finance.Invoice"]["created"], 1)
        self.assertEqual(rep["finance.Payment"]["created"], 1)
        self.assertEqual(rep["accounts.User"]["updated"], 1)
        self.assertEqual(rep["accounts.User"]["created"], 0)
        self.assertEqual(rep["finance.ComplianceProfile"]["updated"], 1)
        self.assertEqual(rep["finance.ComplianceProfile"]["created"], 0)

    def test_restore_teacher_invoice_payment_is_idempotent(self):
        seed = self._seed_source_school_with_staff_and_finance()
        source = seed["school"]
        meta = capture_daily_snapshot(source)

        # Empty the destination of the globally-unique-coded ledger rows (a fresh
        # instance never has the source rows) so the first restore CREATES and the
        # second restore must UPSERT the same rows — proving idempotency.
        Payment.objects.filter(school=source).delete()
        Invoice.objects.filter(school=source).delete()
        TeacherProfile.objects.filter(school=source).delete()

        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="Recovered Finance Twice", slug=target_slug, subdomain=target_slug
        )
        kwargs = dict(
            school_id=str(source.pk),
            expected_sig=meta["signature_hex"],
            target_school=target,
        )
        restore_from_snapshot(Path(meta["primary_uri"]), **kwargs)
        second = restore_from_snapshot(Path(meta["primary_uri"]), **kwargs)

        # Second apply must not duplicate any of the new tables.
        self.assertEqual(TeacherProfile.objects.filter(school=target).count(), 1)
        self.assertEqual(Invoice.objects.filter(school=target).count(), 1)
        self.assertEqual(Payment.objects.filter(school=target).count(), 1)
        rep = second["restored"]["tables"]
        self.assertEqual(rep["people.TeacherProfile"]["updated"], 1)
        self.assertEqual(rep["people.TeacherProfile"]["created"], 0)
        self.assertEqual(rep["finance.Invoice"]["updated"], 1)
        self.assertEqual(rep["finance.Invoice"]["created"], 0)
        self.assertEqual(rep["finance.Payment"]["updated"], 1)
        self.assertEqual(rep["finance.Payment"]["created"], 0)

    def test_tampered_blob_fails_closed_before_any_write(self):
        source = self._seed_source_school()
        meta = capture_daily_snapshot(source)
        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="No Recovery", slug=target_slug, subdomain=target_slug
        )

        # Flip one byte in the on-disk blob -> signature must no longer verify.
        path = Path(meta["primary_uri"])
        data = bytearray(path.read_bytes())
        data[-1] ^= 0xFF
        path.write_bytes(bytes(data))
        self.assertFalse(
            verify_signature(bytes(data), meta["signature_hex"], school_id=str(source.pk))
        )

        with self.assertRaises(ValueError):
            restore_from_snapshot(
                path,
                school_id=str(source.pk),
                expected_sig=meta["signature_hex"],
                target_school=target,
            )
        # Fail-closed: NOTHING was materialized into the target.
        self.assertEqual(StudentProfile.objects.filter(school=target).count(), 0)
        self.assertEqual(AcademicYear.objects.filter(school=target).count(), 0)

    def test_tampered_blob_fails_closed_before_any_finance_write(self):
        """Fail-closed must hold for the EXPANDED 2.1 payload too — a tampered
        blob carrying teacher/invoice/payment rows writes none of them."""
        seed = self._seed_source_school_with_staff_and_finance()
        source = seed["school"]
        meta = capture_daily_snapshot(source)
        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="No Finance Recovery", slug=target_slug, subdomain=target_slug
        )
        pre_users = User.objects.count()

        path = Path(meta["primary_uri"])
        data = bytearray(path.read_bytes())
        data[-1] ^= 0xFF
        path.write_bytes(bytes(data))

        with self.assertRaises(ValueError):
            restore_from_snapshot(
                path,
                school_id=str(source.pk),
                expected_sig=meta["signature_hex"],
                target_school=target,
            )
        # Fail-closed before any write: no child rows AND no shared-parent rows.
        self.assertEqual(TeacherProfile.objects.filter(school=target).count(), 0)
        self.assertEqual(Invoice.objects.filter(school=target).count(), 0)
        self.assertEqual(Payment.objects.filter(school=target).count(), 0)
        self.assertEqual(User.objects.count(), pre_users)

    def test_wrong_key_signature_fails_closed(self):
        source = self._seed_source_school()
        meta = capture_daily_snapshot(source)
        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="Wrong Key", slug=target_slug, subdomain=target_slug
        )
        with self.assertRaises(ValueError):
            restore_from_snapshot(
                Path(meta["primary_uri"]),
                school_id=str(source.pk),
                expected_sig="00" * 32,  # not the real signature
                target_school=target,
            )
        self.assertEqual(StudentProfile.objects.filter(school=target).count(), 0)


@requires_postgres
@tag("dr_snapshot_restore")
class DrSnapshotRestoreRoundTripPostgresTests(DrSnapshotRestoreRoundTripBaseTests):
    """Same round-trip, pinned to the production PostgreSQL engine."""
