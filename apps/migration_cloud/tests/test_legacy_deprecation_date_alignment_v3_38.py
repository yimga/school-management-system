"""v3.38.0 — assert no occurrence of the wrong legacy-header deprecation
date (``2026-08-17``) survives in the files that document or implement
the dual-emit window.

The canonical date is ``2026-08-18`` — it matches the dispatcher
constant ``LEGACY_HEADER_DEPRECATION_DATE`` in
``apps/migration_cloud/api/webhook_dispatch.py`` and is the single
source of truth.

Cosmetic-only drift (the SDKs and one doc were using ``2026-08-17``)
was reconciled in v3.38.0; this test prevents regression.
"""

from __future__ import annotations

import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]

# Files that previously carried the off-by-one cosmetic date drift, OR
# that we now consider authoritative for the date. Every one of these
# must NOT contain the wrong date ``2026-08-17``.
_FILES_THAT_MUST_NOT_CONTAIN_WRONG_DATE = [
    _REPO_ROOT / "config" / "settings.py",
    _REPO_ROOT / "apps" / "migration_cloud" / "api" / "webhook_dispatch.py",
    _REPO_ROOT / "docs" / "WEBHOOK_HEADER_MIGRATION_2026.md",
    _REPO_ROOT / "docs" / "SECURITY_KEYS.md",
    _REPO_ROOT / "apps" / "migration_cloud" / "api" / "static" / "WEBHOOK_VERIFICATION.md",
    _REPO_ROOT / "packages" / "runmycampus-webhook-verifier-py" / "src" / "runmycampus_webhook_verifier" / "verifier.py",
    _REPO_ROOT / "packages" / "runmycampus-webhook-verifier-py" / "README.md",
    _REPO_ROOT / "packages" / "runmycampus-webhook-verifier-js" / "src" / "verifier.ts",
    _REPO_ROOT / "packages" / "runmycampus-webhook-verifier-js" / "README.md",
]

_WRONG_DATE = "2026-08-17"
_CANONICAL_DATE = "2026-08-18"


class LegacyDeprecationDateAlignmentTests(unittest.TestCase):
    """Single-source-of-truth invariant on the legacy-header date."""

    def test_no_off_by_one_date_anywhere_in_listed_files(self):
        violations: list[tuple[Path, list[int]]] = []
        for path in _FILES_THAT_MUST_NOT_CONTAIN_WRONG_DATE:
            if not path.exists():
                # README files exist in the packages; if any listed path
                # is missing we surface that as a failure too, because
                # the docket says all of these have been touched.
                violations.append((path, [-1]))
                continue
            text = path.read_text(encoding="utf-8")
            if _WRONG_DATE in text:
                # Capture the line numbers for diagnostic clarity.
                hits = [
                    i + 1
                    for i, line in enumerate(text.splitlines())
                    if _WRONG_DATE in line
                ]
                violations.append((path, hits))
        self.assertEqual(
            violations,
            [],
            (
                f"Found stale {_WRONG_DATE!r} references — canonical date "
                f"is {_CANONICAL_DATE!r} (the dispatcher constant). "
                f"Violations: {violations}"
            ),
        )

    def test_dispatcher_constant_is_canonical_date(self):
        """The dispatcher MUST carry the canonical date as its constant."""
        dispatch = (
            _REPO_ROOT
            / "apps"
            / "migration_cloud"
            / "api"
            / "webhook_dispatch.py"
        )
        text = dispatch.read_text(encoding="utf-8")
        self.assertIn(
            f'LEGACY_HEADER_DEPRECATION_DATE = "{_CANONICAL_DATE}"',
            text,
            "webhook_dispatch.py must declare the canonical date constant",
        )


if __name__ == "__main__":
    unittest.main()
