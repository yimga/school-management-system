"""M4 seal — approving + sending an AI kudos narrative now reaches the parent.

Before this, ``mark_narrative_sent`` only flipped the row's status to SENT; the
guardian received nothing and no parent-facing surface existed. These tests pin
that it now dispatches the message to the student's guardians through the shared
notification rail before recording it as sent — and that delivery is best-effort
(a transport failure, or a student with no guardians, never strands the row).
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.communication.models import NarrativeFeedback
from apps.communication.narrative_feedback import mark_narrative_sent
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School

User = get_user_model()

_DISPATCH = "apps.communication.dispatch.dispatch_event"


class NarrativeDispatchTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Kudos School", slug="kudos-school", subdomain="kudos-school",
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="N", student_code="K-1",
        )
        self.parent = User.objects.create_user(
            username="kudos_parent", password="pass123", role=User.Role.PARENT,
            email="parent@example.test",
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent, student=self.student, phone="+237600000001",
        )
        self.narrative = NarrativeFeedback.objects.create(
            school=self.school, student=self.student,
            message_text="Ada showed wonderful kindness today.",
            status=NarrativeFeedback.Status.APPROVED,
        )

    def test_mark_sent_dispatches_to_guardian_then_flips_status(self):
        with mock.patch(_DISPATCH) as dispatch:
            mark_narrative_sent(self.narrative)
        self.assertTrue(dispatch.called)
        kwargs = dispatch.call_args_list[0].kwargs
        self.assertEqual(kwargs["recipient"].pk, self.parent.pk)
        self.assertEqual(
            kwargs["context"]["message"], "Ada showed wonderful kindness today.",
        )
        self.assertEqual(dispatch.call_args_list[0].args[0], "achievement.kudos")
        self.narrative.refresh_from_db()
        self.assertEqual(self.narrative.status, NarrativeFeedback.Status.SENT)
        self.assertIsNotNone(self.narrative.sent_at)

    def test_dispatch_failure_still_marks_sent(self):
        with mock.patch(_DISPATCH, side_effect=RuntimeError("smtp down")):
            mark_narrative_sent(self.narrative)
        self.narrative.refresh_from_db()
        self.assertEqual(self.narrative.status, NarrativeFeedback.Status.SENT)

    def test_no_guardians_still_marks_sent_without_dispatch(self):
        orphan = StudentProfile.objects.create(
            school=self.school, first_name="No", last_name="Guardian",
            student_code="K-2",
        )
        lonely = NarrativeFeedback.objects.create(
            school=self.school, student=orphan, message_text="Great effort!",
            status=NarrativeFeedback.Status.APPROVED,
        )
        with mock.patch(_DISPATCH) as dispatch:
            mark_narrative_sent(lonely)
        self.assertFalse(dispatch.called)
        lonely.refresh_from_db()
        self.assertEqual(lonely.status, NarrativeFeedback.Status.SENT)
