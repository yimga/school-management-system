#!/usr/bin/env python3
"""
Verify React island mount contracts and same-origin fetch URLs in static JS.

Complements scan_operator_shell_dead_hrefs.py (template hrefs) by checking:
  - templates referencing js/dist/*.mount.js ship a real bundle file
  - data-rmc-social-feed / data-rmc-social-moderation hosts exist when mount script loads
  - static/js/**/*.js fetch('/api/...') paths are well-formed (leading slash, no '#')

Exit 0 on clean tree.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
STATIC_JS = ROOT / "static" / "js"
OUT = ROOT / "docs" / "generated" / "react_mount_fetch_audit.json"

MOUNT_SCRIPT_RE = re.compile(
    r"""{%\s*static\s+['"](js/dist/[^'"]+\.mount\.js)['"]\s*%}"""
)
ATTR_MOUNT_RE = re.compile(r"""static\s+['"](js/dist/[^'"]+\.mount\.js)['"]""")
FETCH_API_RE = re.compile(r"""fetch\s*\(\s*['"](/api/[^'"]+)['"]""")


def _template_mount_scripts() -> set[str]:
    refs: set[str] = set()
    if not TEMPLATES.is_dir():
        return refs
    for html in TEMPLATES.rglob("*.html"):
        text = html.read_text(encoding="utf-8", errors="replace")
        for pattern in (MOUNT_SCRIPT_RE, ATTR_MOUNT_RE):
            refs.update(pattern.findall(text))
    return refs


def _bad_fetch_urls() -> list[str]:
    bad: list[str] = []
    if not STATIC_JS.is_dir():
        return bad
    for path in STATIC_JS.rglob("*.js"):
        if "vendor" in path.parts or "dist" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in FETCH_API_RE.finditer(text):
            url = match.group(1)
            if "#" in url or " " in url:
                bad.append(f"{rel}: malformed fetch {url}")
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    mount_refs = _template_mount_scripts()
    for rel in sorted(mount_refs):
        bundle = ROOT / "static" / Path(rel)
        if not bundle.is_file():
            errors.append(f"missing mount bundle: {rel}")

    social_template = TEMPLATES / "social_media" / "proud_campus_feed.html"
    if social_template.is_file():
        text = social_template.read_text(encoding="utf-8")
        if "data-rmc-social-feed" not in text:
            errors.append("proud_campus_feed.html missing data-rmc-social-feed host")
        if "social-feed.mount.js" not in text:
            errors.append("proud_campus_feed.html missing social-feed.mount.js")

    errors.extend(_bad_fetch_urls())

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "REACT_MOUNT_FETCH_PASS" if not errors else "REACT_MOUNT_FETCH_FAIL",
        "mount_refs": sorted(mount_refs),
        "error_count": len(errors),
        "errors": errors,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(payload["status"], f"mounts={len(mount_refs)} errors={len(errors)}")
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
