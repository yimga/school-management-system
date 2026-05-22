#!/usr/bin/env python3
"""Seed locale/geos_chrome/*.json from fr.json template (one-time GEOS-99 1388)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    manifest = json.loads((ROOT / "locale/geos_chrome_manifest.json").read_text(encoding="utf-8"))
    msgids = manifest["msgids"]
    fr = json.loads((ROOT / "locale/geos_chrome/fr.json").read_text(encoding="utf-8"))

    # es/pt derived from fr keys with manual overrides loaded from sibling files if present
    es = json.loads((ROOT / "locale/geos_chrome/es.json").read_text(encoding="utf-8")) if (ROOT / "locale/geos_chrome/es.json").is_file() else {}
    if not es:
        es = {m: fr.get(m, m) for m in msgids}
    for locale in ("es", "ar", "pt_BR"):
        path = ROOT / f"locale/geos_chrome/{locale}.json"
        if not path.is_file():
            path.write_text(json.dumps({m: m for m in msgids}, indent=2), encoding="utf-8")
    print("geos_chrome locales present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
