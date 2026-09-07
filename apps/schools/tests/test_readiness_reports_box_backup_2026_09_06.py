"""The every-boot check said nothing about the school's own records (2026-09-06).

Measured on the Cameroon box the night it was rebuilt onto current main. Its own
audit reported the backup honestly -- verified read-back, 9747 archive entries, a
wrong passphrase correctly refused, a restore drill four days old -- and then two
warnings that together undo all of it:

    [WARN] the backup passphrase is ON this box
    [WARN] the off-box copy is on the SAME filesystem as the box itself

``box-audit.sh`` knew. It is run by hand. ``edge_onboarding`` knew, through
``box_backup_status.verdict_from_state``. It runs once, at bring-up. The check that
runs on EVERY boot -- ``check_edge_readiness``, which the entrypoint invokes expressly
to surface edge-deployment footguns -- said nothing about the school database at all.
It checked TLS four ways, the Fernet key, mail signing and the CA. So a box whose
backup stopped in March passes every boot in June, and the first anyone hears of it is
the day the disk dies.

WHY THIS IS WARN AND NOT FAIL, and why that is asserted below rather than assumed.
``--strict`` turns any FAIL into a ``CommandError``, and the entrypoint runs
``check_edge_readiness --strict`` when ``RMC_EDGE_READINESS_STRICT=1``. A FAIL there
stops the boot. Taking a school offline because its backup is stale is strictly worse
than the stale backup, and it is the same house rule the entrypoint's other helpers
already follow. So the severity is not a presentation choice, it is the safety
property, and ``test_a_missing_backup_never_contributes_a_fail`` is the test that
holds it.

WHAT THIS FILE CANNOT DO. There is no box here and no backup container, so nothing
below takes a dump or reads one back. What it does is feed the shipped verdict the
record a real box writes, and assert the severity the boot path will act on.
"""

from __future__ import annotations

import json
import tempfile
import time
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from apps.lifecycle.box_backup_status import (
    evaluate_box_backup,
    offbox_is_independent,
    verdict_from_state,
)

#: The shape ``box-backup.sh`` actually writes, taken from the live record on the
#: Cameroon box on 2026-09-06 rather than invented -- including the string "true"
#: for the booleans, which is how a shell script writes JSON and the reason
#: ``_truthy`` exists at all.
def _record(**overrides):
    now = int(time.time())
    state = {
        "schema": 1,
        "last_attempt_at": "2026-09-06T21:59:35Z",
        "last_success_at": "2026-09-06T21:59:42Z",
        "last_success_epoch": now,
        "last_status": "ok",
        "last_file": "rmc-box-db-20260906T215935Z.dump.enc",
        "verified_at": "2026-09-06T21:59:42Z",
        "verified_file": "rmc-box-db-20260906T215935Z.dump.enc",
        "verified_toc_entries": 9747,
        "verified_full_read": "true",
        "encryption_real": "true",
        "offbox_status": "copied",
        "offbox_independent": "true",
    }
    state.update(overrides)
    return state


class OffboxAccessorTests(SimpleTestCase):
    """The accessor the readiness check reads, rather than string-matching prose."""

    def test_a_copy_on_another_filesystem_is_independent(self):
        self.assertTrue(offbox_is_independent(_record()))

    def test_a_copy_on_the_same_disk_is_not(self):
        self.assertFalse(offbox_is_independent(_record(offbox_independent="false")))

    def test_an_absent_flag_is_not_independence(self):
        """The default must be the CAUTIOUS answer.

        An older record predating the off-box feature has no such key, and reading a
        missing flag as "yes, independent" would silently clear the warning on exactly
        the boxes most likely to need it.
        """
        state = _record()
        del state["offbox_independent"]
        self.assertFalse(offbox_is_independent(state))

    def test_no_record_at_all_is_not_independence(self):
        self.assertFalse(offbox_is_independent(None))

    def test_the_verdict_still_agrees_with_the_accessor(self):
        """verdict_from_state was refactored onto this accessor; pin they agree.

        The verdict PASSES a backup that is verified but not off-box independent --
        it is a real backup, just one a dead disk takes with it -- and mentions the
        risk in its detail. That split is the behaviour the readiness wiring depends
        on, so a change to either half should fail here.
        """
        ok, detail = verdict_from_state(_record(offbox_independent="false"))
        self.assertTrue(ok, "a verified dump is still a backup")
        self.assertIn("off-box copy is NOT", detail)

        ok_independent, detail_independent = verdict_from_state(_record())
        self.assertTrue(ok_independent)
        self.assertNotIn("off-box copy is NOT", detail_independent)


