"""SECRET_KEY stays non-waivable, and a waiver knows which host must record it.

Two properties the waiver slice depends on that nothing asserted end to end:

* The sovereign-only suite proves a fully-waived campus goes green *with* a real
  SECRET_KEY. It does not prove the other direction. If a short or placeholder
  key could ride through on the back of ten recorded waivers, "identity and
  secrets are non-waivable" would be a comment rather than a behaviour.
* ``must_record_on_box`` decides whether the operator console tells the truth.
  Go-dark reads the BOX overlay; a cloud click on a box line is a note, not
  clearance. If that flag were False for a box step the page would quietly
  invite the wrong host.
"""
from __future__ import annotations

import os
import tempfile
import uuid

from django.test import TestCase, override_settings

from apps.lifecycle import edge_onboarding
from apps.lifecycle.onboarding_waivers import WAIVABLE_ASPECTS, WAIVE_BY_KEY
from apps.schools.models import School
from apps.schools.rls_context import rls_bypass

REASON = "No uplink at this campus - sovereign-only box."


def _school():
    with rls_bypass():
        School.objects.filter(slug="waiver-secret-lab").delete()
    return School.objects.create(
        id=uuid.uuid4(),
        name="Waiver Secret Lab",
        slug="waiver-secret-lab",
        subdomain="waiver-secret-lab",
        is_active=True,
        is_approved=True,
        country_code="CM",
        settings={},
    )


class SecretKeySurvivesEveryWaiverTests(TestCase):
    """Waive the whole catalog, then break SECRET_KEY. The step must still FAIL."""

    def _fully_waived_school(self):
        school = _school()
        for row in WAIVABLE_ASPECTS:
            ok, _ = edge_onboarding.set_aspect_skip_reason(school, row.key, REASON)
            self.assertTrue(ok, row.key)
        return school

    def _box_env_verdict(self, school, secret):
        missing = os.path.join(tempfile.gettempdir(), "rmc-no-such-backup-state.json")
        with override_settings(
            RMC_BOX_BACKUP_STATE_FILE=missing,
            SECRET_KEY=secret,
            DEBUG=False,
            ALLOWED_HOSTS=["box.school.lan"],
        ):
            suite = edge_onboarding.run_verification_suite(school, include_gate=True)
        rows = {row["key"]: row for row in suite.get("steps") or []}
        return suite, rows["configure_box_env"]

    def test_a_short_secret_key_fails_even_with_every_aspect_waived(self):
        school = self._fully_waived_school()
        suite, row = self._box_env_verdict(school, "too-short-to-be-a-real-key")
        self.assertFalse(row.get("ok"), row)
        self.assertFalse(row.get("skipped"), "SECRET_KEY must never be skipped: %r" % (row,))
        self.assertIn("SECRET_KEY", row.get("detail") or "")
        self.assertFalse(suite.get("ok"), "a short SECRET_KEY cannot pass the suite")

    def test_the_placeholder_secret_key_fails_even_with_every_aspect_waived(self):
        school = self._fully_waived_school()
        # Long enough to clear the 32-char floor, so only the placeholder test
        # can catch it.
        placeholder = "change-me-to-a-long-random-string"
        self.assertGreaterEqual(len(placeholder), 32)
        suite, row = self._box_env_verdict(school, placeholder)
        self.assertFalse(row.get("ok"), row)
        self.assertFalse(suite.get("ok"))

    def test_configure_box_env_is_not_waivable_from_the_catalog(self):
        self.assertNotIn("configure_box_env", WAIVE_BY_KEY)
        self.assertNotIn("migrate_identities", WAIVE_BY_KEY)


class WaiverNamesTheHostThatMustRecordItTests(TestCase):
    """``must_record_on_box`` is what the console uses to tell an operator that a
    cloud click does not clear go-dark. Prove it per aspect, not in aggregate."""

    def test_every_waiver_flags_the_host_its_step_runs_on(self):
        school = _school()
        book = edge_onboarding.generate_runbook(school)
        steps = {row["key"]: row for row in book["steps"]}
        seen = {}
        for step in book["steps"]:
            for waive in step.get("waives") or []:
                seen[waive["key"]] = (step["key"], waive["must_record_on_box"])
        self.assertEqual(
            set(seen), {row.key for row in WAIVABLE_ASPECTS}, "a catalogued aspect has no form"
        )
        for key, (step_key, flag) in sorted(seen.items()):
            runs_on = steps[step_key]["runs_on"]
            self.assertEqual(
                flag,
                runs_on != edge_onboarding.RUNS_ON_CLOUD,
                "%s on step %s (runs_on=%s) has must_record_on_box=%s" % (key, step_key, runs_on, flag),
            )

    def test_the_uplink_aspects_must_be_recorded_on_the_box(self):
        school = _school()
        book = edge_onboarding.generate_runbook(school)
        flags = {}
        for step in book["steps"]:
            for waive in step.get("waives") or []:
                flags[waive["key"]] = waive["must_record_on_box"]
        for key in (
            "live_sync_proof",
            "verify_and_sync_gate",
            "enable_configure_sync",
            "box_backup_verified",
            "offbox_copy",
            "configure_lan_hostname",
        ):
            self.assertTrue(flags[key], "%s is evaluated on the box" % key)
        # Migration Cloud is the one line the cloud really does evaluate.
        self.assertFalse(flags["migration_cloud_apply"])

    def test_each_box_waiver_hands_the_operator_a_runnable_cli(self):
        school = _school()
        book = edge_onboarding.generate_runbook(school)
        for step in book["steps"]:
            for waive in step.get("waives") or []:
                if not waive["must_record_on_box"]:
                    continue
                cli = waive.get("cli") or ""
                self.assertIn("edge_onboarding_skip", cli, waive["key"])
                self.assertIn("--aspect %s" % waive["key"], cli)
                self.assertIn(school.slug, cli)
                self.assertNotIn("{slug}", cli)
