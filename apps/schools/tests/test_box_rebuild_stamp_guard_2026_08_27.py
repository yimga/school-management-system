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

import os
import pathlib
import re
import shutil
import subprocess
import tempfile

from django.test import SimpleTestCase

SELFHOST = pathlib.Path(__file__).resolve().parents[3] / "deploy" / "selfhost"
REBUILD = SELFHOST / "box-rebuild.sh"
BOOTSTRAP = SELFHOST / "edge-bootstrap.sh"
AUDIT = SELFHOST / "box-audit.sh"

#: Every shell script that runs ON a box. They share one set of ways to stop working.
BOX_SCRIPTS = (REBUILD, BOOTSTRAP, AUDIT)

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
        # The up goes through the compose() wrapper now, because a box in a TLS
        # mode has to carry --profile tls or its terminator never starts.
        build_at = self.text.index('"${COMPOSE[@]}" build web')
        up_at = self.text.index("if ! compose up -d")
        self.assertLess(build_at, up_at)

    def test_a_failed_build_leaves_the_box_alone(self):
        # A half-updated box in a school is worse than an out-of-date one.
        self.assertIn("The box is UNCHANGED and still serving the old image", self.text)

    def test_check_mode_changes_nothing(self):
        # --check exists so somebody can ask the question without committing to a
        # twenty-minute build. It must return before anything mutates.
        check_at = self.text.index('if [ "$CHECK_ONLY" = "1" ]; then')
        for mutation in ('"${COMPOSE[@]}" build web', "if ! compose up -d", "merge --ff-only"):
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
        for script in BOX_SCRIPTS:
            proc = subprocess.run(
                ["bash", "-n", str(script)], capture_output=True, text=True
            )
            self.assertEqual(proc.returncode, 0, "%s: %s" % (script.name, proc.stderr))

    def test_neither_is_CRLF(self):
        # A CRLF here is `$'\r': command not found` on the first line that matters.
        for script in BOX_SCRIPTS:
            self.assertEqual(
                script.read_bytes().count(b"\r\n"), 0, "%s gained CRLF" % script.name
            )

    def test_no_control_characters_survived_an_edit(self):
        # A `\1` backreference written through a careless Python patch becomes a
        # literal 0x01 byte, and sed then substitutes NOTHING -- which made the
        # stamp parser silently return empty while still exiting 0.
        for script in BOX_SCRIPTS:
            raw = script.read_bytes()
            bad = [b for b in raw if b < 9 or (13 < b < 32)]
            self.assertEqual(bad, [], "%s contains control bytes %r" % (script.name, bad))

    def test_every_variable_used_is_one_that_exists(self):
        # `set -u` turns an unbound variable into an abrupt exit. This caught a real
        # one: the new bootstrap message referenced $SCRIPT_DIR, which does not exist
        # in that script (it is $HERE) -- and it sat on the error path, so it would
        # have fired exactly when somebody needed to read the message.
        for script in BOX_SCRIPTS:
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
            # Only what THIS shell expands. Comments and single-quoted spans go
            # first: `$RMC_EDGE_CREDENTIAL` inside a `sh -c '...'` is not an
            # expansion here at all -- the shell INSIDE the container expands it,
            # from that container's environment. Counting it produced a confident
            # false positive on box-audit.sh, which runs clean on real hardware.
            #
            # The stripping is naive, and deliberately so: a mis-paired quote drops
            # real code and costs a missed finding. For a test whose whole value is
            # being believed when it fires, that is the right direction to be wrong.
            scannable = re.sub(r"(?m)#.*$", "", text)
            scannable = re.sub(r"'[^']*'", "''", scannable)
            # `${VAR:-default}` / `${VAR:=x}` / `${VAR:+x}` are SAFE under set -u --
            # that is the whole point of the form. Only a bare $VAR or ${VAR} can
            # abort the script, so only those need an assignment to exist.
            used = set(re.findall(r"\$([A-Z][A-Z0-9_]*)\b", scannable))
            used |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)\}", scannable))
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


class TheAuditIsReadOnlyAndPortableTests(SimpleTestCase):
    """It runs before a rebuild to decide whether one is safe. Two properties follow."""

    def setUp(self):
        self.text = AUDIT.read_text(encoding="utf-8")

    def test_it_does_not_hardcode_one_box_s_path(self):
        # It has to audit ANY box, not the one it was first written on. /srv/rmc is
        # the conventional location, not a guaranteed one.
        self.assertNotIn("cd /srv/rmc", self.text)
        self.assertIn('REPO_ROOT="$(cd "$HERE/../.." && pwd)"', self.text)

    def test_it_changes_nothing(self):
        # An audit that restarts a container to find out whether it is healthy has
        # destroyed the thing it was measuring, and an operator can no longer tell a
        # pre-existing fault from one the audit caused.
        mutating = re.compile(
            r"^\s*(?:\"\$\{COMPOSE\[@\]\}\"\s+(?:up|down|restart|build|stop|start|rm)"
            r"|docker\s+(?:rm|rmi|kill|stop|start|restart)"
            r"|git\s+(?:checkout|reset|clean|stash|merge|pull)"
            r"|rm\s+-[rf]|mv\s|>\s*/)",
            re.M,
        )
        found = mutating.findall(self.text)
        self.assertEqual(found, [], "box-audit.sh mutates the box: %r" % found)

    def test_the_backup_section_is_the_only_thing_that_blocks_a_rebuild(self):
        # Everything else on a box is derived and rebuilds in a minute. The CA cannot
        # be regenerated: losing it means physically revisiting every trusting device.
        self.assertIn("cannot be regenerated", self.text)


