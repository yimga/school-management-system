#!/usr/bin/env python
"""Viewport-engine wiring scanner (v4.00.0 zero-tolerance gate).

Every top-level shell template under ``templates/`` MUST include
``partials/rmc_viewport_engine.html`` in its <head> so that the three-engine
adaptive layout binds before first paint. This scanner enforces it.

A "top-level shell" is any template that:
  * lives directly under ``templates/`` (one level deep), AND
  * contains ``<html`` and ``<head`` opening tags

The shell list is intentionally not allowlisted — every new shell introduced
by a future wave is automatically covered.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPO_ROOT / "templates"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-viewport-class-coverage.json"

REQUIRED_INCLUDE = "partials/rmc_viewport_engine.html"


def _candidate_shells():
    if not TEMPLATES_ROOT.exists():
        return
    for path in sorted(TEMPLATES_ROOT.glob("*.html")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "<html" in text and "<head" in text:
            yield path, text


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for path, text in _candidate_shells():
        if REQUIRED_INCLUDE in text:
            continue
        findings.append({
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "reason": f"missing {{% include \"{REQUIRED_INCLUDE}\" %}} in shell <head>",
        })
    findings.sort(key=lambda item: item["path"])
    return findings


def _baseline_payload(findings):
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            f"every top-level shell must include {REQUIRED_INCLUDE} so the "
            "three-engine viewport classifier runs before first paint"
        ),
        "scan_dirs": [TEMPLATES_ROOT.relative_to(REPO_ROOT).as_posix()],
        "required_include": REQUIRED_INCLUDE,
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline():
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_summary(findings):
    print(f"viewport_class_coverage scan: {len(findings)} shell(s) without engine wiring")
    for f in findings:
        print(f"  {f['path']}  -> {f['reason']}")


def _write_baseline(findings):
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(findings):
    baseline = _load_baseline()
    if baseline is None:
        _print_summary(findings)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_set = {f["path"] for f in baseline.get("findings", [])}
    current_set = {f["path"] for f in findings}
    new = current_set - baseline_set
    _print_summary(findings)
    if new:
        print("\nNEW shells without viewport-engine wiring:")
        for p in sorted(new):
            print(f"  {p}")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = _scan()
    if args.json:
        print(json.dumps(_baseline_payload(findings), indent=2, sort_keys=True))
        return 0
    if args.compare:
        return _compare(findings)
    _print_summary(findings)
    _write_baseline(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
