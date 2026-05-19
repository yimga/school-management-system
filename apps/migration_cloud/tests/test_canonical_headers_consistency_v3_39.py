"""v3.39.0 Agent 3 — canonical-headers SOT/mirror consistency + companion-extension icon presence.

Two Django-side tests for the v3.39.0 Migration Cloud fan-out:

  1. ``test_scanner_exits_zero_on_real_tree`` — runs
     ``scripts/scan_companion_canonical_headers_drift.py`` against the
     real working tree (no mocking) and asserts it reports zero
     unallowed drift. This catches the case where a maintainer edits
     either the Django SOT
     (``apps/migration_cloud/accelerators/runmycampus_canonical.py``)
     OR one of the JSON mirrors
     (``companion-tauri/src-tauri/src/canonical_headers.json``,
     ``companion-docker/app/canonical_headers.json``) without
     synchronizing the other side.

  2. ``test_companion_extension_icons_present_and_valid_png`` — asserts
     the three MV3 icon files exist and start with the PNG magic
     prefix ``b"\\x89PNG\\r\\n\\x1a\\n"``. These were honest-deferred
     in v3.38.0 (Agent 1) and materialized in v3.39.0 (this agent).

Both tests are stdlib-friendly — no DB, no fixtures, no settings.
``SimpleTestCase`` is enough.
"""

from __future__ import annotations

import importlib
import pathlib
import sys

from django.conf import settings
from django.test import SimpleTestCase

REPO_ROOT = pathlib.Path(settings.BASE_DIR)
SCRIPTS_DIR = REPO_ROOT / "scripts"


class CanonicalHeadersDriftScannerOnRealTreeTests(SimpleTestCase):
    """The drift scanner must see zero unallowed drift on the real tree."""

    def test_scanner_exits_zero_on_real_tree(self) -> None:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        # Force a fresh import in case another test mutated module
        # constants earlier in the session.
        scanner = importlib.import_module(
            "scan_companion_canonical_headers_drift"
        )
        importlib.reload(scanner)

        unallowed, rows = scanner.run()

        # Always expect zero drift on a clean tree.
        self.assertEqual(
            unallowed,
            0,
            msg=(
                "canonical-headers drift detected against the real working tree. "
                "Drift rows: "
                + "; ".join(
                    f"{r['mirror']}::{r['domain']}::{r['drift_kind']}"
                    for r in rows
                    if r["drift_kind"] != "identical"
                )
            ),
        )

        # Sanity: at least the 23 documented domains x 2 mirrors = 46 rows.
        self.assertGreaterEqual(len(rows), 46)


class CompanionExtensionIconsTests(SimpleTestCase):
    """The MV3 manifest's icon-16/48/128 files must be on-disk valid PNGs."""

    ICON_DIR = REPO_ROOT / "companion-extension" / "icons"
    EXPECTED_FILES = ("icon-16.png", "icon-48.png", "icon-128.png")
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

    def test_companion_extension_icons_present_and_valid_png(self) -> None:
        for name in self.EXPECTED_FILES:
            path = self.ICON_DIR / name
            self.assertTrue(
                path.exists(),
                msg=f"missing companion-extension icon: {path}",
            )
            data = path.read_bytes()
            self.assertGreater(
                len(data),
                len(self.PNG_MAGIC),
                msg=f"empty/truncated PNG bytes: {path}",
            )
            self.assertEqual(
                data[: len(self.PNG_MAGIC)],
                self.PNG_MAGIC,
                msg=f"bad PNG magic header in {path}",
            )
