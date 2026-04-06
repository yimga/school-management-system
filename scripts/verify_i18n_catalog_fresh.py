#!/usr/bin/env python3
"""
Fail if locale/en/LC_MESSAGES/django.po is missing any string found by the i18n scanner.

Run after template/Python changes; fix with:
  python manage.py sync_i18n_catalog --compile

  --warn-stale   print msgids in .po but not in codebase (advisory)
  --strict-stale exit 1 if any stale entries exist (optional hygiene)

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify en django.po covers scanned strings")
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (default: this repository root)",
    )
    parser.add_argument(
        "--warn-stale",
        action="store_true",
        help="Print msgids present in .po but not found by scanner",
    )
    parser.add_argument(
        "--strict-stale",
        action="store_true",
        help="Exit 1 when stale entries exist (use after --prune-stale or manual cleanup)",
    )
    return parser


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    return _build_parser().parse_args(argv)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _configure_django(root: Path) -> None:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_i18n_catalog_fresh: {exc}", file=sys.stderr)
        return 1

    _configure_django(root)

    from apps.siteconfig.i18n_catalog_builder import verify_en_catalog_against_codebase

    missing, stale = verify_en_catalog_against_codebase(root)
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
    raise SystemExit(main(None))
