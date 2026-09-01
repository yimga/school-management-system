"""Go-dark cannot pass without a verified box backup.

Until 2026-08-31 the runbook walked a school to go-dark without once asking whether
the box had a dump of the school's records that had been READ BACK. Delta sync
carries a handful of Class-A entities; the fee ledger, marks, attendance and
uploaded documents live on one disk. A dead SSD was total loss, and the checklist
that certified the school ready to go dark never mentioned it.

The backup SERVICE and C2 audit already exist (``box-backup.sh`` / ``box-audit.sh``).
This file pins the runbook STEP that reads their record so go-dark cannot skip it.

WHAT THIS STEP MUST NOT DO:

* it must not take a dump or restore one -- Django is not the backup container;
* it must not pass on a listed-but-unread archive, a stale dump, or a read-back of
  yesterday's file while today's dump sits unverified;
* it must not fake the file check on a manager GET (``cloud_preview=False``);
* it must not raise on a hostile school (audit check D).
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from apps.lifecycle import box_backup_status, edge_onboarding
from apps.lifecycle.edge_onboarding import (
    EDGE_ONBOARDING_STEP_KEYS,
    EDGE_ONBOARDING_STEPS,
)
from apps.schools.models import School
from apps.schools.rls_context import rls_bypass

STEP_KEY = "box_backup_verified"


def _valid_state(**overrides):
    dump = "rmc-box-db-20260831T020000Z.dump.enc"
    payload = {
        "schema": 1,
        "last_file": dump,
        "last_success_epoch": int(time.time()),
        "verified_at": "2026-08-31T02:01:00Z",
        "verified_file": dump,
        "verified_full_read": "true",
        "verified_toc_entries": 40,
        "offbox_independent": "true",
    }
    payload.update(overrides)
    return payload


def _write_state(payload):
    handle, path = tempfile.mkstemp(suffix=".json")
    os.close(handle)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


class TheStepExistsAndSitsInTheRightPlaceTests(SimpleTestCase):
    def _step(self):
        return {s.key: s for s in EDGE_ONBOARDING_STEPS}[STEP_KEY]

    def test_the_runbook_has_a_verified_backup_step_at_all(self):
        self.assertIn(STEP_KEY, EDGE_ONBOARDING_STEP_KEYS)

    def test_it_sits_after_live_proof_and_before_go_dark(self):
        order = list(EDGE_ONBOARDING_STEP_KEYS)
        self.assertLess(order.index("live_sync_proof"), order.index(STEP_KEY))
        self.assertLess(order.index(STEP_KEY), order.index("go_dark_checklist"))

    def test_it_does_not_heal_itself(self):
        # Only the backup container dumps. A Django heal that shelled out to
        # pg_dump would be the wizard taking a backup it cannot restore.
        self.assertIsNone(self._step().self_heal)

    def test_a_cloud_get_cannot_fake_the_file_check(self):
        self.assertFalse(self._step().cloud_preview)

    def test_it_runs_on_the_box_and_reads_box_state(self):
        step = self._step()
        self.assertEqual(step.runs_on, edge_onboarding.RUNS_ON_BOX)
        self.assertEqual(step.evidence, edge_onboarding.EVIDENCE_BOX_SETTINGS)

    def test_the_command_names_the_backup_script_and_the_school(self):
        template = self._step().command_template
        self.assertIn("{slug}", template)
        self.assertIn("box-backup.sh once", template)
        self.assertIn("box-backup.sh status", template)

    def test_it_points_at_the_backup_runbook(self):
        self.assertEqual(self._step().help_doc, "docs/EDGE_BOX_BACKUP_RUNBOOK.md")

    def test_the_workaround_forbids_restoring_into_the_live_database(self):
        self.assertIn("box-restore.sh", self._step().workaround)


class TheRecordReaderMatchesC2Tests(SimpleTestCase):
    def test_missing_record_fails(self):
        ok, detail = box_backup_status.verdict_from_state(None)
        self.assertFalse(ok)
        self.assertIn("never taken a backup", detail)

    def test_unverified_dump_fails(self):
        ok, detail = box_backup_status.verdict_from_state(_valid_state(verified_at=""))
        self.assertFalse(ok)
        self.assertIn("read back", detail)

    def test_mismatched_verified_file_fails(self):
        ok, detail = box_backup_status.verdict_from_state(
            _valid_state(verified_file="other.dump.enc")
        )
        self.assertFalse(ok)
        self.assertIn("not the newest dump", detail)

    def test_listed_but_not_read_end_to_end_fails(self):
        ok, detail = box_backup_status.verdict_from_state(
            _valid_state(verified_full_read="false")
        )
        self.assertFalse(ok)
        self.assertIn("END TO END", detail)

    def test_stale_dump_fails(self):
        three_days = 3 * 24 * 60 * 60
        ok, detail = box_backup_status.verdict_from_state(
            _valid_state(last_success_epoch=int(time.time()) - three_days)
        )
        self.assertFalse(ok)
        self.assertIn("more than two days", detail)

    def test_a_fresh_full_read_passes(self):
        ok, detail = box_backup_status.verdict_from_state(_valid_state())
        self.assertTrue(ok, detail)
        self.assertIn("read back in full", detail)


class HostileInputNeverRaisesTests(SimpleTestCase):
    def test_validate_on_a_school_with_no_fields_returns_a_verdict(self):
        broken = SimpleNamespace()
        try:
            ok, detail = edge_onboarding._validate_box_backup_verified(broken)
        except Exception as extra:  # noqa: BLE001
            self.fail("validate raised %r" % extra)
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(detail, str)
        self.assertTrue(detail)


class MissingRecordAndSkipTests(TestCase):
    def _school(self):
        with rls_bypass():
            School.objects.filter(slug="backup-step-school").delete()
        return School.objects.create(
            name="Backup Step School",
            slug="backup-step-school",
            subdomain="backup-step-school",
            is_active=True,
            is_approved=True,
            country_code="CM",
            settings={},
        )

    def test_a_missing_record_fails_the_step(self):
        missing = os.path.join(tempfile.gettempdir(), "rmc-no-such-backup-state.json")
        with override_settings(RMC_BOX_BACKUP_STATE_FILE=missing):
            ok, detail = edge_onboarding._validate_box_backup_verified(self._school())
        self.assertFalse(ok)
        self.assertIn("never taken a backup", detail)

    def test_a_short_skip_does_not_pass(self):
        school = self._school()
        recorded, _ = edge_onboarding.set_box_backup_skip_reason(school, "too-short")
        self.assertFalse(recorded)
        missing = os.path.join(tempfile.gettempdir(), "rmc-no-such-backup-state.json")
        with override_settings(RMC_BOX_BACKUP_STATE_FILE=missing):
            ok, _detail = edge_onboarding._validate_box_backup_verified(school)
        self.assertFalse(ok)

    def test_a_verified_record_passes_the_step(self):
        path = _write_state(_valid_state())
        try:
            with override_settings(RMC_BOX_BACKUP_STATE_FILE=path):
                ok, detail = edge_onboarding._validate_box_backup_verified(self._school())
            self.assertTrue(ok, detail)
            self.assertIn("read back in full", detail)
        finally:
            os.unlink(path)

    def test_a_twelve_char_skip_passes_without_a_dump(self):
        school = self._school()
        recorded, _ = edge_onboarding.set_box_backup_skip_reason(
            school, "Lab box -- USB dump already taken by hand."
        )
        self.assertTrue(recorded)
        missing = os.path.join(tempfile.gettempdir(), "rmc-no-such-backup-state.json")
        with override_settings(RMC_BOX_BACKUP_STATE_FILE=missing):
            ok, detail = edge_onboarding._validate_box_backup_verified(school)
        self.assertTrue(ok, detail)
        self.assertIn("skipped by operator", detail)

    def test_go_dark_stays_blocked_until_backup_clears(self):
        school = self._school()
        missing = os.path.join(tempfile.gettempdir(), "rmc-no-such-backup-state.json")
        with mock.patch.object(
            edge_onboarding, "_validate_live_sync_proof", return_value=(True, "ok")
        ), mock.patch.object(
            edge_onboarding, "_validate_seed_operational_data", return_value=(True, "ok")
        ), mock.patch.object(
            edge_onboarding,
            "_validate_conversion_first_action",
            return_value=(True, "unlocked"),
        ), mock.patch.object(
            edge_onboarding,
            "_latest_sync_run",
            return_value=SimpleNamespace(ok=True, conflicts=0),
        ), override_settings(RMC_BOX_BACKUP_STATE_FILE=missing):
            ok, detail = edge_onboarding._validate_go_dark_checklist(school)
        self.assertFalse(ok)
        self.assertIn("backup=missing", detail)
