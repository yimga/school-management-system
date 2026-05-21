"""Marketing asset integrity — claimed files exist and templates reference real static paths."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]
ASSETS_DIR = REPO / "static" / "images" / "marketing"
README = ASSETS_DIR / "README.md"
SCANNER = REPO / "scripts" / "check_marketing_assets_claimed_vs_present.py"

STATIC_IMG_RE = re.compile(
    r"""{%\s*static\s+['\"]images/marketing/([^'\"]+\.svg)['\"]\s*%}"""
)
HARDCODED_IMG_RE = re.compile(r"""images/marketing/([A-Za-z0-9_-]+\.svg)""")


class MarketingClaimedAssetsTests(SimpleTestCase):
    def test_asset_parity_scanner_exits_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCANNER)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=proc.stdout + proc.stderr,
        )

    def test_category_dominance_core_assets_on_disk(self) -> None:
        required = [
            "home-unified-school-journey.svg",
            "home-six-operating-surfaces.svg",
            "platform-sis-record-spine.svg",
            "platform-attendance-daily-register.svg",
            "platform-workflows-automation-timeline.svg",
            "platform-offline-sync-console.svg",
            "solution-private-growth-engine.svg",
            "solution-multi-campus-command-center.svg",
        ]
        for name in required:
            path = ASSETS_DIR / name
            self.assertTrue(path.is_file(), f"missing marketing asset: {name}")

    def test_readme_lists_shipped_home_and_platform_assets(self) -> None:
        text = README.read_text(encoding="utf-8")
        for name in (
            "home-unified-school-journey.svg",
            "platform-sis-record-spine.svg",
            "solution-private-growth-engine.svg",
        ):
            self.assertIn(name, text, f"README must document {name}")

    def test_readme_rejects_placeholder_proof_language(self) -> None:
        text = README.read_text(encoding="utf-8")
        self.assertIn("must not be presented as customer screenshots", text)
        self.assertIn("Do not use them as proof.", text)
        self.assertNotIn("Default placeholder SVGs", text)

    def test_templates_do_not_reference_missing_marketing_svgs(self) -> None:
        templates_root = REPO / "templates"
        referenced: set[str] = set()
        for path in templates_root.rglob("*.html"):
            body = path.read_text(encoding="utf-8", errors="ignore")
            for match in STATIC_IMG_RE.findall(body):
                referenced.add(match)
            if "marketing" in str(path):
                for match in HARDCODED_IMG_RE.findall(body):
                    if match.startswith(("platform-", "solution-", "home-", "module-", "hero-")):
                        referenced.add(match)
        missing = [name for name in sorted(referenced) if not (ASSETS_DIR / name).is_file()]
        self.assertEqual(missing, [], f"templates reference missing SVGs: {missing}")
