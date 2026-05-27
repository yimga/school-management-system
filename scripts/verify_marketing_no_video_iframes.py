#!/usr/bin/env python3
"""Fail if marketing templates embed YouTube/Vimeo iframes."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOTS = (
    REPO / "templates" / "marketing",
    REPO / "templates" / "schools",
    REPO / "static" / "marketing" / "js",
)

FORBIDDEN = re.compile(
    r"(youtube\.com/embed|youtu\.be/|player\.vimeo\.com|youtube-nocookie\.com)",
    re.I,
)


def main() -> int:
    errors: list[str] = []
    for root in ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix not in {".html", ".js", ".mjs"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if FORBIDDEN.search(text):
                # Allow explicit waiver comment on previous line
                lines = text.splitlines()
                for i, line in enumerate(lines):
                    if FORBIDDEN.search(line):
                        prev = lines[i - 1] if i else ""
                        if "video-iframe-allow:" in prev or "video-iframe-allow:" in line:
                            continue
                        errors.append(f"{path.relative_to(REPO)}:{i + 1}")
    if errors:
        print("verify_marketing_no_video_iframes: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_marketing_no_video_iframes: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
