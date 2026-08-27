"""A bootstrap that "changes nothing" was overwriting the one unregenerable artefact.

`edge_bootstrap` knows when a CA already has a verified backup -- `already` is computed
at the top of `_backup` from the trust-anchor record. But the check that acted on it sat
INSIDE the `--no-backup` branch, and `--no-backup` is only passed when no passphrase is
present. A passphrase is present exactly when an operator wants a backup, so the guard
was unreachable in the one case it existed for.

Measured on the Gilead box on 2026-08-27. Same CA, same fingerprint, two runs:

    passphrase unset -> "Backup skipped; this CA already has a verified one (13:04:32)"
    passphrase set   -> "Exported to /tmp/box-ca-bundle.p12 (4394 bytes, encrypted)"

The second run re-encrypted the bundle under a new passphrase and overwrote
/srv/box-ca-bundle.p12. The copy the operator had already moved off the box still
opened with the OLD passphrase, so the stored copy and the on-box copy quietly stopped
matching -- a difference that surfaces during a restore, if ever.

Nothing was lost either time: the CA itself is untouched (`edge_bootstrap` refuses to
mint a second one) and both bundles carry the same key. The damage is that "which
passphrase opens this file" stopped having one answer.
"""

from __future__ import annotations

import os
import tempfile
from io import StringIO
from unittest import mock

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.schools.management.commands.edge_bootstrap import Command

FINGERPRINT = "F5:7D:37:13:77:53:40:C1:FB:56:17:82:27:D4:0C:6B"
EXPORTED_AT = "2026-08-27T13:04:32.909262+00:00"
LOAD_STATE = (
    "apps.schools.management.commands.edge_bootstrap.edge_trust_state.load_state"
)


class _Facts:
    fingerprint = FINGERPRINT


def _verified(fingerprint=FINGERPRINT):
    return {
        "active": {
            "fingerprint": fingerprint,
            "export_verified_at": EXPORTED_AT,
            "exported_at": EXPORTED_AT,
        }
    }


class TheBackupMustNotSilentlyReplaceItselfTests(SimpleTestCase):
    def setUp(self):
        # The export path is only reached when the skip does NOT happen, which is
        # exactly what several of these assert on.
        self.dest = os.path.join(tempfile.mkdtemp(prefix="ca-backup-"), "bundle.p12")
        self._saved = os.environ.pop("RMC_EDGE_TLS_CA_PASSPHRASE", None)
        if self._saved is not None:
            self.addCleanup(
                os.environ.__setitem__, "RMC_EDGE_TLS_CA_PASSPHRASE", self._saved
            )

    def _run(self, state, **over):
        options = {"no_backup": False, "re_export_backup": False, "backup_to": self.dest}
        options.update(over)
        out = StringIO()
        cmd = Command(stdout=out, stderr=StringIO())
        # handle() builds these, and _backup is being driven directly. Without
        # them _ok() raises AttributeError and the test fails for its own reason
        # rather than the product's -- which is exactly what it did first time.
        cmd.report = {"ok": [], "warn": [], "fail": [], "actions": []}
        cmd.as_json = False
        with mock.patch(LOAD_STATE, return_value=state):
            cmd._backup(_Facts(), options, False)
        return out.getvalue()

    def test_a_ca_with_a_verified_backup_is_left_alone(self):
        out = self._run(_verified())
        self.assertIn("Backup skipped", out)
        self.assertIn(EXPORTED_AT, out)
        # And nothing was written where the bundle would have gone.
        self.assertFalse(os.path.exists(self.dest))

    def test_the_skip_says_how_to_re_export_on_purpose(self):
        # An operator rotating the passphrase must not have to read the source.
        self.assertIn("--re-export-backup", self._run(_verified()))

    def test_a_passphrase_in_the_environment_does_not_defeat_the_skip(self):
        # The whole defect: setting this was what made the guard unreachable.
        os.environ["RMC_EDGE_TLS_CA_PASSPHRASE"] = "x" * 40
        self.addCleanup(os.environ.pop, "RMC_EDGE_TLS_CA_PASSPHRASE", None)
        out = self._run(_verified())
        self.assertIn("Backup skipped", out)
        self.assertFalse(os.path.exists(self.dest))

    def test_asking_for_a_re_export_gets_one(self):
        # Proven by it walking past the skip and demanding the passphrase.
        with self.assertRaises(CommandError) as caught:
            self._run(_verified(), re_export_backup=True)
        self.assertIn("RMC_EDGE_TLS_CA_PASSPHRASE", str(caught.exception))

    def test_a_different_ca_is_not_covered_by_the_old_record(self):
        # A restored or replaced CA has no backup, whatever the record remembers.
        with self.assertRaises(CommandError) as caught:
            self._run(_verified(fingerprint="AA:BB:CC"))
        self.assertIn("RMC_EDGE_TLS_CA_PASSPHRASE", str(caught.exception))

    def test_a_record_that_was_never_read_back_does_not_count(self):
        state = {"active": {"fingerprint": FINGERPRINT, "exported_at": EXPORTED_AT}}
        with self.assertRaises(CommandError) as caught:
            self._run(state)
        self.assertIn("RMC_EDGE_TLS_CA_PASSPHRASE", str(caught.exception))

    def test_no_backup_is_still_refused_when_there_is_no_verified_one(self):
        # The original protection, unchanged: the window where the CA has no copy is
        # the afternoon somebody spends installing it on devices.
        with self.assertRaises(CommandError) as caught:
            self._run({"active": {}}, no_backup=True)
        self.assertIn("--no-backup refused", str(caught.exception))

    def test_no_backup_on_an_already_backed_up_ca_still_skips_quietly(self):
        out = self._run(_verified(), no_backup=True)
        self.assertIn("Backup skipped", out)

    def test_the_flag_is_registered(self):
        from django.core.management import load_command_class

        parser = load_command_class("apps.schools", "edge_bootstrap").create_parser(
            "manage.py", "edge_bootstrap"
        )
        flags = {a for action in parser._actions for a in action.option_strings}
        self.assertIn("--re-export-backup", flags)
        self.assertIn("--no-backup", flags)
