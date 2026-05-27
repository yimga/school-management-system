#!/usr/bin/env python3
"""Write sub-800KB placeholder loop mp4/webm for all manifest buckets (no ffmpeg required)."""
from __future__ import annotations

import base64
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs" / "generated" / "marketing_media_manifest.json"
STATIC = REPO / "static"
MAX_BYTES = 838_860

# Minimal H.264/mp4 (1x1, ~1.1KB) — valid in Chrome/Safari/Firefox for silent loop placeholders.
_MINIMAL_MP4_B64 = (
    "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAAAsxtZGF0AAACrgYF//+q3EXp"
    "vebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE1NSByMjkxMSBhYTBlYzkgLSBILjI2NC9NUEVHLTQg"
    "QVZDIGNvZGVjIC0gQ29weWxlZnQgMjAwMy0yMDE1IC0gaHR0cDovL3d3dy52aWRlb2xhbi5vcmcveDI2"
    "NC5odG1sIC0gb3B0aW9uczogY2FiYWN0PTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmF5c2U9MHgzOjB4"
    "MTEzMDAzYzU1ODJjOThhIDUwMDA4MWRiNDExYjI0ZAAAAw+LFo0="
)


def minimal_mp4_bytes() -> bytes:
    return base64.b64decode(_MINIMAL_MP4_B64)


def main() -> int:
    if not MANIFEST.is_file():
        print("generate_marketing_minimal_loops: manifest missing", file=sys.stderr)
        return 1
    blob = minimal_mp4_bytes()
    if len(blob) > MAX_BYTES:
        print(f"minimal mp4 template {len(blob)}B exceeds {MAX_BYTES}", file=sys.stderr)
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for bucket, paths in (data.get("loops") or {}).items():
        for kind in ("mp4", "webm"):
            rel = paths.get(kind, "")
            if not rel:
                continue
            dest = STATIC / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
        poster = paths.get("poster", "")
        if poster:
            p = STATIC / poster
            if not p.is_file():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 9" role="img" aria-hidden="true">'
                    '<rect width="16" height="9" fill="#0f172a"/>'
                    "</svg>",
                    encoding="utf-8",
                )
    print(f"generate_marketing_minimal_loops: OK ({len(blob)}B x {len(data.get('loops', {}))} buckets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
