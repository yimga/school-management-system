"""Two defects that stopped the edge backup from backing anything up.

MEASURED on the Gilead box, 2026-09-01, on the FIRST real run of this service:

    [backup] generated a backup passphrase at /keys/box-backup-passphrase.txt
    [backup] TAKE A COPY OFF THIS BOX. Without it every dump here is unreadable...
    box-backup.sh: line 578: [: 8.80274e+11: integer expression expected
    box-backup.sh: line 582: [: 8.80274e+11: integer expression expected
    [backup] dumping runmycampus -> rmc-box-db-20260901T220947Z.dump.enc
    box-backup.sh: line 605: PIPESTATUS[1]: unbound variable

and then, from `verify`: "no dump on this box". The service told the operator to
safeguard a passphrase and produced nothing for that passphrase to open.

WHY THE EXISTING SUITE COULD NOT CATCH EITHER, which is the part worth keeping. Its
assertions on these two areas are `assertIn("PIPESTATUS", self.text)` and
`self.text.index('free="$(free_bytes)"')`. Both are true of the broken script, true of
the fixed one, and true of any future script that merely NAMES those things and works in
neither. So the tests below RUN the lines, using the bash-harness technique the sibling
file already established for the retention rules -- and for the reason it states there:
a rule that is only READ is a rule nobody has ever run.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

from django.test import SimpleTestCase

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKUP = REPO / "deploy" / "selfhost" / "box-backup.sh"


def _text() -> str:
    return BACKUP.read_text(encoding="utf-8")


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=60
    )


def _capture_block(pipeline_marker: str, stop_marker: str) -> str:
    """The REAL exit-code capture lines that follow one pipeline in the script."""
    text = _text()
    start = text.index(pipeline_marker)
    body = text[text.index("\n", start) + 1:]
    return body[: body.index(stop_marker)]


class TheExitCodeCaptureSurvivesSetUTests(SimpleTestCase):
    """LOAD-BEARING. These execute the script's own lines and fail on the unfixed tree.

    ``PIPESTATUS`` is rebuilt by EVERY command, including the assignment that reads it.
    Reading ``[0]`` on one line and ``[1]`` on the next therefore indexes an array that
    already holds a single element, and under ``set -u`` that is fatal. It killed the run
    between the pipeline and the check of its exit codes -- so the partial file was never
    cleaned up, no dump was written, and the failure surfaced only as a shell error.
    """

    def setUp(self):
        if shutil.which("bash") is None:
            self.skipTest("bash unavailable")

    def _probe(self, capture, first, second):
        script = (
            "set -uo pipefail\n"
            "probe() {\n"
            "  true | true\n"
            + capture
            + '  printf "A=%s B=%s\\n" "$' + first + '" "$' + second + '"\n'
            "}\n"
            "probe\n"
        )
        return _run(script)

    def test_the_database_dump_capture_runs(self):
        capture = _capture_block('| encrypt_to "$tmp"', '  if [ "$rc_dump"')
        proc = self._probe(capture, "rc_dump", "rc_enc")
        self.assertNotIn("unbound variable", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("A=0 B=0", proc.stdout)

    def test_the_media_archive_capture_runs(self):
        # The identical defect, in the path nobody reaches until a box has media.
        capture = _capture_block('tar -C "$MEDIA_SRC"', '  if [ "$rc_tar"')
        proc = self._probe(capture, "rc_tar", "rc_enc")
        self.assertNotIn("unbound variable", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("A=0 B=0", proc.stdout)

    def test_a_short_status_array_fails_closed(self):
        # If the array is ever shorter than expected the codes must read as FAILURE.
        # An empty default would make `[ "$rc" != "0" ]` true by accident; a default of
        # 0 would call a broken pipe a success and keep a truncated dump.
        proc = _run(
            "set -uo pipefail\n"
            "probe() {\n"
            "  local -a pipe_rc=()\n"
            '  printf "%s %s\\n" "${pipe_rc[0]:-1}" "${pipe_rc[1]:-1}"\n'
            "}\n"
            "probe\n"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "1 1")


class ByteCountsNeverReachATestAsScientificNotationTests(SimpleTestCase):
    """LOAD-BEARING, but a SOURCE contract, and the reason for that is the point.

    awk's ``print`` formats numbers through OFMT (``%.6g``). gawk prints integral values
    as integers whatever OFMT says; mawk -- the awk Debian and Ubuntu ship, and therefore
    the awk inside this container -- does not. 819GB free came back as "8.80274e+11",
    ``[ "$free" -lt "$need" ]`` died with "integer expression expected", and because a
    failed test merely returns non-zero, the guard evaluated FALSE and the run proceeded.
    The one check standing between this service and filling a school's disk was inert on
    every box with more than about a gigabyte free.

    An EXECUTABLE version of this could not be load-bearing anywhere gawk is installed,
    which is every development machine and this test runner. Pinning the FORMAT is the
    honest way to hold it: ``printf`` with an explicit conversion cannot be reformatted
    by OFMT, on any awk.
    """

    def _awk_line(self, func):
        text = _text()
        start = text.index(func + "()")
        return text[start: text.index("\n", text.index("awk", start))]

    def test_free_bytes_uses_printf_not_print(self):
        line = self._awk_line("free_bytes")
        self.assertIn("printf", line)
        self.assertNotIn("{ print $", line)

    def test_dir_bytes_uses_printf_not_print(self):
        line = self._awk_line("dir_bytes")
        self.assertIn("printf", line)
        self.assertNotIn("{ print $", line)


class TheSpaceGuardStillComparesTests(SimpleTestCase):
    """CONTROL. Passes on BOTH trees here, and says so rather than pretending otherwise.

    It cannot fail on this runner, because gawk will not reproduce the formatting. It is
    kept because it WILL fail on a mawk machine if the format is ever reverted, and
    because it proves the function still returns something shell arithmetic accepts.
    """

    def test_free_bytes_returns_digits_a_shell_test_can_compare(self):
        if shutil.which("bash") is None:
            self.skipTest("bash unavailable")
        text = _text()
        start = text.index("free_bytes() {")
        body = text[text.index("{", start) + 1: text.index("\n}", start)]
        script = (
            "set -uo pipefail\n"
            "df() { printf '%s\\n' 'Filesystem 1024-blocks Used Available Cap M' "
            "'/dev/x 1000000000 100 858783744 1% /'; }\n"
            "BACKUP_DIR=/tmp\n"
            "free_bytes() {\n"
            + body + "\n"
            "}\n"
            'v="$(free_bytes)"\n'
            'if [ "$v" -gt 0 ]; then printf "comparable=yes\\n"; '
            'else printf "comparable=no\\n"; fi\n'
        )
        proc = _run(script)
        self.assertNotIn("integer expression expected", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("comparable=yes", proc.stdout)
