"""
Phase II.2 (SOT §2.4): frozen allowlist file set for retained cursor.execute helpers.

Counts are enforced by scripts/lint_raw_sql_usage.py; this test locks the six-file repo bar
so new raw SQL cannot land under a surprise filename without updating the manifest + docs.
"""

from __future__ import annotations

import json
import re
from django.test import SimpleTestCase

from apps.platform_runtime.tests.support.paths import repo_root

# Must match scripts/allowlists/raw_sql_allowlist.json "files" keys and docs/raw_sql_audit.md §1.
_RAW_SQL_ALLOWLIST_REL_PATHS = frozenset(
    {
        "apps/people/repositories/audit_repository.py",
        "apps/schools/repositories/health_repository.py",
        "apps/schools/repositories/rls_repository.py",
        "apps/schools/repositories/rls_context_repository.py",
        "apps/siteconfig/repositories/rls_session_repository.py",
        "apps/siteconfig/repositories/database_recovery_repository.py",
    }
)

_RAW_SQL_AUDIT_TABLE_ROW_RE = re.compile(
    r"^\|\s*(?P<path>apps/[^|]+?)\s*\|\s*(?P<count>\d+)\s*\|"
)


class RawSqlAllowlistManifestTests(SimpleTestCase):
    def test_allowlist_json_files_match_repo_bar(self):
        root = repo_root()
        path = root / "scripts" / "allowlists" / "raw_sql_allowlist.json"
        self.assertTrue(path.is_file(), f"missing allowlist: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        files = data.get("files") or {}
        self.assertEqual(
            frozenset(files),
            _RAW_SQL_ALLOWLIST_REL_PATHS,
            "raw_sql_allowlist.json 'files' keys must match the six-file §2.4 repo bar; "
            "update docs/raw_sql_audit.md and this test when adding or removing allowlisted SQL.",
        )
        for rel, meta in files.items():
            self.assertIsInstance(meta, dict, rel)
            self.assertIn("expected_count", meta, rel)
            self.assertIsInstance(meta["expected_count"], int, rel)
            self.assertGreaterEqual(meta["expected_count"], 1, rel)

    def test_raw_sql_audit_table_matches_allowlist_counts(self):
        root = repo_root()
        allowlist_path = root / "scripts" / "allowlists" / "raw_sql_allowlist.json"
        audit_doc_path = root / "docs" / "raw_sql_audit.md"
        self.assertTrue(allowlist_path.is_file(), f"missing allowlist: {allowlist_path}")
        self.assertTrue(audit_doc_path.is_file(), f"missing audit doc: {audit_doc_path}")

        allowlist_data = json.loads(allowlist_path.read_text(encoding="utf-8"))
        allowlist_files = allowlist_data.get("files") or {}
        expected = {
            rel: int(meta["expected_count"]) for rel, meta in allowlist_files.items()
        }

        doc_counts: dict[str, int] = {}
        for raw_line in audit_doc_path.read_text(encoding="utf-8").splitlines():
            match = _RAW_SQL_AUDIT_TABLE_ROW_RE.match(raw_line.strip())
            if not match:
                continue
            doc_counts[match.group("path")] = int(match.group("count"))

        self.assertEqual(
            doc_counts,
            expected,
            "docs/raw_sql_audit.md §1 table must match raw_sql_allowlist.json paths and expected counts.",
        )
