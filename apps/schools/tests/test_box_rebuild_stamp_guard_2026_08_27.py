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

    START = "# The TLS terminator runs behind a compose PROFILE"
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
