"""W24 increment 1 — structured immunization records + missing-vaccine sweep.

Must-fire tests. Every case below fails BEFORE this increment because the
models (``ImmunizationRecord`` / ``VaccineRequirement``), the compute module
(``apps.schoolops.immunization``), the sweep task
(``check_missing_immunizations_task``), and the management command
(``check_missing_immunizations``) do not exist yet — so the imports / command
lookup raise before any assertion runs.

Runs under the SQLite RLS test harness (``USE_DJANGO_TENANTS`` is engine-derived
and False for SQLite, so the per-school ``_run_with_tenant_context`` wrapper
resolves to a no-op ``rls_school`` and the sweep executes plainly).
"""

from __future__ import annotations

import uuid

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.finance.models import Notification
from apps.people.models import StudentGuardian, StudentProfile
from apps.schoolops.immunization import compute_missing_immunizations
from apps.schoolops.models import ImmunizationRecord, VaccineRequirement
from apps.schoolops.tasks import check_missing_immunizations_task
from apps.schools.models import School

_ALERT_TITLE = "Immunization records incomplete"


class _ImmunizationBase(TestCase):
    databases = {"default"}

    def _make_school(self):
        uid = uuid.uuid4().hex[:8]
        return School.objects.create(
            name=f"IMM {uid}",
            slug=f"imm-{uid}",
            subdomain=f"imm{uid}",
            is_active=True,
        )

    def _make_student(self, school, first="Ada", last="Lovelace"):
        uid = uuid.uuid4().hex[:8]
        return StudentProfile.objects.create(
            first_name=first,
            last_name=last,
            date_of_birth="2015-01-01",
            student_code=f"S{uid}",
            school=school,
            is_active=True,
        )

    def _make_guardian(self, student):
        uid = uuid.uuid4().hex[:8]
        guardian = User.objects.create_user(
            username=f"guardian-{uid}",
            password="pass12345",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=guardian, student=student, receives_sms=False
        )
        return guardian

    def _guardian_alert_count(self, guardian):
        return Notification.objects.filter(
            recipient=guardian, title=_ALERT_TITLE
        ).count()


class ImmunizationModelTests(_ImmunizationBase):
    """Fail-before: the two models are unmodeled today (ImportError)."""

    def test_models_persist_fields(self):
        school = self._make_school()
        student = self._make_student(school)
        req = VaccineRequirement.objects.create(
            school=school, vaccine="MMR", doses_required=2
        )
        rec = ImmunizationRecord.objects.create(
            school=school,
            student=student,
            vaccine="mmr",
            dose_number=1,
            date_administered="2020-03-03",
        )
        req.refresh_from_db()
        rec.refresh_from_db()

        self.assertEqual(req.vaccine, "MMR")
        self.assertEqual(req.doses_required, 2)
        self.assertTrue(req.is_active)
        # save() normalizes the record code too (strip + upper).
        self.assertEqual(rec.vaccine, "MMR")
        self.assertEqual(rec.dose_number, 1)
        self.assertEqual(rec.student_id, student.pk)
        self.assertEqual(rec.school_id, school.pk)


