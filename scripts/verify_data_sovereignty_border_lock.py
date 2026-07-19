#!/usr/bin/env python3
"""Verify data-sovereignty border-lock artefacts are in place.

Checks:
  1. ``docs/SOVEREIGNTY_PLEDGE.md`` exists and is non-empty.
  2. ``RegionalDatabaseMiddleware`` is referenced in ``config/settings.py``
     MIDDLEWARE list.
  3. Router enforce call sites exist (``enforce_region_match`` in
     ``apps/siteconfig/db_router.py``).
  4. ``config/settings_test.py`` registers ``replica_eu_central`` and
     ``replica_us_east`` stub aliases.

Prints ``DATA_SOVEREIGNTY_BORDER_LOCK_PASS`` on success, exits 1 on any
failure.

Stdlib-only — no Django import required.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

CHECKS: list[tuple[str, bool, str]] = []


def _check(label: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((label, ok, detail))
    status = "OK" if ok else "FAIL"
    msg = f"  [{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def main() -> int:
    print("verify_data_sovereignty_border_lock")
    print("=" * 50)

    pledge = REPO / "docs" / "SOVEREIGNTY_PLEDGE.md"
    _check(
        "pledge file exists",
        pledge.is_file() and pledge.stat().st_size > 100,
        str(pledge.relative_to(REPO)),
    )

    settings_py = REPO / "config" / "settings.py"
    settings_text = settings_py.read_text(encoding="utf-8") if settings_py.is_file() else ""
    _check(
        "RegionalDatabaseMiddleware in MIDDLEWARE",
        "RegionalDatabaseMiddleware" in settings_text,
    )

    db_router = REPO / "apps" / "siteconfig" / "db_router.py"
    router_text = db_router.read_text(encoding="utf-8") if db_router.is_file() else ""
    _check(
        "enforce_region_match call site in db_router",
        "enforce_region_match" in router_text,
    )

    settings_test = REPO / "config" / "settings_test.py"
    test_text = settings_test.read_text(encoding="utf-8") if settings_test.is_file() else ""
    _check(
        "replica_eu_central in settings_test",
        "replica_eu_central" in test_text,
    )
    _check(
        "replica_us_east in settings_test",
        "replica_us_east" in test_text,
    )

    print()
    failed = [c for c in CHECKS if not c[1]]
    if failed:
        print(f"FAILED: {len(failed)} check(s)")
        for label, _, detail in failed:
            print(f"  - {label}: {detail}")
        return 1

    print("DATA_SOVEREIGNTY_BORDER_LOCK_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
