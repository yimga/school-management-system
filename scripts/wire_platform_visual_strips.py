#!/usr/bin/env python3
"""One-shot wiring: add {% marketing_platform_visual_strip %} to platform page templates."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGES = REPO / "templates" / "marketing" / "pages"
SKIP = frozenset(
    {
        "type_platform_fees_payments.html",
        "type_platform_offline_first.html",
        "type_platform_grading_report_cards.html",
        "type_platform_admissions.html",
        "type_platform_security.html",
        "type_platform_generic.html",
        "type_platform_hub.html",
    }
)
MARKER = "marketing_platform_visual_strip"
INSERT = "  {% marketing_platform_visual_strip %}\n"


def main() -> int:
    changed = 0
    for path in sorted(PAGES.glob("type_platform_*.html")):
        if path.name in SKIP:
            continue
        text = path.read_text(encoding="utf-8")
        if MARKER in text or "_platform_visual_engine_strip" in text:
            continue
        if "{% load" in text and "marketing_media" not in text:
            text = text.replace("{% load i18n static %}", "{% load i18n static marketing_media %}", 1)
            text = text.replace(
                "{% load i18n static %}\n{% load terminology_tags %}",
                "{% load i18n static marketing_media %}\n{% load terminology_tags %}",
                1,
            )
        if "</header>" in text:
            text = text.replace("</header>\n", f"</header>\n{INSERT}", 1)
        elif "<article" in text:
            idx = text.index("<article")
            end = text.index(">", idx) + 1
            text = text[:end] + "\n" + INSERT + text[end:]
        else:
            print(f"skip (no anchor): {path.name}", file=sys.stderr)
            continue
        path.write_text(text, encoding="utf-8")
        changed += 1
        print(f"wired: {path.name}")
    print(f"wire_platform_visual_strips: OK ({changed} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
