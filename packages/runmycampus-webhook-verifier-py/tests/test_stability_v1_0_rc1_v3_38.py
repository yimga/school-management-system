"""Stability-contract tests for the 1.0.0-rc.1 release candidate (v3.38.0).

Six tests:
1. ``__all__`` matches STABILITY.md "Public API surface" list (parsed
   from the doc via regex).
2. ``pyproject.toml`` ``version`` matches ``__version__`` in
   ``runmycampus_webhook_verifier.__init__``.
3. ``CHANGELOG.md`` exists, parses (one ``## [<version>] — <date>``
   per release), and has a ``1.0.0-rc.1`` entry dated.
4. ``STABILITY.md`` mentions ``accept_legacy``.
5. Deprecated alias ``verify_signature`` still works AND emits
   ``DeprecationWarning``.
6. ``MIGRATION_TO_1_0.md`` exists.
"""

from __future__ import annotations

import re
import unittest
import warnings
from pathlib import Path

import runmycampus_webhook_verifier
from runmycampus_webhook_verifier import (
    __version__,
    compute_signature,
    verify_signature,
)


_PKG_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _PKG_ROOT / "pyproject.toml"
_INIT = _PKG_ROOT / "src" / "runmycampus_webhook_verifier" / "__init__.py"
_CHANGELOG = _PKG_ROOT / "CHANGELOG.md"
_STABILITY = _PKG_ROOT / "STABILITY.md"
_MIGRATION = _PKG_ROOT / "MIGRATION_TO_1_0.md"

_EXPECTED_RC_VERSION = "1.0.0-rc.1"


class PublicApiSurfaceTests(unittest.TestCase):
    """STABILITY.md is the single source of truth for ``__all__``."""

    def test_all_matches_stability_doc(self):
        stability_text = _STABILITY.read_text(encoding="utf-8")
        # Pull the bullet items from the "Public API surface" section
        # up to (but not including) the next heading.
        match = re.search(
            r"## Public API surface\s*(.*?)\n## ",
            stability_text,
            re.DOTALL,
        )
        self.assertIsNotNone(
            match, "STABILITY.md must have a '## Public API surface' section"
        )
        section = match.group(1)
        # Bullets are ``- `name``` — pull each backticked identifier.
        doc_names = set(re.findall(r"-\s+`([A-Za-z_][A-Za-z0-9_]*)`", section))
        self.assertTrue(
            doc_names, "STABILITY.md surface section produced 0 names — regex broken"
        )
        # The package's ``__all__`` should be a superset of the
        # documented stable surface (plus a few package-mechanics
        # items like ``__version__`` which are already in both).
        all_set = set(runmycampus_webhook_verifier.__all__)
        missing = doc_names - all_set
        self.assertEqual(
            missing,
            set(),
            f"STABILITY.md lists names not in __all__: {sorted(missing)}",
        )


class VersionConsistencyTests(unittest.TestCase):
    def test_pyproject_version_matches_dunder_version(self):
        toml_text = _PYPROJECT.read_text(encoding="utf-8")
        match = re.search(
            r'^version\s*=\s*"([^"]+)"\s*$', toml_text, re.MULTILINE
        )
        self.assertIsNotNone(
            match, "pyproject.toml is missing a top-level version = '...'"
        )
        self.assertEqual(match.group(1), __version__)
        self.assertEqual(__version__, _EXPECTED_RC_VERSION)


class ChangelogTests(unittest.TestCase):
    def test_changelog_exists_and_parses(self):
        self.assertTrue(_CHANGELOG.exists(), "CHANGELOG.md must exist")
        text = _CHANGELOG.read_text(encoding="utf-8")
        # ``## [<version>] — <date>`` per release. Em-dash separator.
        release_headings = re.findall(
            r"^##\s*\[([^\]]+)\]\s*[—-]\s*(\d{4}-\d{2}-\d{2})\s*$",
            text,
            re.MULTILINE,
        )
        self.assertGreaterEqual(
            len(release_headings),
            2,
            "CHANGELOG.md must list at least 2 releases",
        )
        versions = {v for v, _ in release_headings}
        self.assertIn(
            _EXPECTED_RC_VERSION,
            versions,
            f"CHANGELOG.md is missing a release entry for {_EXPECTED_RC_VERSION}",
        )


class StabilityDocTests(unittest.TestCase):
    def test_stability_mentions_accept_legacy(self):
        text = _STABILITY.read_text(encoding="utf-8")
        self.assertIn(
            "accept_legacy",
            text,
            "STABILITY.md must document the accept_legacy keyword on verify(...)",
        )


class DeprecatedAliasTests(unittest.TestCase):
    def test_verify_signature_still_works_and_warns(self):
        body = b'{"hello":"world"}'
        secret = b"sk_test_secret"
        sig = compute_signature(body, secret)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ok = verify_signature(body, sig, secret)
        self.assertTrue(ok, "deprecated alias must still verify correctly")
        deprecations = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        self.assertTrue(
            deprecations,
            "verify_signature() must emit DeprecationWarning per 1.0.0-rc.1",
        )


class MigrationDocTests(unittest.TestCase):
    def test_migration_doc_exists(self):
        self.assertTrue(_MIGRATION.exists(), "MIGRATION_TO_1_0.md must exist")
        # Sanity check it isn't empty.
        self.assertGreater(_MIGRATION.stat().st_size, 200)


if __name__ == "__main__":
    unittest.main()
