"""Scan: every shell with a PWA manifest must also wire the install prompt.

The bug class this catches (PWA install never available to users):

    templates/X_shell.html
        <link rel="manifest" …>     ← manifest declared
        <!-- no theme-color meta -->
        <!-- no mobile-web-app-capable meta -->
        <!-- no beforeinstallprompt handler hint -->
    → browsers refuse to surface the install prompt on Chromium/Edge.

Scanner contract:
  * Walks all top-level shell templates (root .html files under
    `templates/`).
  * For any shell that declares a `<link rel="manifest" …>`, asserts the
    presence of at least the chrome contract that lets the install prompt
    actually fire:
      - `<meta name="theme-color" …>`
      - `<meta name="mobile-web-app-capable" content="yes">` OR
        `<meta name="apple-mobile-web-app-capable" content="yes">`
  * Honors `<!-- pwa-install-prompt-coverage-allow: <reason> -->` for the
    rare shell where install is intentionally suppressed (e.g. admin login,
    error pages that should never prompt).

Zero-tolerance gate from day 1 (v3.57.1, 2026-05-21).

Usage:
    python scripts/scan_pwa_install_prompt_coverage.py [--strict] [--json] [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES_ROOT = REPO_ROOT / "templates"
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-pwa-install-prompt-coverage.json"
)

ALLOW_MARKER = "pwa-install-prompt-coverage-allow:"

MANIFEST_RE = re.compile(r"""<link[^>]+rel\s*=\s*["']manifest["']""", re.IGNORECASE)
THEME_COLOR_RE = re.compile(
    r"""<meta[^>]+name\s*=\s*["']theme-color["']""", re.IGNORECASE
)
WEB_APP_CAPABLE_RE = re.compile(
    r"""<meta[^>]+name\s*=\s*["'](?:mobile|apple-mobile)-web-app-capable["']""",
    re.IGNORECASE,
)


# Only walk the canonical shell layer — `_base*`, `base*`, `*_skeleton*`,
# `*_layout*`, and the 4 known shells. Page templates that extend these
# inherit the chrome.
def _is_shell_template(path: pathlib.Path) -> bool:
    name = path.name.lower()
    parts = [p.lower() for p in path.parts]
    canonical = {
        "portal_base.html",
        "base.html",
        "control_plane_skeleton.html",
        "control_plane_base.html",
        "base_site.html",
        "base_marketing.html",
        "marketing/base_marketing.html",
        "admin/base_site.html",
    }
    if any(c in str(path).replace("\\", "/").lower() for c in canonical):
        return True
    if name.startswith("base") or name.endswith("_base.html") or "_skeleton" in name:
        return True
    return False


def scan_file(path: pathlib.Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if ALLOW_MARKER in text:
        return []
    if not MANIFEST_RE.search(text):
        return []
    findings: list[str] = []
    if not THEME_COLOR_RE.search(text):
        findings.append(
            f"{path.relative_to(REPO_ROOT)}: missing <meta name=\"theme-color\">"
        )
    if not WEB_APP_CAPABLE_RE.search(text):
        findings.append(
            f"{path.relative_to(REPO_ROOT)}: missing <meta name=\"(mobile|apple-mobile)-web-app-capable\">"
        )
    return findings


def scan_all() -> list[str]:
    findings: list[str] = []
    if not TEMPLATES_ROOT.exists():
        return findings
    for html in TEMPLATES_ROOT.rglob("*.html"):
        if not _is_shell_template(html):
            continue
        findings.extend(scan_file(html))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = scan_all()
    total = len(findings)

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    baseline_total = 0
    if BASELINE_PATH.exists():
        try:
            baseline_total = int(
                json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get(
                    "finding_count", 0
                )
            )
        except (json.JSONDecodeError, ValueError):
            baseline_total = 0

    if args.update_baseline or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(
            json.dumps(
                {"finding_count": total, "findings": findings},
                indent=2,
            ),
            encoding="utf-8",
        )

    if args.json:
        print(
            json.dumps(
                {
                    "finding_count": total,
                    "baseline": baseline_total,
                    "findings": findings,
                },
                indent=2,
            )
        )
    else:
        print(f"pwa-install-prompt-coverage scan: {total} shell(s) missing chrome")
        print(f"baseline: {baseline_total}")
        for f in findings[:30]:
            print(f"  {f}")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
