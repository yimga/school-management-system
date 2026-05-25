#!/usr/bin/env python3
"""Verify surface-preview mocks are interactive (tabs, filters, editable fields)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_surface_preview_interactivity.py", "--write"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        print(out, file=sys.stderr)
        print("verify_surface_preview_interactivity: FAIL", file=sys.stderr)
        return 1

    js = ROOT / "static/js/rmc-admin-v1-200x.js"
    text = js.read_text(encoding="utf-8")
    required = [
        "initSurfacePreviewChangeform",
        "initSurfacePreviewChangelist",
        "initCatalogExpandLinks",
        "data-cp-form-tab",
        "data-rmc-preview-save",
    ]
    index_surface = ROOT / "apps/siteconfig/admin_index_surface.py"
    if not index_surface.is_file():
        print("verify_surface_preview_interactivity: FAIL missing admin_index_surface.py")
        return 1
    missing = [s for s in required if s not in text]
    if missing:
        print(f"verify_surface_preview_interactivity: FAIL missing in {js.name}: {missing}")
        return 1

    print("verify_surface_preview_interactivity: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
