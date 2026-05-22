#!/usr/bin/env python3
"""GEOS-99 chrome locale coverage (operator + tenant chrome subset, batch 1388)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    manifest_path = ROOT / "locale/geos_chrome_manifest.json"
    if not manifest_path.is_file():
        print("verify_geos_locale_chrome_coverage: FAIL missing manifest", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    msgids = manifest["msgids"]
    locales = manifest.get("locales_required") or ["fr", "es", "ar", "pt_BR"]
    threshold = float(manifest.get("threshold_pct") or 95)

    failures: list[str] = []
    report: dict[str, float] = {}

    for locale in locales:
        path = ROOT / f"locale/geos_chrome/{locale}.json"
        if not path.is_file():
            failures.append(f"missing {path.relative_to(ROOT)}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        translated = sum(
            1 for m in msgids if (data.get(m) or "").strip() and data.get(m) != m
        )
        pct = 100.0 * translated / max(len(msgids), 1)
        report[locale] = round(pct, 1)
        if pct < threshold:
            failures.append(f"{locale} chrome {pct:.1f}% < {threshold}%")

    if failures:
        print("verify_geos_locale_chrome_coverage: FAIL", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    summary = ", ".join(f"{k}={v}%" for k, v in report.items())
    print(f"verify_geos_locale_chrome_coverage: GEOS_CHROME_LOCALE_PASS ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
