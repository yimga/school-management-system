#!/usr/bin/env python
"""Service-worker CACHE_VERSION shape + monotonicity gate.

Seven-pillar audit P9 follow-up. The platform's offline-first contract
ships in [`static/js/service-worker.js`](../static/js/service-worker.js),
versioned via a single ``const CACHE_VERSION = "sms-vMAJOR.MINOR.PATCH-<slug>-<YYYY-MM-DD>"``
declaration. Every wave that ships new CSS/JS must bump this token so
that browsers fetch fresh assets and the stale-cache class of bug stays
closed (see CLAUDE.md "Migration / deploy checklist for a wave").

This gate enforces two invariants:

  1. **Shape:** the string matches
     ``sms-vMAJOR.MINOR.PATCH(-DECORATOR)?-YYYY-MM-DD``.
  2. **Monotonicity (optional, --check-monotonic):** the parsed
     (MAJOR, MINOR, PATCH) of HEAD's SW is >= the value already stored
     under ``var/security-audit-baseline-service-worker-version.json``.
     On a wave that bumps the SW, the baseline is updated in the same
     commit; CI re-runs the gate without --check-monotonic-write so
     bumps don't accidentally regress.

Usage:
    python scripts/verify_service_worker_version.py             # validate shape
    python scripts/verify_service_worker_version.py --json
    python scripts/verify_service_worker_version.py --write-baseline
    python scripts/verify_service_worker_version.py --check-monotonic
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SW_PATH = REPO_ROOT / "static" / "js" / "service-worker.js"
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-service-worker-version.json"
)

_VERSION_DECL_RE = re.compile(
    r'const\s+CACHE_VERSION\s*=\s*"(?P<value>[^"]+)"\s*;'
)
_SHAPE_RE = re.compile(
    r"^sms-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<slug>[a-z0-9][a-z0-9-]*?))?"
    r"-(?P<date>\d{4}-\d{2}-\d{2})$"
)


@dataclass
class ParsedVersion:
    raw: str
    major: int
    minor: int
    patch: int
    slug: str | None
    date: str
    valid: bool
    reason: str | None

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)


def _read_sw_version() -> ParsedVersion:
    if not SW_PATH.exists():
        return ParsedVersion(
            raw="", major=0, minor=0, patch=0, slug=None, date="",
            valid=False, reason=f"service-worker not found at {SW_PATH}",
        )
    text = SW_PATH.read_text(encoding="utf-8")
    decl = _VERSION_DECL_RE.search(text)
    if decl is None:
        return ParsedVersion(
            raw="", major=0, minor=0, patch=0, slug=None, date="",
            valid=False,
            reason="CACHE_VERSION declaration not found in service-worker.js",
        )
    raw = decl.group("value")
    m = _SHAPE_RE.match(raw)
    if m is None:
        return ParsedVersion(
            raw=raw, major=0, minor=0, patch=0, slug=None, date="",
            valid=False,
            reason=(
                f"CACHE_VERSION '{raw}' does not match "
                "sms-vMAJOR.MINOR.PATCH[-slug]-YYYY-MM-DD"
            ),
        )
    # Validate the date component is parseable.
    try:
        datetime.strptime(m.group("date"), "%Y-%m-%d")
    except ValueError:
        return ParsedVersion(
            raw=raw, major=0, minor=0, patch=0, slug=None, date=m.group("date"),
            valid=False,
            reason=f"date component '{m.group('date')}' is not a valid YYYY-MM-DD",
        )
    return ParsedVersion(
        raw=raw,
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        slug=m.group("slug"),
        date=m.group("date"),
        valid=True,
        reason=None,
    )


def _load_baseline() -> ParsedVersion | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return ParsedVersion(
        raw=data.get("raw", ""),
        major=int(data.get("major", 0)),
        minor=int(data.get("minor", 0)),
        patch=int(data.get("patch", 0)),
        slug=data.get("slug"),
        date=data.get("date", ""),
        valid=bool(data.get("valid", False)),
        reason=data.get("reason"),
    )


def _write_baseline(version: ParsedVersion) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "static/js/service-worker.js CACHE_VERSION must match "
            "sms-vMAJOR.MINOR.PATCH[-slug]-YYYY-MM-DD and only move forward"
        ),
        **asdict(version),
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _print_summary(version: ParsedVersion) -> None:
    if version.valid:
        slug = version.slug or "(no-slug)"
        print(
            f"service-worker: {version.raw}  "
            f"v{version.major}.{version.minor}.{version.patch} "
            f"slug={slug} date={version.date}"
        )
    else:
        print(f"service-worker: INVALID  raw='{version.raw}'  reason={version.reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--write-baseline", action="store_true",
        help="Persist the current SW version as the baseline (do this when a wave ships).",
    )
    parser.add_argument(
        "--check-monotonic", action="store_true",
        help="Fail if HEAD's SW (MAJOR,MINOR,PATCH) is less than the baseline's.",
    )
    args = parser.parse_args()

    version = _read_sw_version()
    if args.json:
        print(json.dumps(asdict(version), indent=2, sort_keys=True))

    if not version.valid:
        if not args.json:
            _print_summary(version)
        return 1

    if not args.json:
        _print_summary(version)

    if args.write_baseline:
        _write_baseline(version)
        if not args.json:
            print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")
        return 0

    if args.check_monotonic:
        baseline = _load_baseline()
        if baseline is None:
            if not args.json:
                print("  no baseline yet — run with --write-baseline first")
            return 0
        if version.as_tuple() < baseline.as_tuple():
            if not args.json:
                print(
                    f"  REGRESSION: current v{version.major}.{version.minor}."
                    f"{version.patch} < baseline v{baseline.major}.{baseline.minor}."
                    f"{baseline.patch}"
                )
            return 1
        if not args.json:
            print(
                f"  monotonic OK (baseline v{baseline.major}.{baseline.minor}."
                f"{baseline.patch})"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
