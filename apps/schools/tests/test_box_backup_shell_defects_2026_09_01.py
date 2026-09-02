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


def _check_line(*must_contain):
    """The one line of the real script that makes a given decision."""
    for line in _text().splitlines():
        if all(token in line for token in must_contain):
            return line
    raise AssertionError("no line containing %r in box-backup.sh" % (must_contain,))


#: 9,733 lines, matching the real archive measured on the box -- ~500KB, comfortably
#: past the 64KB pipe buffer. THE SIZE IS THE TEST. Below the buffer, `printf` finishes
#: before `grep -q` closes the pipe, no SIGPIPE is raised, and the broken form behaves
#: perfectly. That is exactly why a suite of 40 tests passed over this for its whole life.
_BIG_TOC = (
    'toc="$(seq 1 9733 | sed \'s/$/; 1259 16385 TABLE public django_migrations rmc/\')"\n'
)
_BIG_TOC_WITHOUT = (
    'toc="$(seq 1 9733 | sed \'s/$/; 1259 16385 TABLE public something_else rmc/\')"\n'
)


class AnEarlyMatchInALargeListIsNotAMissTests(SimpleTestCase):
    """LOAD-BEARING. Each fails on the unfixed tree, and the defect is an INVERSION.

    The script runs under ``set -uo pipefail``. ``grep -q`` exits the instant it matches
    and closes its input, so a ``printf`` feeding it a large string dies of SIGPIPE (141)
    -- and ``pipefail`` promotes that to the pipeline's status. Every ``... | grep -q``
    in the file therefore reported NOT FOUND precisely when the thing WAS found.

    MEASURED on the Gilead box 2026-09-01: a 65,491,424-byte dump, whose decrypted
    archive lists 9,733 entries and names django_migrations five times, was rejected as
    "not of this application" on every single attempt. The service could not report a
    successful backup of a real database, ever.
    """

    def setUp(self):
        if shutil.which("bash") is None:
            self.skipTest("bash unavailable")

    def test_a_real_sized_toc_that_names_the_table_is_accepted(self):
        proc = _run(
            "set -uo pipefail\n"
            'EXPECT_TABLE="django_migrations"\n'
            + _BIG_TOC
            + _check_line("EXPECT_TABLE", "grep -q") + "\n"
            '  echo VERDICT=missing\n'
            "else\n"
            '  echo VERDICT=present\n'
            "fi\n"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("VERDICT=present", proc.stdout)

    def test_a_dump_kept_by_retention_is_not_reported_as_prunable(self):
        # Not cosmetic: this decision DELETES files. A false "not a survivor" removes a
        # backup that should have been kept, and it is position-dependent -- an early
        # match in a 20,000-line list reported NOT FOUND while a late one reported found.
        proc = _run(
            "set -uo pipefail\n"
            'name="file-1.dump.enc"\n'
            'survivors="$(seq 1 20000 | sed \'s/^/file-/;s/$/.dump.enc/\')"\n'
            + _check_line("survivors", "grep -qxF") + "\n"
            '  echo VERDICT=keep\n'
            "else\n"
            '  echo VERDICT=delete\n'
            "fi\n"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("VERDICT=keep", proc.stdout)

    def test_no_early_exit_consumer_is_fed_by_a_pipe(self):
        # The general shape, so the next one is caught at review rather than on a box.
        # `set +o pipefail` is already used for the passphrase `head -c` in this file --
        # the trap was known, it just had not been applied to the greps.
        #
        # Reported as line numbers, not with assertNotIn on the file: the haystack is
        # 46KB and a bare assertNotIn prints all of it, burying the finding it just made.
        offenders = [
            "%d: %s" % (n, line.strip())
            for n, line in enumerate(_text().splitlines(), 1)
            if "| grep -q" in line
        ]
        self.assertEqual(offenders, [], "piped early-exit grep(s):\n" + "\n".join(offenders))


class TheGuardStillRejectsARealFailureTests(SimpleTestCase):
    """CONTROLS. These pass on BOTH trees, and the second one explains the whole story."""

    def setUp(self):
        if shutil.which("bash") is None:
            self.skipTest("bash unavailable")

    def test_a_toc_that_genuinely_lacks_the_table_is_still_rejected(self):
        # The fix must not turn the check into a rubber stamp. Note this passed even
        # while broken -- grep read to EOF, so there was no SIGPIPE to invert.
        proc = _run(
            "set -uo pipefail\n"
            'EXPECT_TABLE="django_migrations"\n'
            + _BIG_TOC_WITHOUT
            + _check_line("EXPECT_TABLE", "grep -q") + "\n"
            '  echo VERDICT=missing\n'
            "else\n"
            '  echo VERDICT=present\n'
            "fi\n"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("VERDICT=missing", proc.stdout)

    def test_a_small_toc_behaves_correctly_even_unfixed(self):
        # WHY NOBODY SAW THIS. Under the 64KB pipe buffer the broken form is correct:
        # printf writes everything and exits before grep closes the pipe, so no SIGPIPE.
        # A fixture-sized table of contents can only ever agree with a real one here --
        # which is the argument for sizing this module's fixtures to the real archive.
        proc = _run(
            "set -uo pipefail\n"
            'EXPECT_TABLE="django_migrations"\n'
            'toc="$(printf \'%s\\n\' a b django_migrations c)"\n'
            + _check_line("EXPECT_TABLE", "grep -q") + "\n"
            '  echo VERDICT=missing\n'
            "else\n"
            '  echo VERDICT=present\n'
            "fi\n"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("VERDICT=present", proc.stdout)
