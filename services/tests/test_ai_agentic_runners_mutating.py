"""Wave Q3 (v3.95.2 — 2026-05-26) — Mutating agentic AI runner tests.

These runners are intentionally NOT auto-registered. Tests confirm:
1. Importing the module doesn't mutate any global registry.
2. Each runner refuses when params are missing or tenant scope unavailable.
3. The opt-in lookup table maps 3 known mutating actions.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from services.ai_agentic import ActionContext, ProposedAction
from services.ai_agentic_runners import _RUNNERS
from services.ai_agentic_runners_mutating import (
    OPT_IN_MUTATING_RUNNERS,
    run_mark_student_absent,
    run_schedule_parent_callback,
    run_send_parent_message,
)


def _ctx(**kw):
    defaults = dict(
        tenant_id="t1", user_id="u1", user_roles=("ADMIN",),
        confirmed_by="u1",
    )
    defaults.update(kw)
    return ActionContext(**defaults)


class GateInvariantTests(SimpleTestCase):
    """Importing this module must NOT add anything to the auto-runner table."""

    def test_module_import_does_not_register_mutating_runners(self):
        # The Wave P-B runner registry holds only read-only.
        for name in ("send_parent_message", "mark_student_absent",
                      "schedule_parent_callback", "apply_fee_waiver",
                      "purge_student_record"):
            self.assertNotIn(name, _RUNNERS)

    def test_opt_in_lookup_holds_three_runners(self):
        self.assertIn("send_parent_message", OPT_IN_MUTATING_RUNNERS)
        self.assertIn("mark_student_absent", OPT_IN_MUTATING_RUNNERS)
        self.assertIn("schedule_parent_callback", OPT_IN_MUTATING_RUNNERS)


class SendParentMessageTests(SimpleTestCase):

    def test_missing_params(self):
        result = run_send_parent_message(
            ProposedAction(action="send_parent_message", params={}),
            _ctx(),
        )
        self.assertFalse(result["ok"])
        self.assertIn("required", result["error"])

    def test_missing_tenant_school(self):
        with patch("services.ai_agentic_runners_mutating._scope_school",
                   return_value=None):
            result = run_send_parent_message(
                ProposedAction(
                    action="send_parent_message",
                    params={"parent_id": "1", "channel": "whatsapp",
                            "body": "Hello"},
                ),
                _ctx(),
            )
        self.assertFalse(result["ok"])
        self.assertIn("tenant scope", result["error"])


class SendParentMessageConsentLiveTests(TestCase):
    """Proves the WOKEN guardian-messaging runner (2026-08-08 dead-guard sweep).

    It imported a non-existent apps.people.models.Guardian and filtered a
    non-existent ``school`` field -> the send path was permanently dead. It now
    uses the real StudentGuardian link (tenant-scoped via student__school,
    active-only) AND enforces the per-channel consent flags the stub ignored.
    ``send_message`` is mocked so nothing actually leaves during the test.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.academics.models import (
            AcademicYear,
            Classroom,
            Department,
            Specialty,
        )
        from apps.people.models import StudentGuardian, StudentProfile
        from apps.schools.models import School

        User = get_user_model()
        self.school = School.objects.create(
            name="Msg S1", slug="msg-s1", subdomain="msg-s1", country_code="CM"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026-msg", start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30), is_active=True, school=self.school,
        )
        self.dept = Department.objects.create(
            name="Science", code="SCI", school=self.school
        )
        self.spec = Specialty.objects.create(
            name="General", code="GEN", department=self.dept
        )
        self.classroom = Classroom.objects.create(
            name="Form 1", code="F1", academic_year=self.year,
            department=self.dept, school=self.school,
        )
        self.student = StudentProfile.objects.create(
            first_name="Kid", last_name="One", student_code="MSG001",
            academic_year=self.year, classroom=self.classroom,
            specialty=self.spec, school=self.school,
        )
        self.user = User.objects.create_user(
            username="guardian_msg", email="gu@example.com", password="pw"
        )
        self.guardian = StudentGuardian.objects.create(
            guardian_user=self.user, student=self.student,
            email="parent@example.com", phone="+237600000000",
            whatsapp_number="+237600000000",
            receives_whatsapp=True, receives_sms=False, receives_email=False,
            is_active=True,
        )

    def _ctx(self):
        return ActionContext(
            tenant_id=str(self.school.id), user_id="u1",
            user_roles=("ADMIN",), confirmed_by="u1",
        )

    def _action(self, channel):
        return ProposedAction(
            action="send_parent_message",
            params={
                "parent_id": str(self.guardian.pk),
                "channel": channel,
                "body": "Hi",
            },
        )

    def test_consented_channel_sends(self):
        with patch("apps.communication.channel_adapter.send_message") as mock_send:
            mock_send.return_value = MagicMock(
                success=True, channel="whatsapp", adapter_id="wa-1", detail="sent"
            )
            result = run_send_parent_message(self._action("whatsapp"), self._ctx())
        self.assertTrue(result["ok"])
        self.assertTrue(mock_send.called)

    def test_opted_out_channel_never_sends(self):
        # receives_email=False -> the consent gate must block BEFORE any send.
        with patch("apps.communication.channel_adapter.send_message") as mock_send:
            result = run_send_parent_message(self._action("email"), self._ctx())
        self.assertFalse(result["ok"])
        self.assertIn("opted in", result["error"])
        mock_send.assert_not_called()

    def test_cross_tenant_guardian_not_found(self):
        from apps.schools.models import School

        other = School.objects.create(
            name="Msg S2", slug="msg-s2", subdomain="msg-s2", country_code="CM"
        )
        ctx_other = ActionContext(
            tenant_id=str(other.id), user_id="u1",
            user_roles=("ADMIN",), confirmed_by="u1",
        )
        with patch("apps.communication.channel_adapter.send_message") as mock_send:
            result = run_send_parent_message(self._action("whatsapp"), ctx_other)
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"])
        mock_send.assert_not_called()