class ReadinessReportsTheBackupTests(SimpleTestCase):
    """What the boot path prints, and at what severity.

    EVERY test here asserts the line EXISTS before asserting anything about its
    severity, and that is not belt-and-braces. The first draft filtered on lines
    containing "backup" and four of these five passed with the wiring removed --
    the command already emits an unrelated WARN about off-box MEDIA backup, and
    that one line satisfied the filter. Absence and innocence look identical to a
    test that only asks whether a bad line is missing.
    """

    #: The prefix the wiring emits, and nothing else in this command does. Matching
    #: on the bare word "backup" is what made the first draft vacuous.
    MARKER = "School database backup:"

    def _run(self, state):
        """Run the real command against a record on disk; return its output lines."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backup-state.json"
            if state is not None:
                path.write_text(json.dumps(state), encoding="utf-8")
            out = StringIO()
            with override_settings(RMC_BOX_BACKUP_STATE_FILE=str(path)):
                # Not --strict: an unrelated FAIL in the ambient environment would
                # raise and this file would be testing the environment, not the
                # backup wiring. Severity is asserted from the text instead.
                call_command("check_edge_readiness", stdout=out, stderr=StringIO())
            return out.getvalue().splitlines()

    def _verdict_line(self, lines):
        """The one line this feature owns. Fails loudly when the wiring is gone."""
        owned = [ln for ln in lines if self.MARKER in ln]
        self.assertEqual(
            len(owned),
            1,
            f"expected exactly one {self.MARKER!r} line, got {owned!r}",
        )
        return owned[0]

    def test_a_missing_backup_never_contributes_a_fail(self):
        """THE safety property. A FAIL here stops a school's box from booting."""
        line = self._verdict_line(self._run(None))
        self.assertNotIn(
            "FAIL",
            line,
            "the backup check must never FAIL: --strict turns a FAIL into a "
            "CommandError and the entrypoint runs it on every boot",
        )

    def test_a_missing_backup_is_still_said_out_loud(self):
        line = self._verdict_line(self._run(None))
        self.assertIn("WARN", line)
        self.assertIn("never taken a backup", line)

    def test_a_verified_backup_on_the_same_disk_warns(self):
        lines = self._run(_record(offbox_independent="false"))
        self.assertIn("OK", self._verdict_line(lines))
        warned = [ln for ln in lines if "WARN" in ln and "SAME filesystem" in ln]
        self.assertTrue(
            warned,
            "a verified backup that shares the box's disk survives none of the "
            "events a backup exists for",
        )

    def test_a_verified_independent_backup_does_not_warn(self):
        """The check must go quiet when the box is actually in good shape.

        A warning that is always on is a warning nobody reads, which is how the
        findings that matter get skimmed past. The verdict line must still be
        present and OK, or this passes for the wrong reason.
        """
        lines = self._run(_record())
        self.assertIn("OK", self._verdict_line(lines))
        noisy = [ln for ln in lines if "WARN" in ln and "SAME filesystem" in ln]
        self.assertEqual(noisy, [], "nothing to warn about on an independent copy")

    def test_an_unreadable_record_is_survived(self):
        """Readiness runs on the boot path; it may not crash on a corrupt file."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backup-state.json"
            path.write_text("{ this is not json", encoding="utf-8")
            out = StringIO()
            with override_settings(RMC_BOX_BACKUP_STATE_FILE=str(path)):
                call_command("check_edge_readiness", stdout=out, stderr=StringIO())
            lines = out.getvalue().splitlines()
        line = self._verdict_line(lines)
        self.assertIn("WARN", line)
        self.assertNotIn("FAIL", line)


class EvaluatorNeverRaisesTests(SimpleTestCase):
    """evaluate_box_backup is documented as never raising; hold it to that."""

    def test_a_path_that_does_not_exist(self):
        ok, detail = evaluate_box_backup(path=Path("/nonexistent/backup-state.json"))
        self.assertFalse(ok)
        self.assertTrue(detail)

    def test_a_directory_where_a_file_belongs(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, detail = evaluate_box_backup(path=Path(tmp))
            self.assertFalse(ok)
            self.assertTrue(detail)
