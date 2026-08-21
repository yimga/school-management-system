"""Fail if authenticated theme tail partial leaks comment text into HTML."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import django

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.template.loader import render_to_string  # noqa: E402

LEAK = "Platform-wide authenticated theme tail"


def main() -> int:
    html = render_to_string("partials/rmc_authenticated_theme_tail.html")
    if LEAK in html:
        print("THEME_TAIL_BLEED_FAIL: comment text rendered in HTML", file=sys.stderr)
        return 1
    if not re.search(
        r"rmc-theme-experience-dual-plane(?:\.[0-9a-f]{8,})?\.css",
        html,
        re.IGNORECASE,
    ):
        print("THEME_TAIL_BLEED_FAIL: dual-plane stylesheet link missing", file=sys.stderr)
        return 1
    print("THEME_TAIL_NO_BLEED_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
