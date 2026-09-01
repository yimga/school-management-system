"""M19 -- DSAR export and erase, asserted as behaviour instead of as source text.

The DSAR row scored Unverified while carrying a test module named exactly for
it. Reading that module explains why: ``test_dsar_export_redaction.py`` is four
tests and every assertion in all four is a string search over
``inspect.getsource(...)`` --

    src = inspect.getsource(gdpr_services.export_student_data_portability)
    self.assertIn('entity="student"', src)
    ...
    helper_src = inspect.getsource(gdpr_services._redact_export_rows)
    self.assertIn('action="export"', helper_src)

It never calls the exporter. Worse, ``inspect.getsource`` includes the
DOCSTRING, and both docstrings name ``redact_record`` and ``action="export"``
in prose -- so gutting either function body while keeping its docstring leaves
all four tests GREEN. That is mutation-proven below in the report, not assumed.

This module asserts the same three claims against observed behaviour:

* the exporter actually RETURNS the subject's data (and returns None, not a
  partial payload, for a subject in another tenant);
* it actually WRITES one ``PolicyDecisionLog`` audit row per export, carrying
  the DSAR action -- a row you can count, not a string you can grep;
* erase actually ANONYMISES the stored rows, and a re-export after erase no
  longer contains the PII -- the export/erase round trip end to end.

It also covers the CSV branch, which no test reached at all, and the
``process_erase_requests`` command UNMOCKED -- the existing command test patches
``scrub_user_subject`` to a stub in four of its five cases, so it verifies the
status flip and never erases a byte.
"""

from __future__ import annotations

import uuid
from datetime import date

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.compliance.gdpr_services import (
    export_student_data_portability,
    fulfill_pending_erasure,
    gdpr_scrub_student,
)
from apps.compliance.models import EraseRequest
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School


class _DsarSubjectMixin:
    """A subject with PII in several places, so 'gone' is a real measurement."""

    FIRST = "Zainab"
    LAST = "Mballa"
    PARENT_PHONE = "699001122"
    GUARDIAN_EMAIL = "guardian.mballa@example.test"
    GUARDIAN_PHONE = "677554433"

    def _build_subject(self, *, tag=None):
        tag = tag or uuid.uuid4().hex[:8]
        school = School.objects.create(
            name=f"M19 School {tag}",
            slug=f"m19-{tag}",
            subdomain=f"m19-{tag}",
            is_active=True,
        )
        student_user = User.objects.create_user(
            username=f"m19stu_{tag}",
            email=f"{tag}.student@example.test",
            password="pw",
            role=User.Role.STUDENT,
        )
        student = StudentProfile.objects.create(
            school=school,
            user=student_user,
            first_name=self.FIRST,
            last_name=self.LAST,
            student_code=f"M19-{tag}",
            parent_phone=self.PARENT_PHONE,
        )
        guardian_user = User.objects.create_user(
            username=f"m19par_{tag}",
            email=f"{tag}.parent@example.test",
            password="pw",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=guardian_user,
            student=student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
            phone=self.GUARDIAN_PHONE,
            email=self.GUARDIAN_EMAIL,
            address="12 Rue Douala",
        )
        return school, student, student_user, guardian_user


