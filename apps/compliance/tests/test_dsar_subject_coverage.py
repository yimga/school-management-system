"""DSAR multi-subject coverage tests (apps.compliance.dsar_subjects).

Roundtrip per newly-covered subject type — teacher/staff, parent/guardian,
applicant: export returns the PII; erase anonymizes it AND a re-export shows it
gone; cross-tenant isolation (a subject in tenant A is invisible to tenant B's
DSAR); retention-hold blocks erase where a financial obligation applies.

Markers/fixtures copied from the sibling compliance DSAR test
``test_fulfill_pending_erasure.py``.
"""

from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.compliance import dsar_subjects as ds
from apps.people.models import (
    Applicant,
    StudentGuardian,
    StudentProfile,
    TeacherProfile,
)
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class _DsarSubjectBase(TestCase):
    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(
            code="DSC",
            defaults={
                "name": "DSAR Coverage Region",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name="DSAR School",
            slug="dsar-school",
            subdomain="dsar-school",
            is_active=True,
            default_region=self.region,
        )
        self.other_school = School.objects.create(
            name="DSAR Other",
            slug="dsar-other",
            subdomain="dsar-other",
            is_active=True,
            default_region=self.region,
        )
        self.operator = User.objects.create_user(
            username="dsc_op", email="op@example.com", password="pw"
        )


class StaffSubjectTests(_DsarSubjectBase):
    def setUp(self):
        super().setUp()
        self.teacher_user = User.objects.create_user(
            username="dsc_teacher",
            email="teacher@example.com",
            password="pw",
            first_name="Tina",
            last_name="Teach",
            role=User.Role.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            school=self.school,
            user=self.teacher_user,
            staff_id="STF-001",
            phone="555-7000",
            position_title="Maths Teacher",
            pay_grade="G5",
            paystub_notes="Sensitive note",
        )

    def test_resolve_subject_kind_staff(self):
        kind = ds.resolve_subject_kind(self.school.id, self.teacher_user.id)
        self.assertEqual(kind, ds.SUBJECT_STAFF)

    def test_export_returns_staff_pii(self):
        payload = ds.export_staff_data(self.school.id, self.teacher_user.id)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["subject_kind"], ds.SUBJECT_STAFF)
        self.assertEqual(payload["user"]["email"], "teacher@example.com")
        self.assertEqual(payload["teacher_profile"]["staff_id"], "STF-001")
        self.assertEqual(payload["teacher_profile"]["phone"], "555-7000")
        self.assertEqual(payload["teacher_profile"]["paystub_notes"], "Sensitive note")

    def test_erase_anonymizes_then_reexport_shows_gone(self):
        result = ds.gdpr_scrub_staff(
            self.school.id, self.teacher_user.id, requested_by_user_id=self.operator.id
        )
        self.assertTrue(result["ok"], result)
        self.teacher.refresh_from_db()
        self.teacher_user.refresh_from_db()
        # PII anonymized in place — row NOT deleted (FK integrity preserved).
        self.assertEqual(self.teacher.staff_id, "")
        self.assertEqual(self.teacher.phone, "")
        self.assertEqual(self.teacher.paystub_notes, "")
        self.assertEqual(self.teacher_user.first_name, "Deleted")
        self.assertFalse(self.teacher_user.is_active)
        self.assertNotEqual(self.teacher_user.email, "teacher@example.com")
        self.assertTrue(TeacherProfile.objects.filter(pk=self.teacher.pk).exists())
        # Re-export shows the original PII is gone.
        payload = ds.export_staff_data(self.school.id, self.teacher_user.id)
        self.assertEqual(payload["teacher_profile"]["staff_id"], "")
        self.assertNotEqual(payload["user"]["email"], "teacher@example.com")

    def test_dry_run_does_not_mutate(self):
        result = ds.gdpr_scrub_staff(self.school.id, self.teacher_user.id, dry_run=True)
        self.assertEqual(result["status"], "planned")
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.staff_id, "STF-001")

    def test_cross_tenant_isolation(self):
        # tenant B cannot export or erase tenant A's staff subject.
        self.assertIsNone(ds.export_staff_data(self.other_school.id, self.teacher_user.id))
        result = ds.gdpr_scrub_staff(self.other_school.id, self.teacher_user.id)
        self.assertFalse(result["ok"])
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.staff_id, "STF-001")  # untouched

    def test_retention_hold_blocks_erase(self):
        # An open AP invoice tied to this staff member blocks erasure.
        from apps.finance.models import ComplianceProfile, Counterparty, Invoice

        cp = Counterparty.objects.create(
            name="Tina Teach",
            counterparty_type=Counterparty.CounterpartyType.VENDOR,
            user=self.teacher_user,
        )
        profile = ComplianceProfile.objects.create(name="Payroll", country_code="US")
        Invoice.objects.create(
            school=self.school,
            profile=profile,
            counterparty=cp,
            invoice_type=Invoice.InvoiceType.AP,
            status=Invoice.Status.ISSUED,
            total_amount="100.00",
        )
        result = ds.gdpr_scrub_staff(self.school.id, self.teacher_user.id)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "retention_hold")
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.staff_id, "STF-001")  # untouched
        # force=True overrides the controller-assessed hold.
        forced = ds.gdpr_scrub_staff(self.school.id, self.teacher_user.id, force=True)
        self.assertTrue(forced["ok"], forced)