class ComputeMissingImmunizationsTests(_ImmunizationBase):
    """Fail-before: ``apps.schoolops.immunization`` does not exist (ImportError)."""

    def test_no_requirements_configured_is_compliant(self):
        # (a) no requirements -> requirements_configured False, is_compliant True.
        school = self._make_school()
        student = self._make_student(school)
        result = compute_missing_immunizations(student, school)
        self.assertFalse(result["requirements_configured"])
        self.assertTrue(result["is_compliant"])
        self.assertEqual(result["missing"], [])

    def test_underdosed_student_is_missing(self):
        # (b) doses_required=2, 1 dose on record -> missing lists it, not compliant.
        school = self._make_school()
        student = self._make_student(school)
        VaccineRequirement.objects.create(
            school=school, vaccine="MMR", doses_required=2
        )
        ImmunizationRecord.objects.create(
            school=school, student=student, vaccine="MMR", dose_number=1
        )
        result = compute_missing_immunizations(student, school)
        self.assertTrue(result["requirements_configured"])
        self.assertFalse(result["is_compliant"])
        self.assertEqual(len(result["missing"]), 1)
        entry = result["missing"][0]
        self.assertEqual(entry["vaccine"], "MMR")
        self.assertEqual(entry["doses_required"], 2)
        self.assertEqual(entry["doses_on_record"], 1)

    def test_fully_dosed_student_is_compliant(self):
        # (c) 2 doses on record for a 2-dose requirement -> compliant.
        school = self._make_school()
        student = self._make_student(school)
        VaccineRequirement.objects.create(
            school=school, vaccine="MMR", doses_required=2
        )
        ImmunizationRecord.objects.create(
            school=school, student=student, vaccine="MMR", dose_number=1
        )
        ImmunizationRecord.objects.create(
            school=school, student=student, vaccine="MMR", dose_number=2
        )
        result = compute_missing_immunizations(student, school)
        self.assertTrue(result["is_compliant"])
        self.assertEqual(result["missing"], [])

    def test_exemption_treated_as_satisfied(self):
        # (d) an exemption record satisfies the requirement (exempt, not missing).
        school = self._make_school()
        student = self._make_student(school)
        VaccineRequirement.objects.create(
            school=school, vaccine="MMR", doses_required=2
        )
        ImmunizationRecord.objects.create(
            school=school,
            student=student,
            vaccine="MMR",
            exemption_type="medical",
            exemption_reason="documented allergy",
        )
        result = compute_missing_immunizations(student, school)
        self.assertTrue(result["is_compliant"])
        self.assertEqual(result["missing"], [])
        self.assertEqual([e["vaccine"] for e in result["exempt"]], ["MMR"])

    def test_vaccine_code_normalization_matches(self):
        # (e) requirement "  mmr " matches record "MmR" via read-time normalize.
        # bulk_create bypasses save()-normalization, so the raw casing/whitespace
        # lands in the DB — proving compute() normalizes at READ time, not only
        # via the model save() hook.
        school = self._make_school()
        student = self._make_student(school)
        VaccineRequirement.objects.bulk_create(
            [VaccineRequirement(school=school, vaccine="  mmr ", doses_required=1)]
        )
        ImmunizationRecord.objects.bulk_create(
            [ImmunizationRecord(school=school, student=student, vaccine="MmR")]
        )
        # Confirm the stored values really are un-normalized.
        self.assertEqual(
            VaccineRequirement.objects.get(school=school).vaccine, "  mmr "
        )
        result = compute_missing_immunizations(student, school)
        self.assertTrue(result["is_compliant"], result)
        self.assertEqual(result["missing"], [])


class MissingImmunizationSweepTests(_ImmunizationBase):
    """Fail-before: the sweep task + management command do not exist."""

    def test_noncompliant_student_raises_guardian_alert(self):
        school = self._make_school()
        student = self._make_student(school)
        guardian = self._make_guardian(student)
        VaccineRequirement.objects.create(
            school=school, vaccine="MMR", doses_required=2
        )
        ImmunizationRecord.objects.create(
            school=school, student=student, vaccine="MMR", dose_number=1
        )

        self.assertEqual(self._guardian_alert_count(guardian), 0)
        call_command("check_missing_immunizations", school=school.slug)
        self.assertEqual(self._guardian_alert_count(guardian), 1)

        # PII-safe: the alert body names the first name only — never a vaccine
        # or dose count.
        notif = Notification.objects.get(recipient=guardian, title=_ALERT_TITLE)
        self.assertEqual(notif.severity, Notification.Severity.WARNING)
        self.assertEqual(notif.school_id, school.pk)
        self.assertNotIn("MMR", notif.message)

    def test_compliant_student_raises_no_alert(self):
        school = self._make_school()
        student = self._make_student(school)
        guardian = self._make_guardian(student)
        VaccineRequirement.objects.create(
            school=school, vaccine="MMR", doses_required=1
        )
        ImmunizationRecord.objects.create(
            school=school, student=student, vaccine="MMR", dose_number=1
        )

        call_command("check_missing_immunizations", school=school.slug)
        self.assertEqual(self._guardian_alert_count(guardian), 0)

    def test_school_with_no_requirements_raises_no_alert(self):
        # Behaviour-preserving: zero VaccineRequirement rows -> nothing enforced.
        school = self._make_school()
        student = self._make_student(school)
        guardian = self._make_guardian(student)

        call_command("check_missing_immunizations", school=school.slug)
        self.assertEqual(self._guardian_alert_count(guardian), 0)

    def test_task_direct_call_returns_summary_and_alerts(self):
        school = self._make_school()
        student = self._make_student(school)
        guardian = self._make_guardian(student)
        VaccineRequirement.objects.create(
            school=school, vaccine="POLIO", doses_required=3
        )
        ImmunizationRecord.objects.create(
            school=school, student=student, vaccine="POLIO", dose_number=1
        )

        summary = check_missing_immunizations_task(school_id=str(school.id))
        self.assertEqual(summary.get("students_checked"), 1)
        self.assertEqual(summary.get("students_noncompliant"), 1)
        self.assertGreaterEqual(summary.get("alerts_raised", 0), 1)
        self.assertEqual(self._guardian_alert_count(guardian), 1)

        # Idempotent: a second sweep does not pile up a second unread alert
        # (notify_unread dedups on (recipient, title)).
        check_missing_immunizations_task(school_id=str(school.id))
        self.assertEqual(self._guardian_alert_count(guardian), 1)
