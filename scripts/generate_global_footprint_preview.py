#!/usr/bin/env python3
"""Regenerate artifacts/global-footprint-section-preview.html from _world_map_demo()."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "artifacts/global-footprint-section-preview.html"
DATA_SCRIPT_RE = re.compile(
    r'(<script type="application/json" id="rmc-world-globe-data">)(.*?)(</script>)',
    re.DOTALL,
)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.siteconfig.cockpit_manager_200x_preview_data import _world_map_demo

    demo = _world_map_demo()
    payload_json = demo["globe_payload_json"]

    if not PREVIEW.is_file():
        print(f"FAIL: missing preview artifact at {PREVIEW}", file=sys.stderr)
        return 1

    html = PREVIEW.read_text(encoding="utf-8")
    payload = json.loads(payload_json)
    for token in ("live_refresh", "globe_texture_url", "label_zoom"):
        if token not in payload:
            print(f"FAIL: demo payload missing {token!r}", file=sys.stderr)
            return 1
    api = payload.get("api") or {}
    if "live" not in api:
        print("FAIL: demo payload api.live missing", file=sys.stderr)
        return 1

    match = DATA_SCRIPT_RE.search(html)
    if not match:
        print("FAIL: preview HTML missing rmc-world-globe-data script block", file=sys.stderr)
        return 1

    html = html[: match.start(2)] + payload_json + html[match.end(2) :]
    html = html.replace(
        "Global Footprint section preview (batch 1654)",
        "Global Footprint section preview (batch 1657)",
    )

    # Sync SVG country labels from payload (positions + data-rmc-country).
    country_labels = payload.get("country_labels") or []
    for lbl in country_labels:
        cc = lbl.get("country_code") or ""
        if not cc:
            continue
        pattern = re.compile(
            rf'(<text class="lx-world__svg-country-label" data-rmc-region="[^"]*")'
            rf'( x="[^"]*" y="[^"]*")'
            rf'([^>]*>)([^<]*{re.escape(cc[:2])}[^<]*)</text>',
            re.IGNORECASE,
        )
        replacement = (
            f'<text class="lx-world__svg-country-label" data-rmc-region="{lbl.get("region", "")}" '
            f'data-rmc-country="{cc}" x="{lbl.get("svg_x")}" y="{lbl.get("svg_y")}" '
            f'text-anchor="middle">{lbl.get("text", "")}</text>'
        )
        if f'data-rmc-country="{cc}"' not in html:
            html = pattern.sub(replacement, html, count=1)

    PREVIEW.write_text(html, encoding="utf-8")
    print(f"OK: wrote {PREVIEW.relative_to(ROOT)} ({len(payload_json)} bytes payload)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
