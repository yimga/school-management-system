"""A box can be told to rebuild and quietly not rebuild.

The containers run a BAKED image. `git pull` in /srv/rmc moves the checkout and
nothing else -- the running code is whatever was compiled into
`runmycampus-selfhost:latest` -- and `docker compose up -d` WITHOUT `--build`
restarts that old image perfectly happily. Every check then passes, against the old
code, and nothing anywhere says so.

MEASURED, not hypothesised. On the Gilead box on 2026-08-27 the checkout was at
d2ec46fce while the running image had been built from 5869d6422: six commits and 877
lines behind, including the CA-passphrase guard written for that box three hours
earlier. The only record of the running commit is /app/.build-stamp.json INSIDE the
image, which nobody thinks to read.

`edge-bootstrap.sh` made it worse: when web was down, its own error message told the
operator to run a bare `docker compose up -d`.

So the property under test is not "does a build happen" -- it is "can this thing
report success while the running code stayed where it was". These tests run the real
stamp parser out of the real script against real stamp bytes, because a parser that
silently returns empty would make the final verification vacuously pass.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

from django.test import SimpleTestCase

SELFHOST = pathlib.Path(__file__).resolve().parents[3] / "deploy" / "selfhost"
REBUILD = SELFHOST / "box-rebuild.sh"
BOOTSTRAP = SELFHOST / "edge-bootstrap.sh"

REAL_STAMP = (
    '{\n  "build_time": "2026-08-27T14:52:31Z",\n'
    '  "commit_sha": "5869d6422b37284a6bbdfe4a4beb5a882cd9fa19"\n}\n'
)


def _need_bash(case):
    if shutil.which("bash") is None:
        case.skipTest("bash not available; these assert real shell behaviour")


def _extract(func_name: str) -> str:
    """Pull one shell function's BODY verbatim out of the real script.

    The closing brace is deliberately excluded: these tests splice the body into a
    harness, and a stray `}` is a syntax error rather than a failed assertion.
    """
    text = REBUILD.read_text(encoding="utf-8")
    start = text.index(func_name + "() {") + len(func_name + "() {")
    end = text.index("\n}", start)
    return text[start:end]


class TheStampParserMustActuallyParseTests(SimpleTestCase):
    """If this returns empty, the final "prove it" check passes on nothing."""

    def setUp(self):
        _need_bash(self)
        # The body of running_commit, with the docker call replaced by the stamp on
        # stdin -- the parsing is the part that can be wrong, and it is pure text.
        body = _extract("running_commit")
        self.pipeline = body.split("2>/dev/null", 1)[1].strip().lstrip("\\").strip()

    def _parse(self, stamp: str) -> str:
        script = "printf '%s' \"$STAMP\" " + self.pipeline
        proc = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env={"STAMP": stamp, "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def test_it_reads_the_commit_out_of_a_real_stamp(self):
        self.assertEqual(
            self._parse(REAL_STAMP), "5869d6422b37284a6bbdfe4a4beb5a882cd9fa19"
        )

    def test_it_does_not_depend_on_key_order(self):
        # The stamp writer is free to reorder its keys; the parser must not care.
        reordered = '{\n  "commit_sha": "abc123def456",\n  "build_time": "x"\n}\n'
        self.assertEqual(self._parse(reordered), "abc123def456")

    def test_a_missing_stamp_parses_to_empty_not_to_junk(self):
        # Empty is the signal the script treats as "cannot tell", and it must FAIL
        # the rebuild rather than pass it. Junk here would compare unequal and look
        # like drift; empty is handled explicitly.
        self.assertEqual(self._parse(""), "")
        self.assertEqual(self._parse('{"build_time": "x"}\n'), "")

    def test_it_does_not_leak_the_build_time_into_the_sha(self):
        # The first cut stripped spaces and quotes but not commas, so a trailing
        # comma could ride along into the compared value and never match.
        self.assertNotIn(",", self._parse(REAL_STAMP))
        self.assertEqual(len(self._parse(REAL_STAMP)), 40)


class TheScriptRefusesToClaimSuccessTests(SimpleTestCase):
    """The verification step is the entire point; it must not be removable by accident."""

    def setUp(self):
        self.text = REBUILD.read_text(encoding="utf-8")

    def test_it_compares_the_new_stamp_against_the_checkout(self):
        self.assertIn('AFTER_COMMIT="$(running_commit)"', self.text)
        self.assertIn('if [ "$AFTER_COMMIT" != "$HEAD_COMMIT" ]; then', self.text)

    def test_an_unstamped_image_is_a_failure_not_a_warning(self):
        # An image with no stamp cannot be proven current, and "cannot prove" must
        # not render as "fine" -- that is the whole class of bug being closed.
        block = self.text[self.text.index('AFTER_COMMIT="$(running_commit)"'):]
        head = block[: block.index("bar 7")]
        self.assertIn('if [ -z "$AFTER_COMMIT" ]; then', head)
        # Whitespace-normalised: the message wraps across lines in the source.
        flat = " ".join(head.lower().split())
        self.assertIn("do not treat this box as updated", flat)

    def test_the_build_runs_before_the_containers_are_recreated(self):
        # Ordering IS the fix. Recreating first would serve the old image and the
        # later build would look like it worked.
        build_at = self.text.index('"${COMPOSE[@]}" build web')
        up_at = self.text.index('"${COMPOSE[@]}" up -d')
        self.assertLess(build_at, up_at)

    def test_a_failed_build_leaves_the_box_alone(self):
        # A half-updated box in a school is worse than an out-of-date one.
        self.assertIn("The box is UNCHANGED and still serving the old image", self.text)

    def test_check_mode_changes_nothing(self):
        # --check exists so somebody can ask the question without committing to a
        # twenty-minute build. It must return before anything mutates.
        check_at = self.text.index('if [ "$CHECK_ONLY" = "1" ]; then')
        for mutation in ('"${COMPOSE[@]}" build web', '"${COMPOSE[@]}" up -d', "merge --ff-only"):
            self.assertLess(
                check_at, self.text.index(mutation), "%s runs before --check exits" % mutation
            )

    def test_it_never_discards_uncommitted_work(self):
        # Standing rule: never revert or check out a file this process did not
        # modify. A dirty tree stops the pull instead of being flattened by it.
        self.assertIn("NOT pulling over them", self.text)
        # Matched as COMMANDS, not as substrings. The script's own prose contains
        # "is not a git checkout -- cannot tell what code it should run", and a
        # naive `assertNotIn("git checkout --")` fails on that sentence -- which
        # would train whoever hits it to weaken the test rather than read it.
        destructive = re.compile(
            r"^\s*git\s+(?:-C\s+\S+\s+)?(?:checkout\s+--|reset\s+--hard|clean\b|stash\b|restore\b)",
            re.M,
        )
        found = destructive.findall(self.text)
        self.assertEqual(found, [], "box-rebuild.sh runs a destructive git command")

    def test_being_offline_does_not_block_a_rebuild(self):
        # Offline is the NORMAL state for a box in a school. Refusing to rebuild
        # code already on disk because a remote is unreachable would be the wrong
        # failure for the deployment this product exists to serve.
        self.assertIn("could not reach the git remote", self.text)
        self.assertIn("building from the checkout as it stands", self.text)


class TheShellScriptsMustRunOnTheBoxTests(SimpleTestCase):
    """Both files execute on Linux. The usual ways they stop doing that."""

    def test_both_parse(self):
        _need_bash(self)
        for script in (REBUILD, BOOTSTRAP):
            proc = subprocess.run(
                ["bash", "-n", str(script)], capture_output=True, text=True
            )
            self.assertEqual(proc.returncode, 0, "%s: %s" % (script.name, proc.stderr))

    def test_neither_is_CRLF(self):
        # A CRLF here is `$'\r': command not found` on the first line that matters.
        for script in (REBUILD, BOOTSTRAP):
            self.assertEqual(
                script.read_bytes().count(b"\r\n"), 0, "%s gained CRLF" % script.name
            )

    def test_no_control_characters_survived_an_edit(self):
        # A `\1` backreference written through a careless Python patch becomes a
        # literal 0x01 byte, and sed then substitutes NOTHING -- which made the
        # stamp parser silently return empty while still exiting 0.
        for script in (REBUILD, BOOTSTRAP):
            raw = script.read_bytes()
            bad = [b for b in raw if b < 9 or (13 < b < 32)]
            self.assertEqual(bad, [], "%s contains control bytes %r" % (script.name, bad))

    def test_every_variable_used_is_one_that_exists(self):
        # `set -u` turns an unbound variable into an abrupt exit. This caught a real
        # one: the new bootstrap message referenced $SCRIPT_DIR, which does not exist
        # in that script (it is $HERE) -- and it sat on the error path, so it would
        # have fired exactly when somebody needed to read the message.
        for script in (REBUILD, BOOTSTRAP):
            text = script.read_text(encoding="utf-8")
            # Assignment can follow `then`/`else`/`do`/`;` on the same line -- the
            # colour variables are set inside a one-line `if [ -t 1 ]; then B=...`.
            assigned = set(
                re.findall(
                    r"(?:^|;|\bthen\b|\belse\b|\bdo\b|\bexport\b)\s*([A-Z][A-Z0-9_]*)=",
                    text,
                    re.M,
                )
            )
            assigned |= set(re.findall(r"\bfor\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b", text))
            assigned |= set(re.findall(r"local\s+([a-z_][a-z0-9_]*)=", text))
            # `${VAR:-default}` / `${VAR:=x}` / `${VAR:+x}` are SAFE under set -u --
            # that is the whole point of the form. Only a bare $VAR or ${VAR} can
            # abort the script, so only those need an assignment to exist.
            used = set(re.findall(r"\$([A-Z][A-Z0-9_]*)\b", text))
            used |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)\}", text))
            # Environment and shell builtins are legitimately unassigned here.
            used -= {
                "BASH_SOURCE", "PATH", "HOME", "PWD", "USER", "IFS", "SHELL", "TERM",
                "RMC_EDGE_TLS_CA_PASSPHRASE", "RMC_EDGE_OUT_DIR", "GIT_TERMINAL_PROMPT",
                "GIT_COMMIT", "BUILD_TIME", "ENVIRONMENT", "COMPOSE_FILE_OVERRIDE",
                "WEB_PORT", "OSTYPE", "HOSTNAME", "LANG", "LC_ALL",
            }
            missing = sorted(used - assigned)
            self.assertEqual(
                missing, [], "%s uses unassigned %r under set -u" % (script.name, missing)
            )


class TheBootstrapStopsTeachingTheTrapTests(SimpleTestCase):
    def setUp(self):
        self.text = BOOTSTRAP.read_text(encoding="utf-8")

    def test_it_no_longer_tells_people_to_run_a_bare_up(self):
        # The instruction that created the trap. Followed after a pull, it starts the
        # image compiled last time and every check below passes against old code.
        self.assertNotIn("Start it (`docker compose -f $COMPOSE_FILE up -d`)", self.text)

    def test_it_points_at_the_rebuild_script_instead(self):
        self.assertIn("box-rebuild.sh", self.text)
        self.assertIn("BAKED image", self.text)

    def test_the_rebuild_script_it_names_actually_exists(self):
        # A runbook that names a command which is not there is worse than no runbook.
        self.assertTrue(REBUILD.exists(), "edge-bootstrap.sh points at a missing script")
