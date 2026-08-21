"""A box must be able to say what code it is running.

The self-hosted appliance answered ``/-/version/`` with
``{"commit_sha": "unknown", "build_time": "unknown", "environment": "unknown"}``
because the resolver read deploy environment variables ONLY, and nothing in
``deploy/`` ever set one. Two things followed from that, neither of them obvious:

* nobody -- operator or support engineer -- could tell which code a box was on,
  so every bug report from a self-hosted site started with a guess; and
* ``resolve_deploy_commit_sha()`` was permanently ``unknown``, which is the value
  the post-deploy cache-buster stamps into ``<meta name="rmc-deploy-sha">``. With
  it inert, a browser had nothing to notice a stale shell by, so an upgraded box
  kept serving the old one.

These tests are DB-free (``SimpleTestCase``) so they run without the shared test
database.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.siteconfig import deploy_meta

REPO_ROOT = Path(deploy_meta.__file__).resolve().parents[2]

VALID_SHA = "e194771fd270a475e18cf7c85e3b6e2cffc85ebc"
OTHER_SHA = "0123456789abcdef0123456789abcdef01234567"


class DeployMetaTestBase(SimpleTestCase):
    """Isolate every cached file read and the whole environment."""

    def setUp(self):
        super().setUp()
        deploy_meta.reset_deploy_meta_caches()
        self.addCleanup(deploy_meta.reset_deploy_meta_caches)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def use_isolated_root(self):
        """Point the resolver at an empty directory: no stamp, no .git."""
        patcher = patch.object(deploy_meta, "_REPO_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_stamp(self, payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        (self.root / deploy_meta.BUILD_STAMP_FILENAME).write_text(
            text, encoding="utf-8"
        )

    def write_git_dir(self, head: str, refs: dict | None = None, packed: str = ""):
        git_dir = self.root / ".git"
        git_dir.mkdir(exist_ok=True)
        (git_dir / "HEAD").write_text(head, encoding="utf-8")
        for ref, sha in (refs or {}).items():
            target = git_dir / ref
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(sha, encoding="utf-8")
        if packed:
            (git_dir / "packed-refs").write_text(packed, encoding="utf-8")
        return git_dir


class AnExplicitCommitEnvVarWinsTests(DeployMetaTestBase):
    def test_render_commit_is_reported_verbatim(self):
        self.use_isolated_root()
        with patch.dict(os.environ, {"RENDER_GIT_COMMIT": VALID_SHA}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), VALID_SHA)

    def test_short_form_truncates_to_twelve(self):
        self.use_isolated_root()
        with patch.dict(os.environ, {"GIT_COMMIT": VALID_SHA}, clear=True):
            self.assertEqual(
                deploy_meta.resolve_deploy_commit_sha(short=True), VALID_SHA[:12]
            )

    def test_env_beats_a_stamp_that_says_something_else(self):
        self.use_isolated_root()
        self.write_stamp({"commit_sha": OTHER_SHA})
        with patch.dict(os.environ, {"RENDER_GIT_COMMIT": VALID_SHA}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), VALID_SHA)

    def test_first_key_in_precedence_order_wins(self):
        self.use_isolated_root()
        env = {"RENDER_GIT_COMMIT": VALID_SHA, "GIT_COMMIT": OTHER_SHA}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), VALID_SHA)


class AMalformedCommitEnvVarDoesNotFallThroughTests(DeployMetaTestBase):
    """A declared-but-invalid commit is a config error, not a cue to guess.

    Falling through to the stamp or to ``.git`` would answer a different question
    from the one asked. Post-deploy smoke compares this value against the commit
    it MEANT to ship, so a confident wrong answer is worse than ``unknown``.
    """

    def test_garbage_env_reports_unknown_even_with_a_good_stamp(self):
        self.use_isolated_root()
        self.write_stamp({"commit_sha": OTHER_SHA})
        with patch.dict(os.environ, {"RENDER_GIT_COMMIT": "not a sha"}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), "unknown")

    def test_garbage_env_reports_unknown_even_with_a_real_git_dir(self):
        self.use_isolated_root()
        self.write_git_dir(head=OTHER_SHA)
        with patch.dict(os.environ, {"GIT_COMMIT": "v3.2.1-release"}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), "unknown")

    def test_an_empty_env_var_is_not_a_declaration(self):
        """Empty means unset -- compose passes "" for an unspecified build arg."""
        self.use_isolated_root()
        self.write_stamp({"commit_sha": OTHER_SHA})
        with patch.dict(os.environ, {"GIT_COMMIT": "  "}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), OTHER_SHA)


class TheBuildStampAnswersWhenTheEnvironmentIsSilentTests(DeployMetaTestBase):
    def test_stamp_supplies_the_commit(self):
        self.use_isolated_root()
        self.write_stamp({"commit_sha": VALID_SHA, "build_time": "2026-08-21T10:00:00Z"})
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), VALID_SHA)
            self.assertEqual(deploy_meta.resolve_build_time(), "2026-08-21T10:00:00Z")

    def test_stamp_path_can_be_overridden(self):
        self.use_isolated_root()
        elsewhere = self.root / "somewhere" / "stamp.json"
        elsewhere.parent.mkdir(parents=True)
        elsewhere.write_text(json.dumps({"commit_sha": VALID_SHA}), encoding="utf-8")
        with patch.dict(
            os.environ, {"RMC_BUILD_STAMP_PATH": str(elsewhere)}, clear=True
        ):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), VALID_SHA)

    def test_a_stamp_holding_a_non_sha_is_ignored(self):
        self.use_isolated_root()
        self.write_stamp({"commit_sha": "HEAD"})
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), "unknown")


class AnUnreadableStampIsAnAbsentStampTests(DeployMetaTestBase):
    """A stamp is a convenience. It must never be able to break a boot."""

    def test_missing_file(self):
        self.use_isolated_root()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.read_build_stamp(), {})

    def test_not_json(self):
        self.use_isolated_root()
        self.write_stamp("this is not json {{{")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.read_build_stamp(), {})

    def test_json_but_not_an_object(self):
        self.use_isolated_root()
        self.write_stamp("[1, 2, 3]")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.read_build_stamp(), {})

    def test_nested_values_are_dropped_not_stringified(self):
        self.use_isolated_root()
        self.write_stamp({"commit_sha": VALID_SHA, "junk": {"a": 1}})
        with patch.dict(os.environ, {}, clear=True):
            stamp = deploy_meta.read_build_stamp()
        self.assertEqual(stamp, {"commit_sha": VALID_SHA})

    def test_an_absurdly_long_value_is_capped(self):
        self.use_isolated_root()
        self.write_stamp({"build_time": "x" * 5000})
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(len(deploy_meta.resolve_build_time()), 128)


class GitIsReadWithoutTheGitBinaryTests(DeployMetaTestBase):
    """The runtime image is not guaranteed to carry git, and a request path is
    no place for a subprocess. Every shape below is read as plain files."""

    def test_detached_head_holds_the_sha_directly(self):
        self.use_isolated_root()
        self.write_git_dir(head=VALID_SHA + "\n")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), VALID_SHA)

    def test_symbolic_head_follows_a_loose_ref(self):
        self.use_isolated_root()
        self.write_git_dir(
            head="ref: refs/heads/main\n",
            refs={"refs/heads/main": VALID_SHA + "\n"},
        )
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), VALID_SHA)

    def test_symbolic_head_falls_back_to_packed_refs(self):
        self.use_isolated_root()
        self.write_git_dir(
            head="ref: refs/heads/main\n",
            packed=(
                "# pack-refs with: peeled fully-peeled sorted\n"
                f"{OTHER_SHA} refs/heads/other\n"
                f"{VALID_SHA} refs/heads/main\n"
                "^aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
            ),
        )
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), VALID_SHA)

    def test_a_linked_worktree_git_file_is_followed(self):
        """`.git` is a FILE in a worktree. The stamp script runs in one here."""
        self.use_isolated_root()
        real = self.root / "elsewhere" / "worktrees" / "wt"
        real.mkdir(parents=True)
        (real / "HEAD").write_text(VALID_SHA, encoding="utf-8")
        (self.root / ".git").write_text(f"gitdir: {real}\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), VALID_SHA)

    def test_a_worktree_reads_packed_refs_from_its_common_dir(self):
        self.use_isolated_root()
        common = self.root / "main" / ".git"
        common.mkdir(parents=True)
        (common / "packed-refs").write_text(
            f"{VALID_SHA} refs/heads/main\n", encoding="utf-8"
        )
        wt = common / "worktrees" / "wt"
        wt.mkdir(parents=True)
        (wt / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (wt / "commondir").write_text("../..\n", encoding="utf-8")
        (self.root / ".git").write_text(f"gitdir: {wt}\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), VALID_SHA)

    def test_a_dangling_head_is_unknown_not_a_crash(self):
        self.use_isolated_root()
        self.write_git_dir(head="ref: refs/heads/deleted\n")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), "unknown")

    def test_a_gitdir_pointer_to_nowhere_is_unknown_not_a_crash(self):
        self.use_isolated_root()
        (self.root / ".git").write_text("gitdir: /no/such/path\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), "unknown")

    def test_nothing_at_all_is_unknown(self):
        self.use_isolated_root()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_commit_sha(), "unknown")


class TheEnvironmentLabelMustNotRouteTests(DeployMetaTestBase):
    """``DJANGO_ENV`` is read by ``config/settings.py`` into ``_IS_CLOUD_DEPLOYED``.

    Labelling a self-hosted appliance ``DJANGO_ENV=production`` -- the obvious
    thing an operator would type -- would therefore flip the box into hosted-cloud
    posture: ``is_cloud_host()`` turns true, the AI tier chain drops Ollama (the
    only provider an offline box HAS), and hosted conversion / paid-install
    enforcement switches on. So the self-host stack labels itself with
    ``ENVIRONMENT``, which nothing routes on.
    """

    def test_environment_is_reported(self):
        self.use_isolated_root()
        with patch.dict(os.environ, {"ENVIRONMENT": "selfhost"}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_environment(), "selfhost")

    def test_render_service_name_still_wins_on_render(self):
        self.use_isolated_root()
        env = {"RENDER_SERVICE_NAME": "school-management-system", "ENVIRONMENT": "x"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                deploy_meta.resolve_deploy_environment(), "school-management-system"
            )

    def test_unset_is_unknown(self):
        self.use_isolated_root()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_deploy_environment(), "unknown")

    def test_the_selfhost_compose_does_not_set_django_env(self):
        compose = (REPO_ROOT / "deploy" / "selfhost" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        offending = [
            line
            for line in compose.splitlines()
            if "DJANGO_ENV" in line and not line.strip().startswith("#")
        ]
        self.assertEqual(
            offending,
            [],
            msg=(
                "deploy/selfhost/docker-compose.yml sets DJANGO_ENV. That feeds "
                "_IS_CLOUD_DEPLOYED in config/settings.py, so it would flip an edge "
                "appliance into hosted-cloud posture and drop its Ollama tier. Use "
                "ENVIRONMENT for the display label instead."
            ),
        )

    def test_the_selfhost_compose_does_label_the_box(self):
        compose = (REPO_ROOT / "deploy" / "selfhost" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("ENVIRONMENT:", compose)


class BuildTimeResolutionTests(DeployMetaTestBase):
    def test_env_wins(self):
        self.use_isolated_root()
        self.write_stamp({"build_time": "from-stamp"})
        with patch.dict(os.environ, {"BUILD_TIME": "from-env"}, clear=True):
            self.assertEqual(deploy_meta.resolve_build_time(), "from-env")

    def test_render_created_at_is_honoured(self):
        self.use_isolated_root()
        with patch.dict(
            os.environ, {"RENDER_CREATED_AT": "2026-08-21T09:00:00Z"}, clear=True
        ):
            self.assertEqual(deploy_meta.resolve_build_time(), "2026-08-21T09:00:00Z")

    def test_unset_and_unstamped_is_unknown(self):
        self.use_isolated_root()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deploy_meta.resolve_build_time(), "unknown")


class TheImageActuallyStampsItselfTests(SimpleTestCase):
    """Contract tests over the deploy files.

    The resolver is only half the fix. If the Dockerfile stops running the stamp
    script, or ``.dockerignore`` starts excluding ``.git``, the appliance silently
    goes back to reporting ``unknown`` -- and nothing else in the suite would
    notice, because every runtime test can supply its own fixture.
    """

    def setUp(self):
        super().setUp()
        self.dockerfile = (REPO_ROOT / "deploy" / "selfhost" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        self.dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")

    def test_the_dockerfile_runs_the_stamp_script(self):
        self.assertIn("scripts/write_build_stamp.py", self.dockerfile)

    def test_the_stamp_script_exists_and_is_importable_without_django(self):
        path = REPO_ROOT / "scripts" / "write_build_stamp.py"
        self.assertTrue(path.is_file())
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("import django", source)
        self.assertNotIn("from django", source)

    def test_dockerignore_does_not_exclude_git(self):
        """The zero-touch stamp reads .git from the build context."""
        entries = [
            line.strip()
            for line in self.dockerignore.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertNotIn(".git", entries)
        self.assertNotIn(".git/", entries)

    def test_dockerignore_excludes_dotenv_files(self):
        """`COPY . .` baked deploy/selfhost/.env -- and its secrets -- into the image."""
        entries = [
            line.strip()
            for line in self.dockerignore.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertIn("**/.env", entries)
        self.assertIn("**/.env.*", entries)

    def test_the_stamp_is_gitignored(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".build-stamp.json", gitignore)


class TheStampWriterItselfTests(SimpleTestCase):
    """The build-time script. Nothing else exercises it -- it runs inside a
    Docker build and on Render, neither of which CI reproduces."""

    @staticmethod
    def _load():
        import importlib.util

        path = REPO_ROOT / "scripts" / "write_build_stamp.py"
        spec = importlib.util.spec_from_file_location("_rmc_stamp_writer", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_render_commit_env_is_used_during_a_render_build(self):
        writer = self._load()
        with patch.dict(os.environ, {"RENDER_GIT_COMMIT": VALID_SHA}, clear=True):
            self.assertEqual(writer.build_stamp()["commit_sha"], VALID_SHA)

    def test_an_explicit_build_arg_is_used(self):
        writer = self._load()
        with patch.dict(os.environ, {"GIT_COMMIT": VALID_SHA}, clear=True):
            self.assertEqual(writer.build_stamp()["commit_sha"], VALID_SHA)

    def test_a_malformed_arg_falls_back_to_git_here(self):
        """Opposite of the runtime rule, on purpose -- see the script docstring.

        At build time ``.git`` is ground truth sitting in the build context, so
        using it beats stamping nothing. At runtime there is nothing to check the
        declaration against, so a bad one must report ``unknown``.
        """
        writer = self._load()
        with patch.dict(os.environ, {"GIT_COMMIT": "v1.2.3"}, clear=True):
            stamp = writer.build_stamp()
        self.assertRegex(stamp["commit_sha"], r"^[0-9a-f]{40}$")

    def test_it_always_stamps_a_build_time(self):
        writer = self._load()
        with patch.dict(os.environ, {}, clear=True):
            self.assertRegex(
                writer.build_stamp()["build_time"],
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
            )

    def test_an_unwritable_destination_does_not_fail_the_build(self):
        writer = self._load()
        with patch.dict(os.environ, {}, clear=True):
            exit_code = writer.main(["--path", str(REPO_ROOT / "no" / "such" / "dir" / "s.json")])
        self.assertEqual(exit_code, 0)

    def test_the_render_build_script_stamps_too(self):
        """Render answers commit_sha from its own env but supplies no build time."""
        build_sh = (REPO_ROOT / "build.sh").read_text(encoding="utf-8")
        self.assertIn("scripts/write_build_stamp.py", build_sh)


class TheEdgeReadinessCheckReportsBuildIdentityTests(SimpleTestCase):
    """`entrypoint.web.sh` runs check_edge_readiness on every boot expressly to
    surface footguns, and it is where the 15-byte Fernet key should have been
    caught and was not. An appliance that cannot name its own code is a footgun
    of the same shape: invisible until someone needs it.

    These RUN the command rather than grepping its source. A source grep passed
    against a mutant that had stopped calling the resolver -- the import line
    alone still matched.
    """

    COMMAND = "check_edge_readiness"
    TARGET = "apps.schools.management.commands.check_edge_readiness"

    def _run(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command(self.COMMAND, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_a_resolvable_commit_is_reported(self):
        with patch(f"{self.TARGET}.resolve_deploy_commit_sha", return_value=VALID_SHA):
            output = self._run()
        self.assertIn("Build identity resolves", output)
        self.assertIn(VALID_SHA[:12], output)

    def test_an_unknown_commit_is_a_warning_the_operator_can_act_on(self):
        with patch(f"{self.TARGET}.resolve_deploy_commit_sha", return_value="unknown"):
            output = self._run()
        self.assertIn("cannot say what code it is running", output)
        # The finding has to name the fix, not just the symptom.
        self.assertIn("write_build_stamp.py", output)
