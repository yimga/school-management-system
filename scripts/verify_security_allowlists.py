#!/usr/bin/env python3
"""
P0 gate: security allowlist JSON discipline (metadata + periodic review dates).

Covers per-file entries (raw_sql, csrf_exempt, allow_any) plus a top-level
``manifest_last_reviewed`` (bundle review date for the whole file), and policy
documents (broad_except_allowlist.json, tracked_root_allowlist.json) with top-level
last_reviewed.

Run after lint_csrf_exempt_usage / lint_allow_any_usage / lint_raw_sql_usage so paths stay aligned.
Usage: python scripts/verify_security_allowlists.py [--base DIR] [--max-age-days N]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RAW_SQL_REQUIRED = ("expected_count", "reason", "last_reviewed")
CSRF_REQUIRED = (
    "expected_count",
    "owner",
    "verdict",
    "auth_model",
    "replay_protection",
    "rate_limiting",
    "audit_logging",
    "notes",
    "last_reviewed",
)
ALLOW_ANY_REQUIRED = (
    "expected_count",
    "owner",
    "verdict",
    "auth_model",
    "data_exposure",
    "rate_limiting",
    "audit_logging",
    "notes",
    "last_reviewed",
)

BROAD_EXCEPT_ROOT_KEYS = ("policy", "issue_link", "last_reviewed", "allowed_counts")


def _parse_reviewed(value: object) -> date:
    text = str(value or "").strip()
    if not text or len(text) != 10:
        raise ValueError(f"invalid last_reviewed date: {value!r}")
    return date.fromisoformat(text)


def _check_entries(
    label: str,
    path: Path,
    required: tuple[str, ...],
    max_age: timedelta,
) -> list[str]:
    errs: list[str] = []
    if not path.is_file():
        return [f"{label}: missing {path}"]
    data = json.loads(path.read_text(encoding="utf-8"))
    today = date.today()
    mlr = data.get("manifest_last_reviewed")
    if not str(mlr or "").strip():
        errs.append(
            f"{label}: missing top-level 'manifest_last_reviewed' "
            "(ISO YYYY-MM-DD; operator bundle review for this allowlist file)"
        )
    else:
        try:
            bundle = _parse_reviewed(mlr)
        except ValueError as exc:
            errs.append(f"{label}: manifest_last_reviewed {exc}")
        else:
            if today - bundle > max_age:
                errs.append(
                    f"{label}: manifest_last_reviewed {bundle.isoformat()} is older than allowed"
                )

    files = data.get("files")
    if not isinstance(files, dict):
        errs.append(f"{label}: top-level 'files' must be an object")
        return errs
    for rel, entry in sorted(files.items()):
        if not isinstance(entry, dict):
            errs.append(f"{label}: {rel} entry must be an object")
            continue
        missing = [k for k in required if not str(entry.get(k, "")).strip()]
        if missing:
            errs.append(f"{label}: {rel} missing {', '.join(missing)}")
            continue
        try:
            reviewed = _parse_reviewed(entry["last_reviewed"])
        except ValueError as exc:
            errs.append(f"{label}: {rel} last_reviewed {exc}")
            continue
        if today - reviewed > max_age:
            errs.append(
                f"{label}: {rel} last_reviewed {reviewed.isoformat()} is older than allowed"
            )
    return errs


def _check_broad_except_policy(path: Path, max_age: timedelta) -> list[str]:
    label = "broad_except"
    errs: list[str] = []
    if not path.is_file():
        return [f"{label}: missing {path}"]
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in BROAD_EXCEPT_ROOT_KEYS:
        if key not in data:
            errs.append(f"{label}: missing top-level key {key!r}")
    if errs:
        return errs
    if not str(data.get("policy", "")).strip():
        errs.append(f"{label}: policy must be non-empty")
    if not str(data.get("issue_link", "")).strip():
        errs.append(f"{label}: issue_link must be non-empty")
    counts = data.get("allowed_counts")
    if not isinstance(counts, dict):
        errs.append(f"{label}: allowed_counts must be an object")
        return errs
    today = date.today()
    try:
        reviewed = _parse_reviewed(data["last_reviewed"])
    except ValueError as exc:
        return [f"{label}: last_reviewed {exc}"]
    if today - reviewed > max_age:
        errs.append(
            f"{label}: last_reviewed {reviewed.isoformat()} is older than allowed "
            f"({max_age.days} days)"
        )
    return errs


def _check_tracked_root_allowlist(path: Path, max_age: timedelta) -> list[str]:
    label = "tracked_root"
    errs: list[str] = []
    if not path.is_file():
        return [f"{label}: missing {path}"]
    data = json.loads(path.read_text(encoding="utf-8"))
    if "last_reviewed" not in data:
        errs.append(f"{label}: missing top-level key 'last_reviewed'")
    allowed = data.get("allowed")
    if not isinstance(allowed, list):
        errs.append(f"{label}: top-level 'allowed' must be a JSON array")
        return errs
    for i, item in enumerate(allowed):
        if not isinstance(item, str) or not item.strip():
            errs.append(f"{label}: allowed[{i}] must be a non-empty string")
    if errs:
        return errs
    today = date.today()
    try:
        reviewed = _parse_reviewed(data["last_reviewed"])
    except ValueError as exc:
        return [f"{label}: last_reviewed {exc}"]
    if today - reviewed > max_age:
        errs.append(
            f"{label}: last_reviewed {reviewed.isoformat()} is older than allowed "
            f"({max_age.days} days)"
        )
    return errs


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify security allowlist JSON contracts.")
    parser.add_argument("--base", default=".", help="Repo root")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=730,
        help="Fail if last_reviewed is older than this many days (default: 730).",
    )
    args = parser.parse_args()
    base = Path(args.base).resolve()
    max_age = timedelta(days=max(args.max_age_days, 1))

    errors: list[str] = []
    checks = [
        ("raw_sql", base / "scripts/allowlists/raw_sql_allowlist.json", RAW_SQL_REQUIRED),
        ("csrf_exempt", base / "scripts/allowlists/csrf_exempt_allowlist.json", CSRF_REQUIRED),
        ("allow_any", base / "scripts/allowlists/allow_any_allowlist.json", ALLOW_ANY_REQUIRED),
    ]
    for label, path, req in checks:
        errors.extend(_check_entries(label, path, req, max_age))

    errors.extend(
        _check_broad_except_policy(
            base / "scripts/allowlists/broad_except_allowlist.json", max_age
        )
    )
    errors.extend(
        _check_tracked_root_allowlist(
            base / "scripts/allowlists/tracked_root_allowlist.json", max_age
        )
    )

    if errors:
        print("verify_security_allowlists: FAIL", file=sys.stderr)
        for msg in errors:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    print(
        "verify_security_allowlists: PASS "
        "(manifest_last_reviewed + per-file last_reviewed; broad_except + tracked_root policy dates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
