"""Must-fire guard for the risk-digest recipient-before-narration ordering.

This is the load-bearing safety property that made analytics.send_risk_digest_all
safe to wake (2026-08-05): _generate_digest runs an LLM gateway invoke, so it
must NOT run for schools that have no enabled RiskDigestRecipient — otherwise the
nightly fan-out burns per-school LLM spend platform-wide for output nobody
receives. If the check is ever moved back after narration, these tests go red.
"""

from __future__ import annotations

from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.siteconfig.models import RegionConfig
from apps.schools.models import School
from apps.analytics.models_digest import RiskDigestRecipient
from apps.analytics.management.commands.send_risk_digest import Command


class RiskDigestRecipientGateTests(TestCase):
    def setUp(self):
        uid = id(self)
        self.region, _ = RegionConfig.objects.get_or_create(
            code="RDG",
            defaults={
                "name": "Risk Digest Region",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name=f"RD {uid}",
            slug=f"rd-{uid}",
            subdomain=f"rd-{uid}",
            is_active=True,
            default_region=self.region,
        )

    @mock.patch.object(Command, "_generate_digest", return_value="DIGEST BODY")
    def test_no_recipient_skips_llm_narration(self, gen):
        # MUST FIRE: zero enabled recipients -> the LLM narration never runs.
        call_command("send_risk_digest", school=self.school.slug, dry_run=True)
        gen.assert_not_called()

    @mock.patch.object(Command, "_generate_digest", return_value="DIGEST BODY")
    def test_disabled_recipient_skips_llm_narration(self, gen):
        RiskDigestRecipient.objects.create(
            school=self.school,
            channel=RiskDigestRecipient.Channel.EMAIL,
            target="head@example.com",
            enabled=False,
        )
        call_command("send_risk_digest", school=self.school.slug, dry_run=True)
        gen.assert_not_called()

    @mock.patch.object(Command, "_generate_digest", return_value="DIGEST BODY")
    def test_enabled_recipient_runs_narration(self, gen):
        RiskDigestRecipient.objects.create(
            school=self.school,
            channel=RiskDigestRecipient.Channel.EMAIL,
            target="head@example.com",
            enabled=True,
        )
        call_command("send_risk_digest", school=self.school.slug, dry_run=True)
        gen.assert_called_once()
