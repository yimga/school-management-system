#!/usr/bin/env python3
"""Regenerate artifacts/global-footprint-section-preview.html from _world_map_demo()."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "artifacts/global-footprint-section-preview.html"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from django.template.loader import render_to_string

    from apps.siteconfig.cockpit_manager_200x_preview_data import _world_map_demo

    demo = _world_map_demo()
    payload_json = demo["globe_payload_json"]

    payload = json.loads(payload_json)
    for token in ("live_refresh", "globe_texture_url", "label_zoom"):
        if token not in payload:
            print(f"FAIL: demo payload missing {token!r}", file=sys.stderr)
            return 1
    api = payload.get("api") or {}
    if "live" not in api:
        print("FAIL: demo payload api.live missing", file=sys.stderr)
        return 1

    section_html = render_to_string(
        "partials/cockpit/_live_world_map.html",
        {
            "cockpit": {"live_world_map": demo},
            "csp_nonce": "",
        },
    )
    for name in (
        "rmc-world-globe-loader",
        "rmc-world-globe-bridge",
        "rmc-world-globe-wow-plus",
        "rmc-world-globe-surface-elevation",
    ):
        section_html = re.sub(
            rf"/static/js/{name}\.[a-f0-9]+\.js",
            f"/static/js/{name}.js",
            section_html,
        )
    section_html = re.sub(
        r"/static/js/dist/world-globe\.mount\.[a-f0-9]+\.js",
        "/static/js/dist/world-globe.mount.js",
        section_html,
    )

    html = f"""<!DOCTYPE html>
<html lang="en" data-bs-theme="dark" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RunMyCampus — Global Footprint section preview (batch 1658)</title>
  <link rel="stylesheet" href="/static/css/design-tokens.css" />
  <link rel="stylesheet" href="/static/css/rmc-cp-200x.css" />
  <link rel="stylesheet" href="/static/css/rmc-cockpit-skin-v8.css" />
  <style>
    body {{ margin: 0; min-height: 100vh; background: #060910; color: var(--text-primary, #f8fafc); font-family: var(--font-sans, Inter, system-ui, sans-serif); }}
    .preview-chrome {{ position: sticky; top: 0; z-index: 20; display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 12px 20px; background: rgba(6, 9, 16, 0.92); border-bottom: 1px solid var(--hairline); backdrop-filter: blur(12px); }}
    .preview-chrome h1 {{ font-size: 14px; font-weight: 700; margin: 0; }}
    .preview-chrome p {{ margin: 0; font-size: 12px; color: var(--text-secondary); flex: 1 1 240px; }}
    .preview-chrome__actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .preview-chrome button {{ border: 1px solid var(--hairline); background: var(--surface-elevated); color: var(--text-primary); border-radius: 8px; padding: 6px 12px; font-size: 12px; cursor: pointer; }}
    .preview-chrome button[aria-pressed="true"] {{ border-color: rgba(99, 102, 241, 0.55); box-shadow: inset 0 0 0 1px rgba(99, 102, 241, 0.35); }}
    .preview-stage {{ max-width: 1280px; margin: 0 auto; padding: 28px 24px 48px; }}
    .preview-note {{ margin: 16px 0 0; font-size: 12px; color: var(--text-tertiary, #64748b); }}
    .visually-hidden-focusable:not(:focus):not(:focus-within) {{ position: absolute !important; width: 1px !important; height: 1px !important; padding: 0 !important; margin: -1px !important; overflow: hidden !important; clip: rect(0, 0, 0, 0) !important; white-space: nowrap !important; border: 0 !important; }}
    dialog#rmc-world-globe-school-sheet {{ max-width: 420px; border: 1px solid var(--hairline); border-radius: 12px; background: var(--surface-elevated); color: var(--text-primary); padding: 16px; }}
  </style>
</head>
<body>
  <header class="preview-chrome">
    <h1>Global Footprint · manager landing</h1>
    <p>Parity preview — renders <code>_live_world_map.html</code> with demo cockpit data.</p>
    <div class="preview-chrome__actions" role="group" aria-label="Preview mode">
      <button type="button" id="mode-online" aria-pressed="true">Online (WebGL globe)</button>
      <button type="button" id="mode-offline" aria-pressed="false">Offline (SVG + labels)</button>
    </div>
  </header>
  <main class="preview-stage">
    {section_html}
    <p class="preview-note" id="preview-hint">Use <code>Open Global Footprint Interactive.bat</code> for WebGL. Toggle Offline to verify SVG labels + legend parity.</p>
  </main>
  <script>
    (function () {{
      var btnOnline = document.getElementById("mode-online");
      var btnOffline = document.getElementById("mode-offline");
      function setPressed(offline) {{
        btnOnline.setAttribute("aria-pressed", offline ? "false" : "true");
        btnOffline.setAttribute("aria-pressed", offline ? "true" : "false");
      }}
      btnOffline.addEventListener("click", function () {{
        setPressed(true);
        window.dispatchEvent(new Event("offline"));
      }});
      btnOnline.addEventListener("click", function () {{
        setPressed(false);
        window.dispatchEvent(new Event("online"));
      }});
    }})();
  </script>
</body>
</html>
"""

    PREVIEW.write_text(html, encoding="utf-8")
    print(f"OK: wrote {PREVIEW.relative_to(ROOT)} ({len(payload_json)} bytes payload)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