class MarkStudentAbsentTests(SimpleTestCase):

    def test_missing_student_id(self):
        result = run_mark_student_absent(
            ProposedAction(action="mark_student_absent", params={}),
            _ctx(),
        )
        self.assertFalse(result["ok"])
        self.assertIn("required", result["error"])

    def test_invalid_date_format(self):
        result = run_mark_student_absent(
            ProposedAction(
                action="mark_student_absent",
                params={"student_id": "1", "date": "not-a-date"},
            ),
            _ctx(),
        )
        self.assertFalse(result["ok"])
        self.assertIn("invalid date", result["error"])

    def test_tenant_unavailable(self):
        with patch("services.ai_agentic_runners_mutating._scope_school",
                   return_value=None):
            result = run_mark_student_absent(
                ProposedAction(
                    action="mark_student_absent",
                    params={"student_id": "1"},
                ),
                _ctx(),
            )
        self.assertFalse(result["ok"])
        self.assertIn("tenant scope", result["error"])


class MarkStudentAbsentLiveTests(TestCase):
    """Proves the WOKEN mark-absent runner (2026-08-08 dead-guard sweep).

    It imported a non-existent apps.academics.models.AttendanceRecord, wrote a
    fictional `notes` field, and never supplied the required classroom FK -> the
    write was permanently dead behind its broad except. It now writes the real
    Attendance model (remarks, classroom from the student, school). The absence
    post_save signals fire here and are safe (parent notify is opt-in per tenant
    config, default off, via an in-app outbox — not a synchronous external send).
    """

    def setUp(self):
        from apps.academics.models import (
            AcademicYear,
            Attendance,
            Classroom,
            Department,
            Specialty,
        )
        from apps.people.models import StudentProfile
        from apps.schools.models import School

        self.Attendance = Attendance
        self.school = School.objects.create(
            name="Abs S1", slug="abs-s1", subdomain="abs-s1", country_code="CM"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026-abs", start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30), is_active=True, school=self.school,
        )
        self.dept = Department.objects.create(
            name="Science", code="SCI", school=self.school
        )
        self.spec = Specialty.objects.create(
            name="General", code="GEN", department=self.dept
        )
        self.classroom = Classroom.objects.create(
            name="Form 1", code="F1", academic_year=self.year,
            department=self.dept, school=self.school,
        )
        self.student = StudentProfile.objects.create(
            first_name="Ab", last_name="Sent", student_code="ABS001",
            academic_year=self.year, classroom=self.classroom,
            specialty=self.spec, school=self.school,
        )

    def _ctx(self):
        return ActionContext(
            tenant_id=str(self.school.id), user_id="u1",
            user_roles=("ADMIN",), confirmed_by="u1",
        )

    def test_marks_absent_with_real_attendance_fields(self):
        result = run_mark_student_absent(
            ProposedAction(
                action="mark_student_absent",
                params={"student_id": str(self.student.id), "reason": "sick"},
            ),
            self._ctx(),
        )
        self.assertTrue(result["ok"], result)
        rec = self.Attendance.objects.get(pk=result["attendance_id"])
        self.assertEqual(rec.status, "absent")
        self.assertEqual(rec.remarks, "sick")
        self.assertEqual(rec.classroom_id, self.classroom.id)
        self.assertEqual(rec.school_id, self.school.id)
        self.assertEqual(rec.student_id, self.student.id)


class ScheduleParentCallbackTests(SimpleTestCase):

    def test_missing_parent_id(self):
        result = run_schedule_parent_callback(
            ProposedAction(action="schedule_parent_callback", params={}),
            _ctx(),
        )
        self.assertFalse(result["ok"])
        self.assertIn("required", result["error"])

    def test_tenant_unavailable(self):
        with patch("services.ai_agentic_runners_mutating._scope_school",
                   return_value=None):
            result = run_schedule_parent_callback(
                ProposedAction(
                    action="schedule_parent_callback",
                    params={"parent_id": "1"},
                ),
                _ctx(),
            )
        self.assertFalse(result["ok"])
        self.assertIn("tenant scope", result["error"])
