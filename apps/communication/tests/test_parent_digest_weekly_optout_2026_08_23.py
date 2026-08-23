"""The weekly-summary checkbox a parent actually ticks now controls the digest.

``accounts:notification_preferences`` is the only digest control on the platform:
it writes ``siteconfig.UserPreference.receive_weekly_summary`` ("Send me a weekly
summary on Friday afternoon."). ``send_parent_digests`` read only
``communication.NotificationPreference.digest_cadence`` — a model NOTHING writes
— so the checkbox was written by the user and read by no sender, and a parent who
unticked it kept receiving the weekly digest.

Each test asserts the send path was REACHED (a ticked/absent preference does
send) before asserting the opt-out suppresses it, so "no mail" can never pass for
the wrong reason — an unreachable guardian, a factless digest, or a dry run.
"""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.communication.models import Message
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School
from apps.siteconfig.models_tooling import UserPreference

User = get_user_model()

_SEND_EMAIL = "apps.communication.notification_service.send_email"


class ParentDigestWeeklySummaryOptOutTests(TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="Digest School", slug=f"digest-{tag}", subdomain=f"digest-{tag}",
        )
        self.parent = User.objects.create_user(
            username=f"digest-parent-{tag}",
            email=f"digest-parent-{tag}@t.test",
            password="Test1234",
            role=User.Role.PARENT,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="N",
            student_code=f"D-{tag}",
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent,
            student=self.student,
            email=self.parent.email,
            receives_email=True,
            is_active=True,
        )
        # One real fact, or the guardian is skipped as "no signal" and every
        # assertion below would pass against fully broken code.
        Message.objects.create(
            sender=self.parent,
            recipient=self.parent,
            school=self.school,
            subject="Fee reminder",
            body="Balance outstanding.",
            is_read=False,
        )

    def _run(self, cadence="weekly"):
        with mock.patch(_SEND_EMAIL, return_value=True) as send_email:
            call_command(
                "send_parent_digests", cadence=cadence, apply=True, school=self.school.pk,
            )
        return send_email

    def test_no_preference_row_still_receives_the_weekly_digest(self):
        """Anti-vacuous guard: the harness genuinely reaches the send."""
        send_email = self._run()
        self.assertTrue(send_email.called)
        self.assertEqual(
            send_email.call_args.kwargs["to_addresses"], [self.parent.email]
        )

    def test_ticked_weekly_summary_receives_the_weekly_digest(self):
        UserPreference.objects.update_or_create(
            user=self.parent, defaults={"receive_weekly_summary": True},
        )
        self.assertTrue(self._run().called)

    def test_unticking_the_weekly_summary_suppresses_the_weekly_digest(self):
        UserPreference.objects.update_or_create(
            user=self.parent, defaults={"receive_weekly_summary": False},
        )
        self.assertFalse(self._run().called)

    def test_opting_out_of_the_weekly_summary_does_not_mute_a_daily_opt_in(self):
        """The checkbox is about the WEEKLY digest only.

        A guardian who explicitly holds ``digest_cadence=daily`` has chosen a
        different digest; unticking the weekly summary must not silence it.
        """
        from apps.communication.models import NotificationPreference

        UserPreference.objects.update_or_create(
            user=self.parent, defaults={"receive_weekly_summary": False},
        )
        NotificationPreference.objects.create(
            user=self.parent,
            digest_cadence=NotificationPreference.Cadence.DAILY,
        )
        self.assertTrue(self._run(cadence="daily").called)
        self.assertFalse(self._run(cadence="weekly").called)
