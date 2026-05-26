#!/usr/bin/env python3
"""Zero external script/style CDN refs in templates (batch 1510)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

CDN_RE = re.compile(
    r"https?://(cdn\.jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com|cdn\.redoc\.ly)/",
    re.I,
)

ALLOW_MARKERS = (
    "fonts.googleapis.com",
    "fonts.gstatic.com",
)

REQUIRED_VENDOR = (
    "static/vendor/dropzone/dropzone.min.js",
    "static/vendor/mermaid/mermaid.min.js",
    "static/vendor/zxcvbn/zxcvbn.min.js",
    "static/js/htmx.min.js",
    "static/unfold/js/chart/chart.js",
)


def main() -> int:
    findings: list[str] = []

    for rel in REQUIRED_VENDOR:
        if not (ROOT / rel).is_file():
            findings.append(f"missing vendor file {rel}")

    redoc = ROOT / "static/vendor/redoc/redoc.standalone.js"
    if not redoc.is_file() or redoc.stat().st_size < 100_000:
        findings.append(
            "missing static/vendor/redoc/redoc.standalone.js "
            "(run: python scripts/fetch_vendor_redoc.py)"
        )

    if TEMPLATES.is_dir():
        for path in TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in CDN_RE.finditer(text):
                if any(a in match.group(0) for a in ALLOW_MARKERS):
                    continue
                findings.append(f"{path.relative_to(ROOT)}: {match.group(0)}")

    if findings:
        print("verify_cdn_self_host_burndown: FAIL", file=sys.stderr)
        for item in findings[:40]:
            print(f"  - {item}", file=sys.stderr)
        if len(findings) > 40:
            print(f"  ... and {len(findings) - 40} more", file=sys.stderr)
        return 1

    print("verify_cdn_self_host_burndown: CDN_SELF_HOST_BURNDOWN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