class TheCaddyfileMigrationTests(SimpleTestCase):
    """A generated file was committed, and the generator overwrote it in place.

    `deploy/selfhost/Caddyfile.edge` is TRACKED and carries the prose explaining the
    three TLS modes. The bootstrap rendered this box's real terminator config
    straight over it. So every box was permanently dirty from its first bootstrap,
    every `git pull` on every box was blocked -- which is what stopped the Gilead box
    updating, and what box-rebuild.sh correctly refused to force -- and the
    documentation only survived on machines nobody had set up.

    These RUN the migration block out of the real script. `bash -n` is not enough: it
    happily passed a version of this block whose line continuation was a literal
    backslash-n, which bash reads as a command named `n`. Valid syntax, wrong
    behaviour, and only running it tells the two apart.
    """

    HARNESS = """
set -uo pipefail
ok()   {{ echo "OK: $*"; }}
warn() {{ echo "WARN: $*"; }}
HERE="{here}"
REPO="{here}"
CADDYFILE="$HERE/Caddyfile.edge.rendered"
git() {{
  case "$*" in
    *"status --porcelain"*) printf "%s" "{dirty}" ;;
    *) echo "GIT: $*" ;;
  esac
  return {git_rc}
}}
{block}
echo "RENDERED_EXISTS=$([ -f "$CADDYFILE" ] && echo yes || echo no)"
"""

    START = 'LEGACY_CADDY="$HERE/Caddyfile.edge"'
    END = "# --- 1. is the box well enough to change?"
    RENDER_MARKER = "x { reverse_proxy web:10000 }"

    def setUp(self):
        _need_bash(self)
        self.dir = tempfile.mkdtemp(prefix="caddy-mig-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.legacy = pathlib.Path(self.dir) / "Caddyfile.edge"
        self.rendered = pathlib.Path(self.dir) / "Caddyfile.edge.rendered"

    def _block(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        start = text.index(self.START)
        end = text.index(self.END, start)
        return text[start:end]

    def _run(self, git_rc=0, dirty=" M deploy/selfhost/Caddyfile.edge"):
        # `git_rc` only shapes the CHECKOUT result; `dirty` is what status reports.
        script = self.HARNESS.format(
            here=self.dir.replace(chr(92), "/"),
            block=self._block(),
            git_rc=git_rc,
            dirty=dirty,
        )
        proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # A literal backslash-n in the condition surfaces here as a command named n.
        self.assertNotIn("command not found", proc.stderr, proc.stderr)
        return proc.stdout

    def _write_render(self):
        self.legacy.write_text(self.RENDER_MARKER + "\n", encoding="utf-8")

    def test_a_box_holding_a_render_on_the_tracked_path_is_migrated(self):
        self._write_render()
        out = self._run()
        self.assertIn("RENDERED_EXISTS=yes", out)
        self.assertIn("moved this box", out)
        self.assertEqual(
            self.rendered.read_text(encoding="utf-8"), self.RENDER_MARKER + "\n"
        )

    def test_it_restores_the_tracked_template_so_the_box_can_pull(self):
        self._write_render()
        out = self._run()
        self.assertIn("checkout -- deploy/selfhost/Caddyfile.edge", out)
        self.assertIn("can git pull again", out)

    def test_it_copies_BEFORE_it_restores(self):
        # Restoring first would destroy the very thing being migrated.
        self._write_render()
        out = self._run()
        self.assertLess(out.index("moved this box"), out.index("GIT: -C"), out)

    def test_a_failed_restore_warns_instead_of_claiming_success(self):
        self._write_render()
        out = self._run(git_rc=1)
        self.assertIn("WARN:", out)
        self.assertIn("may still be blocked", out)
        # The copy still happened, so the render is safe either way.
        self.assertIn("RENDERED_EXISTS=yes", out)

    def test_an_already_migrated_box_is_left_alone(self):
        self.rendered.write_text("already here\n", encoding="utf-8")
        self._write_render()
        out = self._run()
        self.assertNotIn("moved this box", out)
        self.assertEqual(self.rendered.read_text(encoding="utf-8"), "already here\n")

    def test_a_clean_checkout_is_left_alone(self):
        # Nothing was written over the tracked file, so there is nothing to
        # rescue. The render lands at the new path moments later either way.
        self._write_render()
        out = self._run(dirty="")
        self.assertNotIn("moved this box", out)
        self.assertIn("RENDERED_EXISTS=no", out)

    def test_the_tracked_file_is_still_the_documented_default(self):
        # It is NOT pure prose -- it is a working host-agnostic default, and it
        # legitimately contains reverse_proxy web:10000. That is exactly why the
        # migration asks git whether the file is modified instead of sniffing for a
        # directive: a content sniff also fires on a pristine checkout.
        real = (SELFHOST / "Caddyfile.edge").read_text(encoding="utf-8")
        self.assertIn("WHY THIS FILE EXISTS", real)
        self.assertIn(":443 {", real)

    def test_the_migration_asks_git_rather_than_sniffing_content(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("status --porcelain -- deploy/selfhost/Caddyfile.edge", text)

    def test_compose_mounts_the_rendered_file_not_the_template(self):
        compose = (SELFHOST / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("./Caddyfile.edge.rendered:/etc/caddy/Caddyfile:ro", compose)
        self.assertNotIn("./Caddyfile.edge:/etc/caddy/Caddyfile:ro", compose)

    def test_the_rendered_path_is_gitignored(self):
        # Otherwise the next bootstrap re-dirties the checkout and we are back here.
        ignore = (SELFHOST.parents[1] / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("deploy/selfhost/Caddyfile.edge.rendered", ignore)


class TheTlsProfileMustSurviveAColdStartTests(SimpleTestCase):
    """A box in a TLS mode keeps its terminator behind a compose PROFILE.

    `docker compose up -d` does not start a profiled service. So a rebuild on a box
    that was fully down -- a `compose down`, a disk swap, a stop somebody did on
    purpose -- brought the stack back with no HTTPS at all: :10000 answered, :443
    did not, and the script printed "Done. This box is running its own checkout."
    The claim it makes about the code was true, and the box half worked.

    These RUN the real block out of the real script. The mode is read from the
    box's own .env, and .env files get edited on laptops, quoted by hand, and set
    twice.
    """

    # env_value is the .env parser now, and it sits just above the TLS
    # paragraph, so the block starts there.
    START = "# One reader for every value a box configures"
    END = "printf '%sRunMyCampus box rebuild%s"

    def setUp(self):
        _need_bash(self)
        self.dir = tempfile.mkdtemp(prefix="tls-profile-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _block(self) -> str:
        text = REBUILD.read_text(encoding="utf-8")
        start = text.index(self.START)
        return text[start : text.index(self.END, start)]

    def _run(self, env_text) -> str:
        if env_text is not None:
            (pathlib.Path(self.dir) / ".env").write_bytes(env_text.encode("utf-8"))
        script = (
            "set -uo pipefail\n"
            'HERE="' + self.dir.replace(chr(92), "/") + '"\n'
            "COMPOSE=(echo DOCKER)\n"
            'die() { echo "DIE: $*"; exit 1; }\n'
            + self._block()
            + '\necho "MODE=[$TLS_MODE]"\n'
            + self._up_line()
            + "\n"
        )
        proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def _up_line(self) -> str:
        """The REAL up invocation, lifted out of step 5 -- not one typed here.

        A behavioural test that writes its own `compose up -d` proves the wrapper
        works and nothing at all about whether step 5 calls it. Reverting the fix
        left every one of these green; only the structural test noticed.
        """
        step5 = self._step5()
        start = step5.index("if ! ")
        return step5[start : step5.index(chr(10) + "fi", start) + 3]

    # -- reading the mode out of a real .env ---------------------------------

    def test_a_plain_value_is_read(self):
        self.assertIn("MODE=[lan-mkcert]", self._run("RMC_EDGE_TLS_MODE=lan-mkcert\n"))

    def test_a_quoted_value_is_read(self):
        self.assertIn("MODE=[lan-mkcert]", self._run('RMC_EDGE_TLS_MODE="lan-mkcert"\n'))

    def test_a_crlf_env_does_not_smuggle_a_carriage_return_into_the_mode(self):
        # A trailing CR makes the value compare unequal to "off", so an OFF box
        # would start a terminator it has no certificate for. That is worse than
        # no HTTPS: something binds :443 and presents nothing.
        out = self._run("RMC_EDGE_TLS_MODE=off" + chr(13) + "\n")
        self.assertIn("MODE=[off]", out)
        self.assertNotIn("--profile", out)

    def test_the_last_assignment_wins(self):
        self.assertIn(
            "MODE=[lan-ca]",
            self._run("RMC_EDGE_TLS_MODE=off\nRMC_EDGE_TLS_MODE=lan-ca\n"),
        )

    def test_a_commented_out_line_is_not_read(self):
        self.assertIn("MODE=[]", self._run("#RMC_EDGE_TLS_MODE=lan-ca\n"))

    def test_a_missing_env_is_empty_rather_than_an_error(self):
        self.assertIn("MODE=[]", self._run(None))

    # -- what the mode does to the up ----------------------------------------

    def test_a_tls_box_brings_its_terminator_up_with_the_stack(self):
        self.assertIn(
            "DOCKER --profile tls up -d", self._run("RMC_EDGE_TLS_MODE=lan-mkcert\n")
        )

    def test_an_off_box_does_not_start_a_terminator(self):
        out = self._run("RMC_EDGE_TLS_MODE=off\n")
        self.assertIn("DOCKER up -d", out)
        self.assertNotIn("--profile", out)

    def test_a_box_that_never_set_a_mode_does_not_start_a_terminator(self):
        out = self._run("SOMETHING_ELSE=1\n")
        self.assertIn("DOCKER up -d", out)
        self.assertNotIn("--profile", out)

    # -- structure -----------------------------------------------------------

    def _step5(self) -> str:
        text = REBUILD.read_text(encoding="utf-8")
        return text[text.index("--- 5. swap the containers") : text.index("--- 6.")]

    def test_step_five_goes_through_the_profile_aware_wrapper(self):
        step5 = self._step5()
        self.assertIn("compose up -d", step5)
        self.assertNotIn('"${COMPOSE[@]}" up -d', step5)

    def test_a_terminator_that_will_not_start_fails_the_run(self):
        # A warning is not enough. An operator who reads "Done" walks away.
        step5 = self._step5()
        self.assertIn("ps -q edge-tls", step5)
        self.assertIn("die ", step5[step5.index("ps -q edge-tls") :])


class TheAuditMustReadTheFileComposeMountsTests(SimpleTestCase):
    """The audit read the tracked TEMPLATE and failed a healthy box.

    Moving the render to Caddyfile.edge.rendered left section D pointed at
    deploy/selfhost/Caddyfile.edge -- which is tracked, host-agnostic, opens with a
    bare `{` and carries no trust exemption. On the Gilead box that printed:

        [FAIL] site line is '{' -- an IP client gets NO certificate
        [FAIL] rendered Caddyfile has no trust exemption -- re-run edge-bootstrap.sh
        VERDICT: do NOT rebuild until the FAILs above are understood.

    while three live probes in the same section returned 200 and the terminator was
    serving the right certificate. Both FAILs were the audit's own, and it told an
    operator to stop working on a box that was fine.

    These RUN the block against real files on disk.
    """

    START = 'CADDY_RENDERED="$HERE/Caddyfile.edge.rendered"'
    END = "for u in http://127.0.0.1/edge/trust/"

    GOOD = ":443 {\n  handle @trust {\n    reverse_proxy web:10000\n  }\n}\n"

    def setUp(self):
        _need_bash(self)
        self.dir = tempfile.mkdtemp(prefix="audit-caddy-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _template(self) -> str:
        """The real tracked file -- the thing that was being read by mistake."""
        return (SELFHOST / "Caddyfile.edge").read_text(encoding="utf-8")

    def _run(self, rendered=None, legacy=None) -> str:
        d = pathlib.Path(self.dir)
        if rendered is not None:
            (d / "Caddyfile.edge.rendered").write_text(rendered, encoding="utf-8")
        if legacy is not None:
            (d / "Caddyfile.edge").write_text(legacy, encoding="utf-8")
        text = AUDIT.read_text(encoding="utf-8")
        block = text[text.index(self.START) : text.index(self.END)]
        here = self.dir.replace(chr(92), "/")
        script = (
            "set -uo pipefail\n"
            'HERE="' + here + '"\n'
            'REPO_ROOT="' + here + '"\n'
            'ok()   { echo "OK: $*"; }\n'
            'bad()  { echo "FAIL: $*"; }\n'
            'warn() { echo "WARN: $*"; }\n'
            + block
        )
        proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_a_correct_render_passes_both_checks(self):
        out = self._run(rendered=self.GOOD)
        self.assertIn("OK: site line is the catch-all :443", out)
        self.assertIn("OK: the rendered Caddyfile carries the trust exemption", out)
        self.assertNotIn("FAIL:", out)

    def test_the_pristine_template_is_ignored_when_a_render_exists(self):
        # The regression, precisely: both files present, and it must read the render.
        out = self._run(rendered=self.GOOD, legacy=self._template())
        self.assertNotIn("FAIL:", out)
        self.assertNotIn("site line is '{'", out)

    def test_a_pristine_template_alone_is_a_clear_failure_not_a_baffling_one(self):
        # No render anywhere. The old code reported the template's first character as
        # if it were a site address; an operator cannot act on "site line is '{'".
        out = self._run(legacy=self._template())
        self.assertIn("no rendered Caddyfile", out)
        self.assertNotIn("site line is '{'", out)

    def test_a_box_that_has_not_migrated_reads_its_legacy_render_and_says_so(self):
        # Its render is still written over the tracked path. Reading it is correct;
        # staying quiet about it would hide why that box cannot git pull.
        out = self._run(legacy=self.GOOD)
        self.assertIn("OK: site line is the catch-all :443", out)
        self.assertIn("WARN:", out)
        self.assertIn("tracked path", out)

    def test_a_render_whose_site_line_names_addresses_is_still_caught(self):
        out = self._run(rendered="gilead-tech.local:443 {\n  handle @trust {}\n}\n")
        self.assertIn("FAIL: site line is 'gilead-tech.local:443 {'", out)

    def test_a_render_missing_the_trust_exemption_is_still_caught(self):
        out = self._run(rendered=":443 {\n  reverse_proxy web:10000\n}\n")
        self.assertIn("FAIL: rendered Caddyfile has no trust exemption", out)

    def test_comments_and_blank_lines_do_not_become_the_site_line(self):
        out = self._run(rendered="# rendered by edge-bootstrap\n\n" + self.GOOD)
        self.assertIn("OK: site line is the catch-all :443", out)

    def test_it_names_which_file_it_read(self):
        # Two candidate paths and a verdict that stops work: say which one was read.
        self.assertIn("terminator config:", self._run(rendered=self.GOOD))

    def test_no_grep_in_the_block_reads_a_hardcoded_path(self):
        # The invariant, stated properly: every read of the terminator config goes
        # through a CADDY_ variable, so there is no second place to forget when the
        # path moves again. An earlier version of this test counted occurrences and
        # miscounted -- the -z guard reads the variable too.
        text = AUDIT.read_text(encoding="utf-8")
        block = text[text.index(self.START) : text.index(self.END)]
        greps = [
            ln.strip()
            for ln in block.splitlines()
            if "grep" in ln and not ln.strip().startswith("#")
        ]
        self.assertTrue(greps, block)
        for ln in greps:
            self.assertIn("$CADDY_", ln, ln)
            self.assertNotIn("deploy/selfhost/", ln, ln)


# --- the second trap: "Done" answers a narrower question than the one asked ----


def _need_git_and_timeout(case):
    _need_bash(case)
    probe = subprocess.run(
        ["bash", "-c", "command -v git >/dev/null && command -v timeout >/dev/null"],
        capture_output=True,
    )
    if probe.returncode != 0:
        case.skipTest("these run the real git paths; bash needs git and timeout")


def _section(first: str, last: str, path=None) -> str:
    """Lift a contiguous run of a real box script, from one whole line to another.

    Whole lines, not substrings: every one of these anchors also appears inside the
    scripts' own prose, and a boundary that can drift into a comment is a test that
    quietly starts asserting about nothing.
    """
    lines = (path or REBUILD).read_text(encoding="utf-8").splitlines()
    i = lines.index(first)
    j = lines.index(last, i)
    return "\n".join(lines[i : j + 1]) + "\n"


def _posix(path) -> str:
    return str(path).replace(chr(92), "/")


def _git(*args, cwd=None):
    return subprocess.run(
        [
            "git",
            "-c", "user.email=t@t.com",
            "-c", "user.name=t",
            "-c", "init.defaultBranch=main",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        cwd=None if cwd is None else str(cwd),
        capture_output=True,
        text=True,
    )


class TheSummaryMustSayWhetherTheCodeIsCurrentTests(SimpleTestCase):
    """Step 7 proves the image matches the CHECKOUT. Nobody asked that question.

    Somebody typing `box-rebuild.sh` is asking for the latest CODE. The two answers
    coincide only when the checkout itself reached the remote, and step 3 is the only
    place that can know.

    MEASURED on the Gilead box on 2026-08-28. The fetch failed for want of a stored
    credential. The script warned, correctly built the code already on disk, and then
    -- eight minutes of build log later -- printed "Done. This box is running its own
    checkout." Every word of that is true. It was read as "updated", and the next
    command typed was a management-command flag that exists only in the commit which
    never arrived: `unrecognized arguments: --explain`.

    A warning that scrolled past before a long build is not a caveat anyone still
    has on screen. So the verdict has to survive to the summary.

    These RUN the real blocks against real git repositories. A test that only read
    the source would have stayed green through the entire episode above.
    """

    STEP3 = ('step "Update the checkout"', "bar 3")
    SUMMARY = (
        "# THE SUMMARY MUST NOT FORGET STEP 3. This is where somebody decides whether to",
        "fi",
    )

    def setUp(self):
        _need_git_and_timeout(self)
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="box-upstream-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.origin = self.dir / "origin.git"
        self.repo = self.dir / "repo"
        _git("init", "-q", "--bare", _posix(self.origin))
        _git("clone", "-q", _posix(self.origin), _posix(self.repo))
        _git("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.repo)
        (self.repo / "a.txt").write_text("one\n", encoding="utf-8")
        _git("add", "a.txt", cwd=self.repo)
        _git("commit", "-qm", "one", cwd=self.repo)
        push = _git("push", "-q", "-u", "origin", "main", cwd=self.repo)
        self.assertEqual(push.returncode, 0, push.stderr)

    # -- fixtures ------------------------------------------------------------

    def _head(self, cwd=None):
        return _git("rev-parse", "HEAD", cwd=cwd or self.repo).stdout.strip()

    def _advance_origin(self):
        """Put a commit on origin that the checkout does not have."""
        other = self.dir / "other"
        _git("clone", "-q", _posix(self.origin), _posix(other))
        _git("commit", "-q", "--allow-empty", "-m", "remote work", cwd=other)
        push = _git("push", "-q", "origin", "HEAD:main", cwd=other)
        self.assertEqual(push.returncode, 0, push.stderr)

    def _go_offline(self):
        _git("remote", "set-url", "origin", _posix(self.dir / "gone.git"), cwd=self.repo)

    # -- running the real blocks ---------------------------------------------

    _SHIMS = (
        "set -uo pipefail\n"
        'B=""; N=""; G=""; Y=""\n'
        "step() { printf '[step] %s\\n' \"$*\"; }\n"
        "ok()   { printf '  OK   %s\\n' \"$*\"; }\n"
        "warn() { printf '  WARN %s\\n' \"$*\"; }\n"
        "bar()  { :; }\n"
        "short() { printf '%.9s' \"$1\"; }\n"
        'checkout_commit() { git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null; }\n'
        'HERE="/srv/rmc/deploy/selfhost"\n'
    )

    def _run_step3(self, do_pull=1):
        script = (
            self._SHIMS
            + 'REPO_ROOT="' + _posix(self.repo) + '"\n'
            + "DO_PULL=" + str(do_pull) + "\n"
            # Step 3 reads this now. Omitting it puts the fetch subshell into
            # `set -u` and the failure reads as a broken remote.
            + 'FETCH_BUDGET="300"\n'
            + 'HEAD_COMMIT="$(checkout_commit)"\n'
            + _section(*self.STEP3)
            + 'printf "\\nUPSTREAM=[%s]\\nNOTE=[%s]\\nHEAD=[%s]\\n"'
            + ' "$UPSTREAM" "$CHECKOUT_NOTE" "$HEAD_COMMIT"\n'
        )
        proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def _run_summary(self, upstream="", note="", branch="main"):
        script = (
            self._SHIMS
            + 'REPO_ROOT="/srv/rmc"\n'
            + 'AFTER_COMMIT="102e0e510ee2edb4f2426ce176f27ba13bb40646"\n'
            + 'UPSTREAM="' + upstream + '"\n'
            + 'CHECKOUT_NOTE="' + note + '"\n'
            + 'BRANCH="' + branch + '"\n'
            + _section(*self.SUMMARY)
        )
        proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    # -- step 3 establishes the verdict, or says it could not ----------------

    def test_a_checkout_already_level_with_origin_is_confirmed(self):
        out = self._run_step3()
        self.assertIn("UPSTREAM=[level]", out)
        self.assertIn("already level with origin/main", out)

    def test_a_checkout_that_fast_forwards_is_confirmed_and_moves(self):
        was = self._head()
        self._advance_origin()
        out = self._run_step3()
        self.assertIn("UPSTREAM=[advanced]", out)
        # The build stamps $HEAD_COMMIT, so a fast-forward that did not update it
        # would bake the new code under the old commit's name.
        self.assertNotIn("HEAD=[%s]" % was, out)
        self.assertIn("HEAD=[%s]" % self._head(), out)

    def test_being_offline_leaves_the_verdict_unestablished(self):
        # Offline is the NORMAL state for a box in a school. It must not become a
        # failure -- and it must not become a silent success either.
        self._go_offline()
        out = self._run_step3()
        self.assertIn("UPSTREAM=[]", out)
        # What it says about WHY is git's business now, not this script's. The
        # guarantee under test here is only that the verdict stays unestablished
        # and a reason is recorded; TheFetchMustReportWhatHappenedRatherThanGuess
        # owns the wording.
        self.assertIn("In git's own words", out)
        self.assertNotIn("UPSTREAM=[level]", out)

    def test_a_dirty_checkout_leaves_the_verdict_unestablished(self):
        (self.repo / "a.txt").write_text("edited\n", encoding="utf-8")
        out = self._run_step3()
        self.assertIn("UPSTREAM=[]", out)
        self.assertIn("uncommitted changes", out)

    def test_no_pull_leaves_the_verdict_unestablished(self):
        out = self._run_step3(do_pull=0)
        self.assertIn("UPSTREAM=[]", out)
        self.assertIn("--no-pull", out)

    def test_a_diverged_checkout_leaves_the_verdict_unestablished(self):
        self._advance_origin()
        _git("commit", "-q", "--allow-empty", "-m", "local work", cwd=self.repo)
        out = self._run_step3()
        self.assertIn("UPSTREAM=[]", out)
        self.assertIn("diverged", out)

    def test_every_unestablished_path_says_which_one_it_was(self):
        # "Not updated" with no reason is a dead end for whoever has to fix it, and
        # the four reasons need four different actions.
        self._go_offline()
        offline = self._run_step3()
        nopull = self._run_step3(do_pull=0)
        for out in (offline, nopull):
            note = out.split("NOTE=[", 1)[1].split("]", 1)[0]
            self.assertTrue(note.strip(), out)

    # -- the summary reads it back -------------------------------------------

    def test_a_confirmed_checkout_is_reported_as_up_to_date(self):
        out = self._run_summary(upstream="level")
        self.assertIn("Up to date", out)
        self.assertIn("origin/main", out)
        self.assertNotIn("NOT updated", out)

    def test_an_unconfirmed_checkout_is_told_so_plainly(self):
        out = self._run_summary(note="the git remote could not be reached")
        self.assertIn("The checkout was NOT updated", out)
        self.assertIn("the git remote could not be reached", out)
        self.assertIn("has NOT been established", out)
        self.assertNotIn("Up to date", out)

    def test_an_unconfirmed_checkout_is_handed_the_next_command(self):
        # The operator on the box is not going to derive this, and the whole failure
        # is that they walked away instead.
        out = self._run_summary(note="offline")
        self.assertIn("fetch origin", out)
        self.assertIn("status -sb", out)

    def test_a_path_that_sets_no_note_still_does_not_claim_currency(self):
        # A future branch added to step 3 that forgets CHECKOUT_NOTE must degrade to
        # "unknown", never to "current". Empty is not evidence of being up to date.
        out = self._run_summary()
        self.assertIn("NOT updated", out)
        self.assertNotIn("Up to date", out)
        self.assertNotIn("--  .", out)

    def test_the_summary_reads_step_threes_variable_rather_than_a_constant(self):
        # Behavioural tests above drive $UPSTREAM directly, so they would all pass on
        # a summary that step 3 no longer feeds. This is the wire between them.
        block = _section(*self.SUMMARY)
        self.assertIn('if [ -n "$UPSTREAM" ]; then', block)
        step3 = _section(*self.STEP3)
        self.assertIn('UPSTREAM="level"', step3)
        self.assertIn('UPSTREAM="advanced"', step3)

    def test_the_summary_is_the_last_thing_printed_before_the_next_steps(self):
        text = REBUILD.read_text(encoding="utf-8")
        self.assertLess(text.index("$UPSTREAM"), text.index("Next, if TLS or trust changed"))


class TheCheckMustAskTheRemoteWithoutTouchingAnythingTests(SimpleTestCase):
    """`--check` is the command for "is this box current?", and it knew half the answer.

    The image can match the checkout perfectly while the CHECKOUT sits commits behind
    origin -- and CURRENT invited the operator to skip the rebuild that would not have
    moved it anyway. So it asks the remote too, read-only: --check promises to change
    NOTHING, and a fetch writes remote-tracking refs.
    """

    BLOCK = ('if [ "$CHECK_ONLY" = "1" ]; then', "fi")

    def setUp(self):
        _need_git_and_timeout(self)
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="box-check-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.origin = self.dir / "origin.git"
        self.repo = self.dir / "repo"
        _git("init", "-q", "--bare", _posix(self.origin))
        _git("clone", "-q", _posix(self.origin), _posix(self.repo))
        _git("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.repo)
        (self.repo / "a.txt").write_text("one\n", encoding="utf-8")
        _git("add", "a.txt", cwd=self.repo)
        _git("commit", "-qm", "one", cwd=self.repo)
        _git("push", "-q", "-u", "origin", "main", cwd=self.repo)

    def _run(self, drifted=0):
        script = (
            "set -uo pipefail\n"
            'G=""; N=""; Y=""\n'
            "CHECK_ONLY=1\n"
            "ok()   { printf '  OK   %s\\n' \"$*\"; }\n"
            "warn() { printf '  WARN %s\\n' \"$*\"; }\n"
            "short() { printf '%.9s' \"$1\"; }\n"
            'HERE="/srv/rmc/deploy/selfhost"\n'
            'REPO_ROOT="' + _posix(self.repo) + '"\n'
            + 'HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"\n'
            + "DRIFTED=" + str(drifted) + "\n"
            + _section(*self.BLOCK)
        )
        proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        return proc.returncode, proc.stdout

    def _advance_origin(self):
        other = self.dir / "other"
        _git("clone", "-q", _posix(self.origin), _posix(other))
        _git("commit", "-q", "--allow-empty", "-m", "remote work", cwd=other)
        _git("push", "-q", "origin", "HEAD:main", cwd=other)

    def test_a_checkout_level_with_origin_reports_current_and_says_so(self):
        rc, out = self._run()
        self.assertEqual(rc, 0, out)
        self.assertIn("CURRENT", out)
        self.assertIn("level", out)

    def test_a_checkout_behind_origin_is_not_current(self):
        # The failure this closes: image == checkout, so the old --check said CURRENT
        # while the box ran code three commits old.
        self._advance_origin()
        rc, out = self._run()
        self.assertEqual(rc, 1, out)
        self.assertIn("BEHIND", out)
        self.assertNotIn("CURRENT", out)

    def test_a_checkout_behind_origin_is_told_a_rebuild_alone_will_not_fix_it(self):
        self._advance_origin()
        _rc, out = self._run()
        self.assertIn("pull", out)

    def test_image_drift_is_reported_ahead_of_checkout_drift(self):
        # Both are true at once on a neglected box. Naming the one a rebuild fixes
        # first is the order that gets somebody unstuck.
        self._advance_origin()
        rc, out = self._run(drifted=1)
        self.assertEqual(rc, 1, out)
        self.assertIn("DRIFTED", out)
        self.assertNotIn("BEHIND --", out)

    def test_an_unreachable_remote_is_not_a_failure(self):
        # Boxes in schools are offline for days. Exiting non-zero here would make
        # --check useless exactly where this product is deployed.
        _git("remote", "set-url", "origin", _posix(self.dir / "gone.git"), cwd=self.repo)
        rc, out = self._run()
        self.assertEqual(rc, 0, out)
        self.assertIn("CURRENT", out)
        self.assertIn("NOT checked", out)

    def test_an_unreachable_remote_never_hangs_on_a_credential_prompt(self):
        block = _section(*self.BLOCK)
        self.assertIn("GIT_TERMINAL_PROMPT=0", block)
        self.assertIn("timeout ", block)

    def test_check_reads_the_remote_without_writing_to_git(self):
        # `ls-remote` writes nothing; `fetch` writes remote-tracking refs. --check
        # documents itself as changing NOTHING, and that has to include .git.
        # Comment lines out first: this block's own prose explains WHY it does not
        # fetch, and a naive substring search would fail on the explanation.
        code = re.sub(r"(?m)^\s*#.*$", "", _section(*self.BLOCK))
        self.assertIn("ls-remote", code)
        self.assertNotIn("fetch", code)
        self.assertNotIn("merge", code)


class TheHelpTextMustSurviveAnEditedHeaderTests(SimpleTestCase):
    """`sed -n '2,28p'` meant "the header" only while the header was 28 lines long."""

    def test_help_prints_the_whole_header_and_no_shell_code(self):
        _need_bash(self)
        proc = subprocess.run(
            ["bash", str(REBUILD), "--help"], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Rebuild this box onto the code in its own checkout", proc.stdout)
        self.assertIn("--no-pull", proc.stdout)
        # The first line of code after the header. Seeing it means the range ran on.
        self.assertNotIn("set -uo pipefail", proc.stdout)
        self.assertNotIn("BASH_SOURCE", proc.stdout)

    def test_the_range_is_anchored_to_a_marker_not_a_line_number(self):
        text = REBUILD.read_text(encoding="utf-8")
        help_line = [ln for ln in text.splitlines() if "--help)" in ln][0]
        self.assertNotIn("2,28p", help_line)
        self.assertIn("set -uo pipefail", help_line)


class TheFetchMustReportWhatHappenedRatherThanGuessTests(SimpleTestCase):
    """The script held git's own error message and sent it to /dev/null.

    It then warned "could not reach the git remote (offline, or no stored
    credential)" -- two causes, neither measured. On the Gilead box on 2026-08-28
    both were false: `git ls-remote origin refs/heads/main` answered from that same
    checkout, over that same URL, with no prompt, returning the sha origin really
    was at. The operator was handed a guess, and the guess pointed at the network.

    A fetch stopped by `timeout` is a third outcome and the likeliest one on a box:
    a school link and a repo this size do not finish in sixty seconds, and rc 124 is
    a fetch that was working when it was killed. It has a different remedy, so it
    gets a different message -- and the budget stopped being a hardcoded number.
    """

    STEP3 = ('step "Update the checkout"', "bar 3")
    BUDGET = (
        "# One reader for every value a box configures in its own .env. The last assignment",
        "esac",
    )

    def setUp(self):
        _need_git_and_timeout(self)
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="box-fetch-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.origin = self.dir / "origin.git"
        self.repo = self.dir / "repo"
        _git("init", "-q", "--bare", _posix(self.origin))
        _git("clone", "-q", _posix(self.origin), _posix(self.repo))
        _git("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.repo)
        (self.repo / "a.txt").write_text("one\n", encoding="utf-8")
        _git("add", "a.txt", cwd=self.repo)
        _git("commit", "-qm", "one", cwd=self.repo)
        _git("push", "-q", "-u", "origin", "main", cwd=self.repo)

    _SHIMS = (
        "set -uo pipefail\n"
        'B=""; N=""; G=""; Y=""\n'
        "step() { printf '[step] %s\\n' \"$*\"; }\n"
        "ok()   { printf '  OK   %s\\n' \"$*\"; }\n"
        "warn() { printf '  WARN %s\\n' \"$*\"; }\n"
        "bar()  { :; }\n"
        "short() { printf '%.9s' \"$1\"; }\n"
        'checkout_commit() { git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null; }\n'
        'HERE="/srv/rmc/deploy/selfhost"\n'
    )

    def _run_step3(self, prelude="", budget="300"):
        script = (
            self._SHIMS
            + 'REPO_ROOT="' + _posix(self.repo) + '"\n'
            + "DO_PULL=1\n"
            + 'FETCH_BUDGET="' + budget + '"\n'
            + prelude
            + 'HEAD_COMMIT="$(checkout_commit)"\n'
            + _section(*self.STEP3)
            + 'printf "\\nNOTE=[%s]\\nUPSTREAM=[%s]\\n" "$CHECKOUT_NOTE" "$UPSTREAM"\n'
        )
        proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def _resolve_budget(self, env=None, dotenv=None):
        """Run the real resolution, with a real .env, exactly as the script does."""
        if dotenv is not None:
            (self.dir / ".env").write_bytes(dotenv.encode("utf-8"))
        script = (
            "set -uo pipefail\n"
            'HERE="' + _posix(self.dir) + '"\n'
            + _section(*self.BUDGET)
            + 'printf "BUDGET=[%s]\\n" "$FETCH_BUDGET"\n'
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.split("BUDGET=[", 1)[1].split("]", 1)[0]

    # -- the three outcomes, told apart --------------------------------------

    def test_a_stopped_fetch_is_not_reported_as_an_outage(self):
        # rc 124 is `timeout` killing a fetch that was working. Calling that an
        # unreachable remote sends somebody to check a network that is fine.
        out = self._run_step3(prelude="timeout() { return 124; }\n", budget="45")
        self.assertIn("still running after 45s", out)
        self.assertNotIn("could not reach", out)
        self.assertIn("slow link, not an outage", out)

    def test_a_stopped_fetch_says_how_to_give_it_longer(self):
        out = self._run_step3(prelude="timeout() { return 124; }\n")
        self.assertIn("RMC_GIT_FETCH_TIMEOUT=", out)

    def test_a_failed_fetch_prints_gits_own_message(self):
        _git("remote", "set-url", "origin", _posix(self.dir / "nope.git"), cwd=self.repo)
        out = self._run_step3()
        self.assertIn("In git's own words", out)
        self.assertIn("does not appear to be a git repository", out)
        self.assertIn("exit 128", out)

    def test_a_failed_fetch_names_no_cause_it_did_not_measure(self):
        # The exact string that was wrong on the box. It survives in the comments
        # that explain why it went, so the executable text is what is checked.
        code = re.sub(r"(?m)^\s*#.*$", "", REBUILD.read_text(encoding="utf-8"))
        self.assertNotIn("offline, or no stored credential", code)

    def test_a_working_fetch_is_untouched_by_any_of_this(self):
        out = self._run_step3()
        self.assertIn("UPSTREAM=[level]", out)
        self.assertIn("NOTE=[]", out)

    # -- the budget is configured, not hardcoded ------------------------------

    def test_the_default_is_no_longer_the_sixty_that_failed(self):
        self.assertEqual(self._resolve_budget(dotenv=""), "300")

    def test_the_box_env_file_can_raise_it(self):
        self.assertEqual(
            self._resolve_budget(dotenv="RMC_GIT_FETCH_TIMEOUT=1200\n"), "1200"
        )

    def test_the_environment_beats_the_env_file(self):
        # Somebody standing at the box needs to override it for one run without
        # editing a file the next bootstrap will rewrite.
        got = self._resolve_budget(
            env={"RMC_GIT_FETCH_TIMEOUT": "900"},
            dotenv="RMC_GIT_FETCH_TIMEOUT=1200\n",
        )
        self.assertEqual(got, "900")

    def test_a_nonsense_value_falls_back_instead_of_choking_timeout(self):
        # `timeout 5min` is a usage error, and a usage error here would abort the
        # rebuild over a typo in a config file.
        self.assertEqual(self._resolve_budget(dotenv="RMC_GIT_FETCH_TIMEOUT=5min\n"), "300")
        self.assertEqual(self._resolve_budget(dotenv="RMC_GIT_FETCH_TIMEOUT=\n"), "300")

    def test_a_crlf_env_does_not_smuggle_a_carriage_return_into_the_budget(self):
        # A trailing CR makes the value non-numeric, which the guard catches -- but
        # it would silently become 300 on a box that asked for 1200.
        self.assertEqual(
            self._resolve_budget(dotenv="RMC_GIT_FETCH_TIMEOUT=1200\r\n"), "1200"
        )

    def test_the_tls_mode_reads_through_the_same_reader(self):
        # Two hand-rolled awk parsers drift. The .env behaviours asserted for the TLS
        # mode -- quotes, CRLF, last-wins, commented-out -- are this one function now.
        text = REBUILD.read_text(encoding="utf-8")
        self.assertIn("edge_tls_mode() { env_value RMC_EDGE_TLS_MODE; }", text)


class TheAuditMustNotCallAStaleRefCurrentTests(SimpleTestCase):
    """`box-audit.sh` printed "[ OK ] level with origin/main" on a box that was behind.

    Section A ran `git fetch`, threw the exit status away, and compared HEAD against
    whatever origin/main was sitting in .git. On a box that fetched successfully last
    week and has been offline since, that ref is last week's, HEAD matches it, and the
    audit reports a green PASS about a comparison it never made.

    REPRODUCED, not reasoned about: box level and fetched, cloud moves one commit on,
    box loses its remote, old code says "[ OK ] level with origin/main". That was the
    Gilead box's state on 2026-08-28, and the audit is the command somebody runs to
    decide whether the box is fine.

    It asks for the TIP now rather than for the objects. A fetch pulls the whole delta
    -- minutes, on this repo over a school link -- so it needs a timeout, and then a
    slow link reads as an unreachable remote. Measured on the same box: `ls-remote`
    answered that URL while `fetch` did not finish. It also writes nothing, which an
    audit should not be doing at all.
    """

    BLOCK = ('branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"', "fi")

    def setUp(self):
        _need_git_and_timeout(self)
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="box-audit-a-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.origin = self.dir / "origin.git"
        self.repo = self.dir / "repo"
        _git("init", "-q", "--bare", _posix(self.origin))
        _git("clone", "-q", _posix(self.origin), _posix(self.repo))
        _git("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.repo)
        (self.repo / "a.txt").write_text("one\n", encoding="utf-8")
        _git("add", "a.txt", cwd=self.repo)
        _git("commit", "-qm", "one", cwd=self.repo)
        push = _git("push", "-q", "-u", "origin", "main", cwd=self.repo)
        self.assertEqual(push.returncode, 0, push.stderr)
        # The box has fetched successfully at least once -- which is what leaves the
        # ref on disk that the old code went on to trust.
        _git("fetch", "origin", "--quiet", cwd=self.repo)

    def _cloud_moves_on(self, branch="main"):
        other = self.dir / "other"
        if not other.exists():
            _git("clone", "-q", _posix(self.origin), _posix(other))
        _git("commit", "-q", "--allow-empty", "-m", "cloud work", cwd=other)
        push = _git("push", "-q", "origin", "HEAD:" + branch, cwd=other)
        self.assertEqual(push.returncode, 0, push.stderr)

    def _go_offline(self):
        _git("remote", "set-url", "origin", _posix(self.dir / "gone.git"), cwd=self.repo)

    def _run(self):
        script = (
            "set -uo pipefail\n"
            "ok()   { printf '  [ OK ] %s\\n' \"$*\"; }\n"
            "warn() { printf '  [WARN] %s\\n' \"$*\"; }\n"
            + _section(*self.BLOCK, path=AUDIT)
        )
        proc = subprocess.run(
            ["bash", "-c", script], cwd=str(self.repo), capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_a_checkout_level_with_a_reachable_origin_is_reported_as_level(self):
        out = self._run()
        self.assertIn("[ OK ]", out)
        self.assertIn("level with origin/main", out)

    def test_an_unreachable_remote_is_never_reported_as_level(self):
        # THE BUG. The stale ref matches HEAD, so the comparison "succeeds" and says
        # the opposite of the truth.
        self._cloud_moves_on()
        self._go_offline()
        out = self._run()
        self.assertNotIn("[ OK ]", out)
        self.assertIn("could not reach the git remote", out)
        self.assertIn("cannot tell", out)

    def test_the_stale_ref_really_would_have_said_level(self):
        # Proves the fixture reproduces the defect rather than merely exercising the
        # fix -- without this, the test above could pass on any fixture at all.
        self._cloud_moves_on()
        self._go_offline()
        head = _git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        stale = _git("rev-parse", "origin/main", cwd=self.repo).stdout.strip()
        self.assertEqual(head, stale, "the fixture does not reproduce the stale ref")
        remote = _git("ls-remote", _posix(self.origin), "refs/heads/main").stdout.split()[0]
        self.assertNotEqual(head, remote, "the cloud did not actually move on")

    def test_a_checkout_behind_an_origin_it_has_fetched_says_how_far(self):
        self._cloud_moves_on()
        self._cloud_moves_on()
        _git("fetch", "origin", "--quiet", cwd=self.repo)
        out = self._run()
        self.assertIn("behind origin/main by 2 commit(s)", out)

    def test_a_checkout_that_has_not_fetched_does_not_invent_a_distance(self):
        # The count needs the objects, and the objects need a fetch. Naming a number
        # it could not compute is exactly how this section went wrong before.
        self._cloud_moves_on()
        out = self._run()
        self.assertIn("behind origin/main", out)
        self.assertIn("not in this checkout yet", out)
        self.assertNotIn("commit(s)", out)

    def test_a_branch_the_remote_does_not_have_is_not_an_unreachable_remote(self):
        # The remote answered. Reporting that as an outage sends somebody to check a
        # network that is working.
        _git("checkout", "-q", "-b", "never-pushed", cwd=self.repo)
        out = self._run()
        self.assertIn("origin has no branch 'never-pushed'", out)
        self.assertNotIn("could not reach", out)
        self.assertNotIn("[ OK ]", out)

    def test_the_branch_is_read_rather_than_assumed_to_be_main(self):
        # A box on any other branch was being measured against a ref that says
        # nothing about it.
        _git("checkout", "-q", "-b", "boxline", cwd=self.repo)
        push = _git("push", "-q", "-u", "origin", "boxline", cwd=self.repo)
        self.assertEqual(push.returncode, 0, push.stderr)
        out = self._run()
        self.assertIn("origin/boxline", out)
        self.assertNotIn("origin/main", out)

    def test_the_audit_does_not_fetch_at_all(self):
        # An audit runs to decide whether a rebuild is safe. Writing remote-tracking
        # refs while answering that is both unnecessary and slow.
        code = re.sub(r"(?m)^\s*#.*$", "", AUDIT.read_text(encoding="utf-8"))
        self.assertNotIn("git fetch", code)
        self.assertIn("ls-remote", code)

    def test_the_audit_cannot_hang_waiting_for_a_credential(self):
        # A prompt nobody is there to answer is an audit that never finishes.
        code = _section(*self.BLOCK, path=AUDIT)
        self.assertIn("GIT_TERMINAL_PROMPT=0", code)
        self.assertIn("timeout 30", code)
