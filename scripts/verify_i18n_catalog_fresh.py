#!/usr/bin/env python3
"""
Fail if locale/en/LC_MESSAGES/django.po is missing any string found by the i18n scanner.

Run after template/Python changes; fix with:
  python manage.py sync_i18n_catalog --compile

  --warn-stale   print msgids in .po but not in codebase (advisory)
  --strict-stale exit 1 if any stale entries exist (optional hygiene)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.siteconfig.i18n_catalog_builder import verify_en_catalog_against_codebase

    ap = argparse.ArgumentParser(description="Verify en django.po covers scanned strings")
    ap.add_argument(
        "--warn-stale",
        action="store_true",
        help="Print msgids present in .po but not found by scanner",
    )
    ap.add_argument(
        "--strict-stale",
        action="store_true",
        help="Exit 1 when stale entries exist (use after --prune-stale or manual cleanup)",
    )
    args = ap.parse_args()

    missing, stale = verify_en_catalog_against_codebase(ROOT)
    if missing:
        print(
            f"FAIL: {len(missing)} scanned strings missing from locale/en/LC_MESSAGES/django.po",
            file=sys.stderr,
        )
        print("Fix: python manage.py sync_i18n_catalog --compile", file=sys.stderr)
        for m in sorted(missing)[:40]:
            print(f"  {m[:120]!r}", file=sys.stderr)
        if len(missing) > 40:
            print(f"  ... and {len(missing) - 40} more", file=sys.stderr)
        return 1

    if args.warn_stale or args.strict_stale:
        if stale:
            print(f"INFO: {len(stale)} msgids in .po not seen by scanner (stale / manual).")
            if args.warn_stale:
                for s in sorted(stale)[:25]:
                    print(f"  {s[:120]!r}")
                if len(stale) > 25:
                    print(f"  ... and {len(stale) - 25} more")
            if args.strict_stale:
                return 1
        else:
            print("INFO: no stale .po entries vs scanner.")

    print("OK: en django.po covers all scanned translatable strings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