class ExportReturnsTheSubjectsDataTests(_DsarSubjectMixin, TestCase):
    def setUp(self):
        self.school, self.student, self.student_user, _ = self._build_subject()

    def test_export_contains_the_subjects_identifiers_and_guardians(self):
        payload = export_student_data_portability(
            self.school.id, self.student.id, format="json"
        )
        self.assertIsNotNone(payload)
        self.assertEqual(payload["student_id"], self.student.id)
        self.assertEqual(payload["student"]["first_name"], self.FIRST)
        self.assertEqual(payload["student"]["last_name"], self.LAST)
        self.assertEqual(len(payload["guardians"]), 1)
        self.assertEqual(payload["guardians"][0]["email"], self.GUARDIAN_EMAIL)
        # The documented section shape is part of the Art.20 promise.
        for section in ("academics", "finance", "athletics"):
            self.assertIn(section, payload)
        for sub in ("evaluations", "attendance", "incidents"):
            self.assertIn(sub, payload["academics"])

    def test_export_writes_one_audit_row_naming_the_dsar_action(self):
        """The audit row is the accountability artefact. Counting rows is the
        only assertion that survives the helper being deleted."""
        from apps.policies.pdp import PolicyDecisionLog

        before = PolicyDecisionLog.objects.filter(action="dsar_access_export").count()
        export_student_data_portability(self.school.id, self.student.id)
        rows = PolicyDecisionLog.objects.filter(
            action="dsar_access_export", resource_id=str(self.student.id)
        )
        self.assertEqual(
            PolicyDecisionLog.objects.filter(action="dsar_access_export").count(),
            before + 1,
        )
        row = rows.order_by("-id").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.school_id, self.school.id)
        self.assertEqual(row.effect, "allow")
        self.assertEqual(row.resource_type, "people.StudentProfile")

    def test_a_second_export_writes_a_second_audit_row(self):
        from apps.policies.pdp import PolicyDecisionLog

        export_student_data_portability(self.school.id, self.student.id)
        export_student_data_portability(self.school.id, self.student.id)
        self.assertEqual(
            PolicyDecisionLog.objects.filter(
                action="dsar_access_export", resource_id=str(self.student.id)
            ).count(),
            2,
        )

    def test_a_subject_in_another_tenant_exports_nothing(self):
        other_school, _, _, _ = self._build_subject()
        self.assertIsNone(
            export_student_data_portability(other_school.id, self.student.id)
        )

    def test_an_unknown_student_exports_nothing(self):
        self.assertIsNone(
            export_student_data_portability(self.school.id, 99_999_999)
        )

    def test_csv_export_is_a_real_csv_carrying_the_subjects_data(self):
        """The ``format="csv"`` branch had no test at all -- it is a separate
        return SHAPE (filename/content/status), not the JSON payload, so a
        caller wiring it up got a KeyError with nothing to catch it."""
        import csv
        import io

        result = export_student_data_portability(
            self.school.id, self.student.id, format="csv"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["export_format"], "csv")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            result["filename"], f"student_{self.student.id}_portability.csv"
        )

        rows = list(csv.reader(io.StringIO(result["content"])))
        self.assertEqual(rows[0], ["section", "field", "value"])
        self.assertGreater(len(rows), 1)
        # Every data row carries the documented 3-column shape.
        for row in rows[1:]:
            self.assertEqual(len(row), 3)
        student_rows = {row[1]: row[2] for row in rows[1:] if row[0] == "student"}
        self.assertEqual(student_rows.get("first_name"), self.FIRST)
        self.assertEqual(student_rows.get("last_name"), self.LAST)
        self.assertIn("guardians", {row[0] for row in rows[1:]})


class EraseActuallyAnonymisesTests(_DsarSubjectMixin, TestCase):
    def setUp(self):
        self.school, self.student, self.student_user, _ = self._build_subject()

    def test_erase_anonymises_the_stored_rows(self):
        result = gdpr_scrub_student(self.school.id, self.student.id)
        self.assertTrue(result.get("ok", True), msg=str(result))

        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Deleted")
        self.assertNotEqual(self.student.last_name, self.LAST)
        self.assertEqual(self.student.parent_phone, "")
        self.assertFalse(self.student.is_active)
        self.assertIsNotNone(self.student.deleted_at)

        self.student_user.refresh_from_db()
        self.assertFalse(self.student_user.is_active)
        self.assertNotIn(self.LAST, self.student_user.email)
        self.assertFalse(self.student_user.has_usable_password())

        guardian = StudentGuardian.objects.get(student=self.student)
        self.assertEqual(guardian.email, "")
        self.assertEqual(guardian.phone, "")

    def test_erase_preserves_the_rows_it_anonymises(self):
        """Art.17 here is anonymise-in-place, NOT delete: the User FK is
        CASCADE, so a hard delete would take the audit trail with it."""
        before = StudentGuardian.objects.filter(student=self.student).count()
        self.assertEqual(before, 1)
        gdpr_scrub_student(self.school.id, self.student.id)
        self.assertTrue(StudentProfile.objects.filter(pk=self.student.pk).exists())
        self.assertEqual(
            StudentGuardian.objects.filter(student=self.student).count(), before
        )

    def test_a_dry_run_changes_nothing(self):
        gdpr_scrub_student(self.school.id, self.student.id, dry_run=True)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, self.FIRST)
        self.assertEqual(self.student.parent_phone, self.PARENT_PHONE)
        self.assertTrue(self.student.is_active)

    def test_erasing_one_subject_does_not_touch_another(self):
        other_school, other_student, _, _ = self._build_subject()
        gdpr_scrub_student(self.school.id, self.student.id)
        other_student.refresh_from_db()
        self.assertEqual(other_student.first_name, self.FIRST)
        self.assertEqual(other_student.parent_phone, self.PARENT_PHONE)
        self.assertTrue(other_student.is_active)