class GuardianSubjectTests(_DsarSubjectBase):
    def setUp(self):
        super().setUp()
        self.parent_user = User.objects.create_user(
            username="dsc_parent",
            email="parent@example.com",
            password="pw",
            first_name="Pat",
            last_name="Parent",
            role=User.Role.PARENT,
        )
        self.child = StudentProfile.objects.create(
            school=self.school,
            first_name="Kid",
            last_name="Parent",
            student_code="DSC-KID-1",
        )
        self.link = StudentGuardian.objects.create(
            guardian_user=self.parent_user,
            student=self.child,
            relationship=StudentGuardian.Relationship.MOTHER,
            phone="555-8000",
            email="parent.contact@example.com",
            whatsapp_number="555-8001",
            address="12 Privacy Lane",
        )

    def test_resolve_subject_kind_guardian(self):
        kind = ds.resolve_subject_kind(self.school.id, self.parent_user.id)
        self.assertEqual(kind, ds.SUBJECT_GUARDIAN)

    def test_export_returns_guardian_pii(self):
        payload = ds.export_guardian_data(self.school.id, self.parent_user.id)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["subject_kind"], ds.SUBJECT_GUARDIAN)
        link = payload["guardian_links"][0]
        self.assertEqual(link["phone"], "555-8000")
        self.assertEqual(link["email"], "parent.contact@example.com")
        self.assertEqual(link["address"], "12 Privacy Lane")

    def test_erase_anonymizes_then_reexport_shows_gone(self):
        result = ds.gdpr_scrub_guardian(
            self.school.id, self.parent_user.id, requested_by_user_id=self.operator.id
        )
        self.assertTrue(result["ok"], result)
        self.link.refresh_from_db()
        self.assertEqual(self.link.phone, "")
        self.assertEqual(self.link.email, "")
        self.assertEqual(self.link.address, "")
        self.assertFalse(self.link.receives_email)
        # link row not deleted (FK to student preserved).
        self.assertTrue(StudentGuardian.objects.filter(pk=self.link.pk).exists())
        # parent has only a guardian relationship → shared User anonymized too.
        self.parent_user.refresh_from_db()
        self.assertEqual(self.parent_user.first_name, "Deleted")
        payload = ds.export_guardian_data(self.school.id, self.parent_user.id)
        self.assertEqual(payload["guardian_links"][0]["phone"], "")

    def test_cross_tenant_isolation(self):
        self.assertIsNone(
            ds.export_guardian_data(self.other_school.id, self.parent_user.id)
        )
        result = ds.gdpr_scrub_guardian(self.other_school.id, self.parent_user.id)
        self.assertFalse(result["ok"])
        self.link.refresh_from_db()
        self.assertEqual(self.link.phone, "555-8000")  # untouched

    def test_retention_hold_blocks_erase(self):
        from apps.finance.models import ComplianceProfile, Invoice

        profile = ComplianceProfile.objects.create(name="Fees", country_code="US")
        Invoice.objects.create(
            school=self.school,
            profile=profile,
            student=self.child,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.OVERDUE,
            total_amount="500.00",
        )
        result = ds.gdpr_scrub_guardian(self.school.id, self.parent_user.id)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "retention_hold")
        self.link.refresh_from_db()
        self.assertEqual(self.link.phone, "555-8000")  # untouched


class ApplicantSubjectTests(_DsarSubjectBase):
    def setUp(self):
        super().setUp()
        self.applicant = Applicant.objects.create(
            school=self.school,
            first_name="Andy",
            last_name="Apply",
            email="andy.apply@example.com",
            lead_source="webform",
            exam_marker="WASSCE",
        )

    def test_export_returns_applicant_pii(self):
        payload = ds.export_applicant_data(self.school.id, self.applicant.id)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["subject_kind"], ds.SUBJECT_APPLICANT)
        self.assertEqual(payload["applicant"]["email"], "andy.apply@example.com")
        self.assertEqual(payload["applicant"]["first_name"], "Andy")

    def test_erase_anonymizes_then_reexport_shows_gone(self):
        result = ds.gdpr_scrub_applicant(
            self.school.id, self.applicant.id, requested_by_user_id=self.operator.id
        )
        self.assertTrue(result["ok"], result)
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.first_name, "Deleted")
        self.assertNotEqual(self.applicant.email, "andy.apply@example.com")
        self.assertEqual(self.applicant.lead_source, "gdpr_redacted")
        # row preserved (not hard-deleted).
        self.assertTrue(Applicant.objects.filter(pk=self.applicant.pk).exists())
        payload = ds.export_applicant_data(self.school.id, self.applicant.id)
        self.assertNotEqual(payload["applicant"]["email"], "andy.apply@example.com")

    def test_cross_tenant_isolation(self):
        self.assertIsNone(
            ds.export_applicant_data(self.other_school.id, self.applicant.id)
        )
        result = ds.gdpr_scrub_applicant(self.other_school.id, self.applicant.id)
        self.assertFalse(result["ok"])
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.email, "andy.apply@example.com")  # untouched


class DispatchTests(_DsarSubjectBase):
    def test_dispatch_routes_staff(self):
        teacher_user = User.objects.create_user(
            username="dsc_disp_t", email="t2@example.com", password="pw",
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(
            school=self.school, user=teacher_user, staff_id="STF-9", phone="555-9",
        )
        result = ds.scrub_user_subject(self.school.id, teacher_user.id)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["subject_kind"], ds.SUBJECT_STAFF)

    def test_dispatch_unsupported_for_unrelated_user(self):
        bare = User.objects.create_user(
            username="dsc_bare", email="bare@example.com", password="pw",
        )
        result = ds.scrub_user_subject(self.school.id, bare.id)
        self.assertFalse(result["ok"])
        self.assertIn("unsupported_subject_kind", result["error"])
