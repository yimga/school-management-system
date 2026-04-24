from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.platform_runtime.tests.support.paths import repo_root
from apps.platform_runtime.tests.support.raw_sql_lint_fixtures import (
    write_raw_sql_lint_fixture_repo,
)
from apps.platform_runtime.tests.support.script_loading import load_repo_script


class LintRawSqlUsageScriptTests(SimpleTestCase):
    def _script_path(self) -> Path:
        return repo_root() / "scripts" / "lint_raw_sql_usage.py"

    def _load_script_module(self):
        return load_repo_script(
            "scripts/lint_raw_sql_usage.py",
            "lint_raw_sql_usage_script_test_module",
        )

    def test_load_allowlist_returns_files_mapping_only(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allowlist.json"
            path.write_text(
                json.dumps(
                    {
                        "manifest_last_reviewed": "2026-04-09",
                        "files": {"apps/demo/sql_user.py": {"expected_count": 1}},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            allowlist = module._load_allowlist(path)

        self.assertEqual(
            allowlist,
            {"apps/demo/sql_user.py": {"expected_count": 1}},
        )

    def test_scan_with_manifest_metadata_only_allowlist_reports_clean_success(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps" / "demo").mkdir(parents=True, exist_ok=True)
            (root / "scripts" / "allowlists").mkdir(parents=True, exist_ok=True)
            (root / "apps" / "demo" / "introspection_only.py").write_text(
                "\n".join(
                    [
                        "from django.db import connection",
                        "",
                        "with connection.cursor() as cursor:",
                        "    columns = connection.introspection.get_table_description(",
                        '        cursor, "schools_school"',
                        "    )",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                json.dumps({"manifest_last_reviewed": "2026-04-09"}, indent=2),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertIn(
            "All non-migration raw SQL usage is classified and unchanged.",
            result.stdout,
        )

    def test_invalid_base_returns_error(self):
        script = self._script_path()
        missing = Path(tempfile.gettempdir()) / "lint_raw_sql_usage_missing_base"
        result = subprocess.run(
            [sys.executable, str(script), "--base", str(missing)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("--base path does not exist or is not a directory", result.stderr)

    def test_exit_zero_reports_violation_but_returns_success(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root)
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                    "--exit-zero",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("violations detected", result.stderr)
        self.assertIn(
            "Unexpected raw SQL usage in apps/demo/sql_user.py (1 hit(s))",
            result.stderr,
        )

    def test_count_mismatch_reports_expected_vs_found(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"apps/demo/sql_user.py": {"expected_count": 2}},
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "Raw SQL count changed in apps/demo/sql_user.py: expected 2, found 1",
            result.stderr,
        )

    def test_missing_allowlisted_path_reports_violation(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"apps/demo/sql_user.py": {"expected_count": 1}},
                write_sql_user=False,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "Allowlisted raw SQL path missing from scan: apps/demo/sql_user.py",
            result.stderr,
        )

    def test_missing_allowlist_file_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root)
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").unlink()
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("allowlist file not found", result.stderr)

    def test_invalid_allowlist_json_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root)
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                "{not-json",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("allowlist JSON invalid", result.stderr)

    def test_allowlist_path_outside_base_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root)
            outside_allowlist = root.parent / "outside_allowlist.json"
            outside_allowlist.write_text(
                json.dumps({"files": {}}, indent=2),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    str(outside_allowlist),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("allowlist path must be within --base", result.stderr)

    def test_allowlist_with_non_repo_prefix_path_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"README.md": {"expected_count": 0}},
                write_sql_user=False,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("must start with apps/ or config/", result.stderr)

    def test_allowlist_with_backslash_path_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={r"apps\\demo\\sql_user.py": {"expected_count": 0}},
                write_sql_user=False,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("must use /", result.stderr)

    def test_allowlist_with_non_int_expected_count_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"apps/demo/sql_user.py": {"expected_count": "1"}},
                write_sql_user=False,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid expected_count", result.stderr)

    def test_allowlist_with_negative_expected_count_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"apps/demo/sql_user.py": {"expected_count": -1}},
                write_sql_user=False,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("must be >= 0", result.stderr)

    def test_allowlist_with_missing_expected_count_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"apps/demo/sql_user.py": {}},
                write_sql_user=False,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing expected_count", result.stderr)

    def test_allowlist_with_non_object_entry_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root, write_sql_user=False)
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                json.dumps({"files": {"apps/demo/sql_user.py": 123}}, indent=2),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid allowlist entry", result.stderr)

    def test_allowlist_with_parent_dir_path_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"apps/demo/../sql_user.py": {"expected_count": 0}},
                write_sql_user=False,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("must not contain ..", result.stderr)

    def test_allowlist_with_absolute_path_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"/apps/demo/sql_user.py": {"expected_count": 0}},
                write_sql_user=False,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("must be relative", result.stderr)

    def test_allowlist_with_non_py_extension_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"apps/demo/sql_user.txt": {"expected_count": 1}},
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("Invalid allowlist path (must be a .py file): apps/demo/sql_user.txt", result.stderr)

    def test_allowlist_with_invalid_manifest_last_reviewed_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root)
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                json.dumps(
                    {
                        "manifest_last_reviewed": "2026/04/09",
                        "files": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("Invalid allowlist manifest_last_reviewed", result.stderr)

    def test_allowlist_with_future_manifest_last_reviewed_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root)
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                json.dumps(
                    {
                        "manifest_last_reviewed": "2999-01-01",
                        "files": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("manifest_last_reviewed (must not be in the future)", result.stderr)

    def test_allowlist_with_invalid_entry_last_reviewed_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root, allowlist_files={"apps/demo/sql_user.py": {"expected_count": 1}})
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                json.dumps(
                    {
                        "manifest_last_reviewed": "2026-04-09",
                        "files": {
                            "apps/demo/sql_user.py": {
                                "expected_count": 1,
                                "last_reviewed": "2026-13-01",
                            }
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("Invalid allowlist last_reviewed for apps/demo/sql_user.py", result.stderr)

    def test_allowlist_with_blank_reason_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root, allowlist_files={"apps/demo/sql_user.py": {"expected_count": 1}})
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                json.dumps(
                    {
                        "manifest_last_reviewed": "2026-04-09",
                        "files": {
                            "apps/demo/sql_user.py": {
                                "expected_count": 1,
                                "reason": "   ",
                                "last_reviewed": "2026-04-09",
                            }
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("reason is required when expected_count > 0", result.stderr)

    def test_allowlist_missing_manifest_when_positive_expected_count_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root, allowlist_files={"apps/demo/sql_user.py": {"expected_count": 1}})
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                json.dumps(
                    {
                        "files": {
                            "apps/demo/sql_user.py": {
                                "expected_count": 1,
                                "reason": "x",
                                "last_reviewed": "2026-04-09",
                            }
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("manifest_last_reviewed is required when any file has expected_count > 0", result.stderr)

    def test_allowlist_missing_reason_when_positive_expected_count_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root, write_sql_user=False)
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                json.dumps(
                    {
                        "manifest_last_reviewed": "2026-04-09",
                        "files": {
                            "apps/demo/sql_user.py": {
                                "expected_count": 1,
                                "last_reviewed": "2026-04-09",
                            }
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("reason is required when expected_count > 0", result.stderr)

    def test_allowlist_missing_last_reviewed_when_positive_expected_count_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(root, write_sql_user=False)
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                json.dumps(
                    {
                        "manifest_last_reviewed": "2026-04-09",
                        "files": {
                            "apps/demo/sql_user.py": {
                                "expected_count": 1,
                                "reason": "Justification present.",
                            }
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("last_reviewed is required when expected_count > 0", result.stderr)

    def test_allowlist_with_unknown_entry_key_returns_error(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={
                    "apps/demo/sql_user.py": {
                        "expected_count": 1,
                        "reason": "ok",
                        "last_reviewed": "2026-04-09",
                        "notes": "not an allowed key",
                    }
                },
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid allowlist paths detected", result.stderr)
        self.assertIn("unknown key 'notes'", result.stderr)
        self.assertIn("expected_count", result.stderr)

    def test_allowlisted_match_returns_success_message(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"apps/demo/sql_user.py": {"expected_count": 1}},
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertIn(
            "All non-migration raw SQL usage is classified and unchanged.",
            result.stdout,
        )

    def test_missing_allowlisted_zero_count_path_is_ignored(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_raw_sql_lint_fixture_repo(
                root,
                allowlist_files={"apps/demo/sql_user.py": {"expected_count": 0}},
                write_sql_user=False,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertIn(
            "All non-migration raw SQL usage is classified and unchanged.",
            result.stdout,
        )

    def test_count_execute_calls_falls_back_to_string_count_on_syntax_error(self):
        module = self._load_script_module()
        text = "\n".join(
            [
                "def broken(",
                '    cursor.execute("SELECT 1")',
                '    cursor.execute("SELECT 2")',
                "not cursor.execute but still text",
            ]
        )

        self.assertEqual(module._count_execute_calls(text), 2)

    def test_count_execute_calls_tracks_supported_cursor_alias_patterns(self):
        module = self._load_script_module()
        text = "\n".join(
            [
                "from django.db import connection",
                "",
                "with connection.cursor() as cursor:",
                '    cursor.execute("SELECT 1")',
                "",
                "assigned = connection.cursor()",
                'assigned.execute("SELECT 2")',
                "",
                "typed_cursor: object = connection.cursor()",
                'typed_cursor.execute("SELECT 3")',
                "",
                "def use_cursor_arg(cursor):",
                '    cursor.execute("SELECT 4")',
                "",
                "def use_cur_arg(cur):",
                '    cur.execute("SELECT 5")',
                "",
                "def use_suffix(report_cursor):",
                '    report_cursor.execute("SELECT 6")',
                "",
                "async def use_async_with():",
                "    async with connection.cursor() as cursor:",
                '        cursor.execute("SELECT 7")',
            ]
        )

        self.assertEqual(module._count_execute_calls(text), 7)

    def test_count_execute_calls_keeps_cursor_aliases_scoped_to_their_scope(self):
        module = self._load_script_module()
        text = "\n".join(
            [
                "from django.db import connection",
                "",
                "with connection.cursor() as cursor:",
                '    cursor.execute("SELECT 1")',
                "",
                "def outer():",
                "    with connection.cursor() as cursor:",
                '        cursor.execute("SELECT 2")',
                "",
                "        def inner():",
                '            cursor.execute("SELECT 3")',
                "",
                "        return inner",
            ]
        )

        self.assertEqual(module._count_execute_calls(text), 2)

    def test_count_execute_calls_tracks_all_supported_argument_kinds(self):
        module = self._load_script_module()
        text = "\n".join(
            [
                "def use_posonly(cursor, /):",
                '    cursor.execute("SELECT 1")',
                "",
                "def use_kwonly(*, cursor):",
                '    cursor.execute("SELECT 2")',
                "",
                "def use_vararg(*cursor):",
                '    cursor.execute("SELECT 3")',
                "",
                "def use_kwarg(**cursor):",
                '    cursor.execute("SELECT 4")',
            ]
        )

        self.assertEqual(module._count_execute_calls(text), 4)

    def test_count_execute_calls_ignores_non_alias_execute_calls(self):
        module = self._load_script_module()
        text = "\n".join(
            [
                "class Client:",
                "    def execute(self, sql):",
                "        return sql",
                "",
                "client = Client()",
                'client.execute("SELECT 1")',
                'cursor.execute("SELECT 2")',
                'report_cursor.execute("SELECT 3")',
                "holder = type('Holder', (), {'cursor': client})()",
                'holder.cursor.execute("SELECT 4")',
                'literal = "cursor.execute(\\"SELECT 5\\")"',
            ]
        )

        self.assertEqual(module._count_execute_calls(text), 0)

    def test_count_execute_calls_ignores_cursor_introspection_only_patterns(self):
        module = self._load_script_module()
        text = "\n".join(
            [
                "from django.db import connection",
                "",
                "with connection.cursor() as cursor:",
                "    columns = {",
                "        col.name",
                "        for col in connection.introspection.get_table_description(",
                '            cursor, "schools_school"',
                "        )",
                "    }",
                "    has_domain = 'domain' in columns",
            ]
        )

        self.assertEqual(module._count_execute_calls(text), 0)

    def test_scan_with_cursor_introspection_only_file_reports_clean_success(self):
        script = self._script_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps" / "demo").mkdir(parents=True, exist_ok=True)
            (root / "scripts" / "allowlists").mkdir(parents=True, exist_ok=True)
            (root / "apps" / "demo" / "introspection_only.py").write_text(
                "\n".join(
                    [
                        "from django.db import connection",
                        "",
                        "with connection.cursor() as cursor:",
                        "    columns = {",
                        "        col.name",
                        "        for col in connection.introspection.get_table_description(",
                        '            cursor, "schools_school"',
                        "        )",
                        "    }",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
                json.dumps({"files": {}}, indent=2),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--base",
                    str(root),
                    "--allowlist",
                    "scripts/allowlists/raw_sql_allowlist.json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertIn(
            "All non-migration raw SQL usage is classified and unchanged.",
            result.stdout,
        )

    def test_iter_candidate_python_files_uses_tracked_python_files_only(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked_python = root / "apps" / "demo" / "sql_user.py"
            tracked_python.parent.mkdir(parents=True, exist_ok=True)
            tracked_python.write_text("pass\n", encoding="utf-8")
            tracked_config = root / "config" / "settings.py"
            tracked_config.parent.mkdir(parents=True, exist_ok=True)
            tracked_config.write_text("pass\n", encoding="utf-8")
            skipped_test = root / "apps" / "demo" / "tests" / "test_sql_user.py"
            skipped_test.parent.mkdir(parents=True, exist_ok=True)
            skipped_test.write_text("pass\n", encoding="utf-8")
            skipped_migration = root / "apps" / "demo" / "migrations" / "0001_initial.py"
            skipped_migration.parent.mkdir(parents=True, exist_ok=True)
            skipped_migration.write_text("pass\n", encoding="utf-8")
            skipped_text = root / "apps" / "demo" / "notes.txt"
            skipped_text.write_text("raw sql?\n", encoding="utf-8")

            with patch.object(
                module,
                "_tracked_file_relpaths",
                return_value=frozenset(
                    {
                        "apps/demo/sql_user.py",
                        "config/settings.py",
                        "apps/demo/tests/test_sql_user.py",
                        "apps/demo/migrations/0001_initial.py",
                        "apps/demo/notes.txt",
                        "scripts/utility.py",
                    }
                ),
            ):
                results = [
                    path.relative_to(root).as_posix()
                    for path in module._iter_candidate_python_files(root)
                ]

        self.assertEqual(results, ["apps/demo/sql_user.py", "config/settings.py"])

    def test_iter_candidate_python_files_falls_back_to_rglob_when_git_tracking_missing(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_python = root / "apps" / "demo" / "sql_user.py"
            app_python.parent.mkdir(parents=True, exist_ok=True)
            app_python.write_text("pass\n", encoding="utf-8")
            config_python = root / "config" / "settings.py"
            config_python.parent.mkdir(parents=True, exist_ok=True)
            config_python.write_text("pass\n", encoding="utf-8")
            skipped_cache = root / "apps" / "demo" / "__pycache__" / "cache.py"
            skipped_cache.parent.mkdir(parents=True, exist_ok=True)
            skipped_cache.write_text("pass\n", encoding="utf-8")
            skipped_test = root / "apps" / "demo" / "tests" / "test_sql_user.py"
            skipped_test.parent.mkdir(parents=True, exist_ok=True)
            skipped_test.write_text("pass\n", encoding="utf-8")

            with patch.object(module, "_tracked_file_relpaths", return_value=None):
                results = sorted(
                    path.relative_to(root).as_posix()
                    for path in module._iter_candidate_python_files(root)
                )

        self.assertEqual(results, ["apps/demo/sql_user.py", "config/settings.py"])

    def test_tracked_file_relpaths_returns_none_without_git_directory(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(module._tracked_file_relpaths(root))

    def test_tracked_file_relpaths_returns_none_on_git_nonzero_exit(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            with patch.object(
                module.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    args=["git"],
                    returncode=1,
                    stdout=b"",
                    stderr=b"fatal: bad revision",
                ),
            ):
                self.assertIsNone(module._tracked_file_relpaths(root))

    def test_tracked_file_relpaths_decodes_valid_paths_and_skips_invalid_utf8(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            with patch.object(
                module.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    args=["git"],
                    returncode=0,
                    stdout=(
                        b"apps/demo/sql_user.py\0"
                        b"config/settings.py\0"
                        b"apps/demo/\xffbad.py\0"
                    ),
                    stderr=b"",
                ),
            ):
                results = module._tracked_file_relpaths(root)

        self.assertEqual(
            results,
            frozenset({"apps/demo/sql_user.py", "config/settings.py"}),
        )

    def test_resolve_base_returns_resolved_directory_path(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            nested = base / "demo"
            nested.mkdir()

            resolved = module._resolve_base(str(base / "." / "demo"))

        self.assertEqual(resolved, nested.resolve())

    def test_parse_args_uses_expected_defaults(self):
        module = self._load_script_module()

        args = module.parse_args([])

        self.assertEqual(args.base, str(module.ROOT))
        self.assertEqual(args.allowlist, "scripts/allowlists/raw_sql_allowlist.json")
        self.assertFalse(args.exit_zero)

    def test_parse_args_accepts_custom_values(self):
        module = self._load_script_module()

        args = module.parse_args(
            ["--base", "demo-root", "--allowlist", "custom.json", "--exit-zero"]
        )

        self.assertEqual(args.base, "demo-root")
        self.assertEqual(args.allowlist, "custom.json")
        self.assertTrue(args.exit_zero)

    def test_tracked_file_relpaths_returns_none_on_git_timeout(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            with patch.object(
                module.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30),
            ):
                self.assertIsNone(module._tracked_file_relpaths(root))