class ExportEraseReexportRoundTripTests(_DsarSubjectMixin, TestCase):
    """The end-to-end claim: what came out before must not come out after."""

    def setUp(self):
        self.school, self.student, self.student_user, _ = self._build_subject()

    def test_the_export_carries_every_field_the_eraser_calls_personal_data(self):
        """An internal contradiction, found by running the round trip.

        ``gdpr_scrub_student`` blanks ``parent_phone`` and ``place_of_birth``
        under Art.17 -- so this module classifies both as Personal Data. The
        Art.15/Art.20 export payload omitted both, telling the same subject
        their data did not exist while promising to erase it. A subject access
        response that is narrower than the erasure it triggers is not a subject
        access response.
        """
        self.student.place_of_birth = "Bamenda"
        self.student.save(update_fields=["place_of_birth"])

        payload = export_student_data_portability(self.school.id, self.student.id)
        self.assertIsNotNone(payload)
        core = payload["student"]
        self.assertEqual(core["parent_phone"], self.PARENT_PHONE)
        self.assertEqual(core["place_of_birth"], "Bamenda")

        gdpr_scrub_student(self.school.id, self.student.id)

        after = export_student_data_portability(self.school.id, self.student.id)
        self.assertEqual(after["student"]["parent_phone"], "")
        self.assertEqual(after["student"]["place_of_birth"], "")

    def test_pii_present_before_erase_is_absent_after(self):
        before = export_student_data_portability(self.school.id, self.student.id)
        self.assertIsNotNone(before)
        blob_before = repr(before)
        # Control: the fixture really does export the PII, so 'absent after' is
        # a change and not an empty payload both times.
        for value in (self.FIRST, self.LAST, self.PARENT_PHONE, self.GUARDIAN_EMAIL):
            self.assertIn(value, blob_before, msg=f"{value!r} never exported")

        gdpr_scrub_student(self.school.id, self.student.id)

        after = export_student_data_portability(self.school.id, self.student.id)
        self.assertIsNotNone(
            after, msg="erase destroyed the record instead of anonymising it"
        )
        blob_after = repr(after)
        for value in (self.FIRST, self.LAST, self.PARENT_PHONE, self.GUARDIAN_EMAIL):
            self.assertNotIn(
                value,
                blob_after,
                msg=f"{value!r} survived erasure and is still exportable",
            )
        # The record still exists -- erasure is not deletion.
        self.assertEqual(after["student_id"], self.student.id)
        self.assertEqual(after["student"]["first_name"], "Deleted")


class FulfilPendingErasureTests(_DsarSubjectMixin, TestCase):
    def setUp(self):
        self.school, self.student, self.student_user, _ = self._build_subject()
        self.request = EraseRequest.objects.create(
            school=self.school,
            subject_user=self.student_user,
            status=EraseRequest.Status.APPROVED,
            reason="Art.17 request",
        )

    def test_fulfilling_an_approved_request_erases_and_completes(self):
        fulfill_pending_erasure(self.request.pk)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, EraseRequest.Status.COMPLETED)
        self.assertIsNotNone(self.request.completed_at)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Deleted")

    def test_a_completed_request_is_not_fulfilled_twice(self):
        fulfill_pending_erasure(self.request.pk)
        self.request.refresh_from_db()
        first_completed_at = self.request.completed_at
        fulfill_pending_erasure(self.request.pk)
        self.request.refresh_from_db()
        self.assertEqual(self.request.completed_at, first_completed_at)


class ProcessEraseRequestsCommandUnmockedTests(_DsarSubjectMixin, TestCase):
    """The command test mocks the eraser in 4 of its 5 cases. This one does not.

    A mocked ``scrub_user_subject`` returning ``{"ok": True}`` proves the status
    flip and nothing else -- the command could be pointed at a no-op and stay
    green. Here the real eraser runs and the PII is measured afterwards.
    """

    def setUp(self):
        self.school, self.student, self.student_user, _ = self._build_subject()
        self.request = EraseRequest.objects.create(
            school=self.school,
            subject_user=self.student_user,
            status=EraseRequest.Status.APPROVED,
            reason="Art.17 request",
        )

    def test_the_command_really_erases(self):
        call_command("process_erase_requests")
        self.request.refresh_from_db()
        self.student.refresh_from_db()
        self.assertEqual(self.request.status, EraseRequest.Status.COMPLETED)
        self.assertEqual(
            self.student.first_name,
            "Deleted",
            msg="the command completed the request without erasing anything",
        )
        self.assertEqual(self.student.parent_phone, "")

    def test_a_pending_request_is_not_erased_by_the_sweep(self):
        """Only APPROVED requests may be fulfilled -- erasing on PENDING would
        action a request nobody authorised."""
        self.request.status = EraseRequest.Status.PENDING
        self.request.save(update_fields=["status"])
        call_command("process_erase_requests")
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, self.FIRST)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, EraseRequest.Status.PENDING)
