"""The readiness report answers "are our blueprints at 100?" for real tenants.

Readiness is per-tenant, so the catalog-level ceiling test cannot answer it for
an actual school. This command is how an operator asks, and how they settle the
one shortfall that does not need a PSP.
"""
from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.finance.fee_collection_posture import (
    POSTURE_MANUAL,
    get_recorded_posture,
    record_collection_posture,
)
from apps.schools.models import School

_NO_RAILS = {"stripe_connect": False, "verified_corridors": []}


class BlueprintReadinessReportCommandTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Report School",
            slug="report-school",
            subdomain="report-school",
            is_active=True,
            settings={},
        )

    def _run(self, *args) -> str:
        out = StringIO()
        with patch(
            "apps.finance.fee_collection_posture._live_rail_evidence",
            return_value=dict(_NO_RAILS),
        ):
            call_command(
                "blueprint_readiness_report", "--school", self.school.slug, *args, stdout=out
            )
        return out.getvalue()

    def test_reports_the_payment_shortfall_before_it_is_settled(self):
        output = self._run()

        self.assertIn("Live payment onboarding", output)
        self.assertIn("below 100", output)
        self.assertEqual(get_recorded_posture(self.school), {})

    def test_recording_manual_collection_takes_every_blueprint_to_100(self):
        output = self._run("--record-manual-collection", "--note", "Cash at bursary")

        self.school.refresh_from_db()
        self.assertEqual(get_recorded_posture(self.school)["mode"], POSTURE_MANUAL)
        self.assertIn("every tenant-safe blueprint is at 100", output)
        self.assertNotIn("below 100", output)

    def test_report_is_read_only_without_the_flag(self):
        self._run()

        self.school.refresh_from_db()
        self.assertEqual(self.school.settings.get("fee_collection_posture"), None)

    def test_existing_posture_is_not_silently_overwritten(self):
        record_collection_posture(self.school, mode=POSTURE_MANUAL, note="original")
        self.school.refresh_from_db()

        output = self._run("--record-manual-collection", "--note", "replacement")

        self.school.refresh_from_db()
        self.assertIn("already recorded", output)
        self.assertEqual(get_recorded_posture(self.school)["note"], "original")

    def test_live_rail_school_is_skipped_as_nothing_to_settle(self):
        out = StringIO()
        with patch(
            "apps.finance.fee_collection_posture._live_rail_evidence",
            return_value={"stripe_connect": True, "verified_corridors": []},
        ):
            call_command(
                "blueprint_readiness_report",
                "--school",
                self.school.slug,
                "--record-manual-collection",
                stdout=out,
            )

        self.school.refresh_from_db()
        self.assertIn("nothing to settle", out.getvalue())
        self.assertEqual(get_recorded_posture(self.school), {})

    def test_unknown_school_is_an_error_not_a_silent_pass(self):
        with self.assertRaises(CommandError):
            call_command("blueprint_readiness_report", "--school", "no-such-school")
