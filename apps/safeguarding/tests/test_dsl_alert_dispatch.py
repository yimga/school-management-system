"""M5 seal — a raised safeguarding concern now fires a real-time DSL alert.

Before this, ``submit_concern_for_school`` only appended the concern to a
poll-only ``dsl_inbox`` bucket, so an abuse / FGM / self-harm disclosure could
sit unseen until a DSL happened to open the queue. These tests pin that:

* an URGENT concern escalates to SMS + email + the in-app bell (severity ALERT);
* a non-urgent concern still rings the bell + email (never poll-only);
* the roster is the primary recipient pool, admin-tier members the fallback;
* a dispatch failure never unwinds the persisted concern;
* safeguarding is non-muteable — a DSL cannot silence child-protection alerts.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.communication.models import NotificationPreference
from apps.finance.models import Notification
from apps.safeguarding.services import find_concern, submit_concern_for_school
from apps.schools.models import School, SchoolMembership

User = get_user_model()

_DISPATCH = "apps.communication.dispatch.dispatch_event"


class DslAlertDispatchTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="DSL Alert School",
            slug="dsl-alert-school",
            subdomain="dsl-alert-school",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            username="dsl_reporter", password="testpass123", role=User.Role.TEACHER,
            email="reporter@example.test",
        )
        self.dsl = User.objects.create_user(
            username="dsl_lead", password="testpass123", role=User.Role.ADMIN,
            email="dsl@example.test",
        )

    def _set_roster(self, *user_ids):
        settings = dict(self.school.settings or {})
        blob = dict(settings.get("safeguarding") or {})
        blob["dsl_user_ids"] = list(user_ids)
        settings["safeguarding"] = blob
        self.school.settings = settings
        self.school.save(update_fields=["settings"])

    def test_urgent_concern_escalates_to_sms_email_inapp_alert(self):
        self._set_roster(self.dsl.pk)
        with mock.patch(_DISPATCH) as dispatch:
            submit_concern_for_school(
                school=self.school,
                reporter_user_id=self.teacher.pk,
                category_key="self_harm",  # urgent
                narrative="Student disclosed self-harm ideation to the class teacher.",
                student_id=7,
            )
        self.assertTrue(dispatch.called)
        # One call, to the configured DSL.
        recipients = {c.kwargs["recipient"].pk for c in dispatch.call_args_list}
        self.assertEqual(recipients, {self.dsl.pk})
        kwargs = dispatch.call_args_list[0].kwargs
        self.assertEqual(kwargs["channels"], [
            NotificationPreference.Channel.SMS,
            NotificationPreference.Channel.EMAIL,
            NotificationPreference.Channel.IN_APP,
        ])
        self.assertEqual(kwargs["context"]["severity"], Notification.Severity.ALERT)
        self.assertEqual(dispatch.call_args_list[0].args[0], "safeguarding.concern_raised")
        # PII stays out of the payload — only a deep link.
        self.assertIn("/safeguarding/", kwargs["context"]["link"])
        self.assertNotIn("self-harm ideation", kwargs["context"]["message"])

    def test_nonurgent_concern_still_rings_bell_and_email(self):
        self._set_roster(self.dsl.pk)
        with mock.patch(_DISPATCH) as dispatch:
            submit_concern_for_school(
                school=self.school,
                reporter_user_id=self.teacher.pk,
                category_key="neglect",  # not urgent
                narrative="Observed persistent hunger and inadequate clothing.",
                student_id=8,
            )
        kwargs = dispatch.call_args_list[0].kwargs
        self.assertEqual(kwargs["channels"], [
            NotificationPreference.Channel.EMAIL,
            NotificationPreference.Channel.IN_APP,
        ])
        self.assertEqual(kwargs["context"]["severity"], Notification.Severity.WARNING)

    def test_falls_back_to_admin_members_when_no_roster(self):
        # No dsl_user_ids configured; an ADMIN member triages.
        SchoolMembership.objects.get_or_create(
            school=self.school, user=self.dsl,
            defaults={"role": "ADMIN"},
        )
        with mock.patch(_DISPATCH) as dispatch:
            submit_concern_for_school(
                school=self.school,
                reporter_user_id=self.teacher.pk,
                category_key="physical_abuse",  # urgent
                narrative="Visible bruising consistent with physical abuse.",
                student_id=9,
            )
        recipients = {c.kwargs["recipient"].pk for c in dispatch.call_args_list}
        self.assertIn(self.dsl.pk, recipients)

    def test_dispatch_failure_never_unwinds_the_concern(self):
        self._set_roster(self.dsl.pk)
        with mock.patch(_DISPATCH, side_effect=RuntimeError("smtp down")):
            entry = submit_concern_for_school(
                school=self.school,
                reporter_user_id=self.teacher.pk,
                category_key="fgm",
                narrative="Disclosure indicating FGM risk.",
                student_id=10,
            )
        # The concern is still persisted despite the alert blowing up.
        self.school.refresh_from_db()
        self.assertIsNotNone(find_concern(self.school, entry.concern_id))


class SafeguardingNonMuteableTests(SimpleTestCase):
    def test_safeguarding_is_never_muted_even_when_listed(self):
        pref = NotificationPreference(
            muted_categories=[
                NotificationPreference.Category.SAFEGUARDING,
                NotificationPreference.Category.GRADES,
            ]
        )
        # Safeguarding is force-excluded from the mute check; grades honours it.
        self.assertFalse(pref.is_muted(NotificationPreference.Category.SAFEGUARDING))
        self.assertTrue(pref.is_muted(NotificationPreference.Category.GRADES))
