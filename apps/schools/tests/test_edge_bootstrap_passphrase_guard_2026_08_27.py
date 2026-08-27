"""Following the closing banner must not invalidate the backup you just secured.

THE TRAP, as shipped. `edge-bootstrap.sh` ends by telling the operator to move one of
these off the machine:

    /srv/box-ca-bundle.p12       the encrypted CA backup
    /srv/box-ca-passphrase.txt

An operator who moves the PASSPHRASE is punished for it. The next run finds no
passphrase file, falls into the `else` branch, mints a NEW passphrase, re-encrypts the
bundle under it and overwrites the bundle -- so the copy they carefully stored opens
nothing. Nothing warns them; they find out during a restore, which is the worst
possible moment to find out anything.

The script already knew the hazard. Its own comment on the REUSE branch says "A second
passphrase would re-encrypt the bundle and silently strand whatever copy is already off
the box." The `else` branch does exactly that, because it cannot tell a fresh box from
a secured one -- and it guessed "fresh".

These tests RUN the real decision block out of the real script rather than asserting on
its text, because the property that matters is what the shell does, not what the source
says. The block is extracted between two stable anchors; if somebody restructures it so
the anchors no longer match, extraction fails loudly rather than silently passing.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import tempfile

from django.test import SimpleTestCase

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[3] / "deploy" / "selfhost" / "edge-bootstrap.sh"
)

# The decision block, start and end. Both are load-bearing lines that exist for their
# own reasons, so they are unlikely to be reworded casually.
START = "SKIP_CA_EXPORT=0"
END = 'ok "docker, compose file and .env all present"'

HARNESS = """
set -uo pipefail
ok()   {{ :; }}
warn() {{ :; }}
say()  {{ :; }}
die()  {{ echo "DIED: $*" >&2; exit 9; }}
new_passphrase() {{ printf '%s' 'GENERATED0000000000000000000000000000000000x'; }}
OUT_DIR="{out}"
PASSPHRASE_FILE="{passfile}"
{block}
echo "SKIP_CA_EXPORT=$SKIP_CA_EXPORT"
echo "PASSPHRASE=${{RMC_EDGE_TLS_CA_PASSPHRASE:-}}"
"""


def _block() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index(START)
    end = text.index(END, start)
    return text[start:end]


class TheBootstrapMustNotReEncryptABundleItCannotOpenTests(SimpleTestCase):
    def setUp(self):
        if shutil.which("bash") is None:
            self.skipTest("bash not available; this asserts real shell behaviour")
        self.dir = tempfile.mkdtemp(prefix="edge-boot-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.passfile = os.path.join(self.dir, "box-ca-passphrase.txt")
        self.bundle = os.path.join(self.dir, "box-ca-bundle.p12")

    def _run(self):
        script = HARNESS.format(
            out=self.dir.replace("\\", "/"),
            passfile=self.passfile.replace("\\", "/"),
            block=_block(),
        )
        proc = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, env={**os.environ}
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = dict(
            line.split("=", 1)
            for line in proc.stdout.strip().splitlines()
            if "=" in line
        )
        return out

    # --- the branch that was missing -------------------------------------------------

    def test_a_secured_box_does_not_mint_a_second_passphrase(self):
        # Bundle present, passphrase gone: the operator did what the banner asked.
        # Minting here re-encrypts the bundle and strands the copy they are holding.
        pathlib.Path(self.bundle).write_bytes(b"an existing encrypted bundle")
        out = self._run()
        self.assertEqual(out["SKIP_CA_EXPORT"], "1")
        self.assertEqual(
            out["PASSPHRASE"], "", "it must not invent a passphrase it cannot verify"
        )

    def test_a_secured_box_leaves_the_bundle_byte_identical(self):
        # The strongest statement of the property: the file on disk is untouched.
        original = b"an existing encrypted bundle"
        pathlib.Path(self.bundle).write_bytes(original)
        self._run()
        self.assertEqual(pathlib.Path(self.bundle).read_bytes(), original)

    def test_a_secured_box_does_not_recreate_the_passphrase_file(self):
        # Recreating it would silently undo the separation the operator just made,
        # and the next run would then "reuse" a passphrase that opens nothing.
        pathlib.Path(self.bundle).write_bytes(b"an existing encrypted bundle")
        self._run()
        self.assertFalse(
            os.path.exists(self.passfile),
            "the passphrase file came back; the operator's separation was undone",
        )

    # --- the two branches that already worked, which must keep working ---------------

    def test_a_fresh_box_still_generates_and_stores_one(self):
        # No bundle and no passphrase is a genuinely fresh box. Refusing here would
        # mean no box could ever take its first backup.
        out = self._run()
        self.assertEqual(out["SKIP_CA_EXPORT"], "0")
        self.assertTrue(out["PASSPHRASE"], "a fresh box must still get a passphrase")
        self.assertTrue(os.path.exists(self.passfile))

    def test_an_existing_passphrase_file_is_reused_not_regenerated(self):
        pathlib.Path(self.passfile).write_text("kept-passphrase\n", encoding="utf-8")
        pathlib.Path(self.bundle).write_bytes(b"an existing encrypted bundle")
        out = self._run()
        self.assertEqual(out["SKIP_CA_EXPORT"], "0")
        self.assertEqual(out["PASSPHRASE"], "kept-passphrase")

    def test_the_passphrase_file_wins_over_the_secured_branch(self):
        # Ordering matters: with BOTH present the file is authoritative, because a
        # readable passphrase means a fresh verified export is possible and better.
        pathlib.Path(self.passfile).write_text("kept-passphrase\n", encoding="utf-8")
        pathlib.Path(self.bundle).write_bytes(b"bundle")
        self.assertEqual(self._run()["SKIP_CA_EXPORT"], "0")

    def test_an_environment_passphrase_still_wins_over_everything(self):
        # An operator supplying it explicitly is the one case where a re-export is
        # unambiguously wanted, and it must not be second-guessed.
        pathlib.Path(self.bundle).write_bytes(b"bundle")
        script = HARNESS.format(
            out=self.dir.replace("\\", "/"),
            passfile=self.passfile.replace("\\", "/"),
            block=_block(),
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env={**os.environ, "RMC_EDGE_TLS_CA_PASSPHRASE": "from-the-environment"},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("SKIP_CA_EXPORT=0", proc.stdout)
        self.assertIn("PASSPHRASE=from-the-environment", proc.stdout)


class TheRestOfTheScriptHonoursTheDecisionTests(SimpleTestCase):
    """Deciding to skip is worthless if the two places that act on it ignore it."""

    def setUp(self):
        self.text = SCRIPT.read_text(encoding="utf-8")

    def test_the_export_uses_no_backup_when_the_passphrase_is_off_box(self):
        # `--no-backup` is itself refused by edge_bootstrap unless a VERIFIED backup is
        # already on record, so this cannot become a way to ship a box with none.
        self.assertIn("BACKUP_ARGS=(--no-backup)", self.text)
        self.assertIn('BACKUP_ARGS=(--backup-to "$BUNDLE_IN_BOX")', self.text)
        self.assertIn('edge_bootstrap "${BACKUP_ARGS[@]}"', self.text)
        self.assertNotIn(
            'edge_bootstrap --backup-to "$BUNDLE_IN_BOX"',
            self.text,
            "the unconditional export is back; a secured box will be re-encrypted",
        )

    def test_the_off_box_copy_does_not_overwrite_a_kept_bundle(self):
        # Overwriting is the same mistake as re-encrypting: the bundle on disk is the
        # one the operator's stored passphrase opens, and a fresh export would not be.
        copy_line = 'cp "web:$BUNDLE_IN_BOX" "$OUT_DIR/box-ca-bundle.p12"'
        self.assertIn(copy_line, self.text)
        guard = self.text.index('if [ "$SKIP_CA_EXPORT" = "1" ]', self.text.index("Off-box copies"))
        self.assertLess(guard, self.text.index(copy_line, guard), "the copy is not guarded")

    def test_the_banner_stops_telling_people_to_move_the_passphrase(self):
        # The instruction that created the trap. Moving the BUNDLE is safe; moving the
        # passphrase leaves the box holding a file nobody can open.
        self.assertIn("Move the BUNDLE off this machine -- not the passphrase", self.text)
        self.assertNotIn("Move ONE of these off this machine", self.text)

    def test_the_banner_says_nothing_to_move_once_it_is_already_done(self):
        self.assertIn("Nothing to move -- the passphrase is already off this machine", self.text)

    def test_the_script_still_parses(self):
        if shutil.which("bash") is None:
            self.skipTest("bash not available")
        proc = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_it_is_still_an_LF_only_file(self):
        # It runs on the box, not on Windows. A CRLF here is a `$'\r': command not
        # found` on the first line that matters.
        raw = SCRIPT.read_bytes()
        self.assertEqual(raw.count(b"\r\n"), 0)

    def test_the_extraction_anchors_still_match(self):
        # If this fails, the behavioural tests above are testing nothing. Better to
        # fail here with a reason than to pass an empty block.
        block = _block()
        self.assertIn("SKIP_CA_EXPORT=1", block)
        self.assertIn("elif", block)
        self.assertGreater(len(block.splitlines()), 15)
        self.assertTrue(re.search(r"box-ca-bundle\.p12", block))
