"""v3.39.0 — tests for `scripts/preflight_signed_release.py`.

Coverage:

1. Passes when versions are aligned (Cargo.toml matches a synthetic
   tag pointing at the real on-disk version).
2. Fails when Cargo.toml version diverges from the tag suffix.
3. Fails when CHANGELOG / fallback docs do not mention the version.
4. Passes the secrets check WITHOUT a GitHub token in env (the
   "secrets-list path"; no API call is attempted).
5. The Tauri required-secrets list is non-empty.
6. The 3 new workflow YAML files exist on disk.

Tests are stdlib-only (`unittest`), match the v3.38.0 pattern in
`test_legacy_deprecation_date_alignment_v3_38.py`, and never touch
network. Path-based tests are skipped when the repo layout is not
reachable (defensive on sandboxes).
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PREFLIGHT_PATH = _REPO_ROOT / "scripts" / "preflight_signed_release.py"


def _load_preflight_module():
    spec = importlib.util.spec_from_file_location("preflight_signed_release", str(_PREFLIGHT_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load preflight module from {_PREFLIGHT_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(_PREFLIGHT_PATH.is_file(), "preflight script not on disk")
class PreflightModuleLoadTests(unittest.TestCase):
    def test_module_loads_cleanly(self):
        mod = _load_preflight_module()
        self.assertTrue(hasattr(mod, "run"))
        self.assertTrue(hasattr(mod, "required_secrets_for"))
        self.assertTrue(hasattr(mod, "check_secrets"))
        self.assertTrue(hasattr(mod, "check_workflow_files"))


@unittest.skipUnless(_PREFLIGHT_PATH.is_file(), "preflight script not on disk")
class RequiredSecretsListTests(unittest.TestCase):
    def test_tauri_required_secrets_non_empty(self):
        mod = _load_preflight_module()
        secrets = mod.required_secrets_for("companion-tauri")
        self.assertIsInstance(secrets, tuple)
        self.assertGreater(len(secrets), 0)
        # Sanity: well-known names must be present.
        for name in ("APPLE_ID", "APPLE_TEAM_ID", "MACOS_CERT_P12_BASE64",
                     "WIN_CERT_PFX_BASE64", "WIN_CERT_PASSWORD"):
            self.assertIn(name, secrets)

    def test_docker_required_secrets_empty_keyless(self):
        # Cosign keyless does NOT need user-managed signing secrets.
        mod = _load_preflight_module()
        self.assertEqual(mod.required_secrets_for("companion-docker"), ())

    def test_unknown_sibling_raises(self):
        mod = _load_preflight_module()
        with self.assertRaises(ValueError):
            mod.required_secrets_for("companion-bogus")


@unittest.skipUnless(_PREFLIGHT_PATH.is_file(), "preflight script not on disk")
class SecretsCheckOfflinePathTests(unittest.TestCase):
    def test_no_token_yields_info_line_not_failure(self):
        mod = _load_preflight_module()
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "RMC_GH_REPO")}
        with mock.patch.dict(os.environ, env, clear=True):
            findings = mod.check_secrets(["APPLE_ID", "APPLE_TEAM_ID"])
        # Exactly one informational line, no [FAIL].
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].startswith("[INFO]"))
        self.assertIn("APPLE_ID", findings[0])
        self.assertIn("APPLE_TEAM_ID", findings[0])

    def test_empty_secrets_list_yields_no_findings(self):
        mod = _load_preflight_module()
        with mock.patch.dict(os.environ, {}, clear=True):
            findings = mod.check_secrets([])
        self.assertEqual(findings, [])


@unittest.skipUnless(_PREFLIGHT_PATH.is_file(), "preflight script not on disk")
class VersionAlignmentTests(unittest.TestCase):
    def test_tauri_aligned_when_tag_matches_cargo_toml(self):
        mod = _load_preflight_module()
        cargo = mod.TAURI_CARGO_TOML
        if not cargo.is_file():
            self.skipTest(f"Cargo.toml not present at {cargo}")
        actual_version = mod._read_cargo_version(cargo)
        findings = mod.check_version_alignment("companion-tauri", actual_version)
        self.assertEqual(findings, [])

    def test_tauri_release_metadata_versions_match_cargo_toml(self):
        mod = _load_preflight_module()
        cargo = mod.TAURI_CARGO_TOML
        package_json = mod.TAURI_PACKAGE_JSON
        tauri_config = mod.TAURI_CONFIG_JSON
        for path in (cargo, package_json, tauri_config):
            if not path.is_file():
                self.skipTest(f"release metadata file not present at {path}")
        actual_version = mod._read_cargo_version(cargo)
        self.assertEqual(mod._read_json_version(package_json), actual_version)
        self.assertEqual(mod._read_json_version(tauri_config), actual_version)

    def test_tauri_diverges_when_tag_is_wrong(self):
        mod = _load_preflight_module()
        cargo = mod.TAURI_CARGO_TOML
        if not cargo.is_file():
            self.skipTest(f"Cargo.toml not present at {cargo}")
        findings = mod.check_version_alignment("companion-tauri", "999.999.999")
        self.assertGreaterEqual(len(findings), 1)
        for finding in findings:
            self.assertTrue(finding.startswith("[FAIL]"))
            self.assertIn("999.999.999", finding)

    def test_docker_aligned_when_tag_matches_init_py(self):
        mod = _load_preflight_module()
        init = mod.DOCKER_VERSION_FILE
        if not init.is_file():
            self.skipTest(f"app/__init__.py not present at {init}")
        actual_version = mod._read_docker_version(init)
        findings = mod.check_version_alignment("companion-docker", actual_version)
        self.assertEqual(findings, [])


@unittest.skipUnless(_PREFLIGHT_PATH.is_file(), "preflight script not on disk")
class ChangelogCheckTests(unittest.TestCase):
    def test_missing_version_in_any_doc_is_failure(self):
        mod = _load_preflight_module()
        # Use a manifestly-impossible version string so no doc could legitimately mention it.
        findings = mod.check_changelog("companion-tauri", "0.0.0-impossible-zzz")
        # Either no CHANGELOG found OR the version is absent — both are [FAIL].
        self.assertGreaterEqual(len(findings), 1)
        for f in findings:
            self.assertTrue(f.startswith("[FAIL]"))


@unittest.skipUnless(_PREFLIGHT_PATH.is_file(), "preflight script not on disk")
class WorkflowFilesTests(unittest.TestCase):
    def test_all_three_workflow_files_exist(self):
        mod = _load_preflight_module()
        for path in mod.WORKFLOW_FILES:
            self.assertTrue(path.is_file(), f"workflow file missing: {path}")

    def test_workflow_files_pass_structural_check(self):
        mod = _load_preflight_module()
        findings = mod.check_workflow_files()
        # No [FAIL] entries; INFO/WARN are allowed.
        fails = [f for f in findings if f.startswith("[FAIL]")]
        self.assertEqual(fails, [], f"unexpected failures: {fails}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
