"""Wave 8 tests — digest fan-out command."""

from __future__ import annotations

import unittest.mock as mock
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.analytics.models import RiskDigestRecipient, RiskFactor
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class _DigestFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = abs(hash(cls.__name__))
        cls.region, _ = RegionConfig.objects.get_or_create(
            code=f"D8{uid % 9999}",
            defaults={
                "name": "D8 Region", "default_language": "en",
                "timezone": "UTC", "date_format": "DD/MM/YYYY",
            },
        )
        cls.school = School.objects.create(
            name=f"D8 {uid}", slug=f"d8-{uid}",
            subdomain=f"d8-{uid}", is_active=True, default_region=cls.region,
        )
        u = User.objects.create_user(
            username=f"d8_st_{uid}",
            email=f"d8_st_{uid}@example.com", password="p",
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school, user=u, first_name="Daria",
            last_name="Test", student_code=f"D8-{uid}",
        )
        RiskFactor.objects.create(
            school=cls.school, student=cls.student, score=85.0,
            reason_summary="heuristic",
        )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SendRiskDigestTests(_DigestFixture):
    def test_no_recipients_no_send(self):
        out = StringIO()
        call_command(
            "send_risk_digest",
            "--school", self.school.slug,
            stdout=out,
        )
        self.assertIn("no recipients", out.getvalue())
        self.assertEqual(len(mail.outbox), 0)

    def test_email_recipient_receives_digest(self):
        RiskDigestRecipient.objects.create(
            school=self.school,
            channel=RiskDigestRecipient.Channel.EMAIL,
            target="principal@example.com",
            label="principal",
        )
        call_command(
            "send_risk_digest",
            "--school", self.school.slug,
            stdout=StringIO(),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("principal@example.com", mail.outbox[0].to)
        self.assertIn("Daria", mail.outbox[0].body)
        self.assertIn("85.0", mail.outbox[0].body)

    def test_slack_recipient_posts_to_webhook(self):
        RiskDigestRecipient.objects.create(
            school=self.school,
            channel=RiskDigestRecipient.Channel.SLACK_WEBHOOK,
            target="https://hooks.slack.example/T/x",
            label="#success",
        )
        with mock.patch(
            "urllib.request.urlopen"
        ) as urlopen_mock:
            urlopen_mock.return_value.__enter__.return_value.status = 200
            call_command(
                "send_risk_digest",
                "--school", self.school.slug,
                stdout=StringIO(),
            )
        self.assertTrue(urlopen_mock.called)
        sent_req = urlopen_mock.call_args.args[0]
        # Slack payload contains the digest body.
        body = sent_req.data.decode("utf-8")
        self.assertIn("Daria", body)

    def test_dry_run_doesnt_send(self):
        RiskDigestRecipient.objects.create(
            school=self.school,
            channel=RiskDigestRecipient.Channel.EMAIL,
            target="principal@example.com",
        )
        out = StringIO()
        call_command(
            "send_risk_digest",
            "--school", self.school.slug,
            "--dry-run",
            stdout=out,
        )
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("[dry]", out.getvalue())

    def test_disabled_recipient_skipped(self):
        RiskDigestRecipient.objects.create(
            school=self.school,
            channel=RiskDigestRecipient.Channel.EMAIL,
            target="principal@example.com",
            enabled=False,
        )
        call_command(
            "send_risk_digest",
            "--school", self.school.slug,
            stdout=StringIO(),
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_slack_post_failure_counts_failed_not_raised(self):
        RiskDigestRecipient.objects.create(
            school=self.school,
            channel=RiskDigestRecipient.Channel.SLACK_WEBHOOK,
            target="https://hooks.slack.example/T/x",
        )
        import urllib.error
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("nope"),
        ):
            out = StringIO()
            call_command(
                "send_risk_digest",
                "--school", self.school.slug,
                stdout=out,
            )
            self.assertIn("0 sent, 1 failed", out.getvalue())


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CommunicationTemplateSubjectTests(_DigestFixture):
    def test_template_subject_used_when_present(self):
        from apps.communication.models import CommunicationTemplate

        CommunicationTemplate.objects.create(
            school=self.school,
            key="analytics.risk_digest",
            subject_template="🚨 {school} digest for {date}",
            body_template="—",
            is_active=True,
        )
        RiskDigestRecipient.objects.create(
            school=self.school,
            channel=RiskDigestRecipient.Channel.EMAIL,
            target="x@example.com",
        )
        call_command(
            "send_risk_digest",
            "--school", self.school.slug,
            stdout=StringIO(),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("🚨", mail.outbox[0].subject)
        self.assertIn(self.school.name, mail.outbox[0].subject)
