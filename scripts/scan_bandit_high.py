#!/usr/bin/env python3
"""Bandit HIGH-severity drift detector (incremental burndown gate).

Counts ``issue_severity == HIGH`` findings from ``bandit -r apps config -f json``.
Does not fail on MEDIUM/LOW. Use ``--update-baseline`` after intentional burndown.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-bandit-high.json"
SCAN_ROOTS = ("apps", "config")


def _run_bandit() -> tuple[list[dict], str | None]:
    cmd = [
        sys.executable,
        "-m",
        "bandit",
        "-r",
        *SCAN_ROOTS,
        "-f",
        "json",
        "-lll",
        "-q",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError:
        return [], "bandit not installed (`pip install bandit`)"
    except subprocess.TimeoutExpired:
        return [], "bandit timed out"
    if not proc.stdout.strip():
        return [], proc.stderr.strip() or f"bandit exit {proc.returncode}"
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return [], f"bandit json parse failed: {exc}"
    return list(payload.get("results") or []), None


def _high_findings(results: list[dict]) -> list[dict]:
    out = []
    for item in results:
        if str(item.get("issue_severity", "")).upper() != "HIGH":
            continue
        out.append(
            {
                "path": str(item.get("filename", "")).replace("\\", "/"),
                "line": int(item.get("line_number") or 0),
                "test_id": str(item.get("test_id") or ""),
                "issue_text": str(item.get("issue_text") or "")[:160],
            }
        )
    out.sort(key=lambda row: (row["path"], row["line"], row["test_id"]))
    return out


def _payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "bandit HIGH severity count must not exceed baseline",
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results, err = _run_bandit()
    if err:
        print(f"scan_bandit_high: {err}", file=sys.stderr)
        return 0 if not args.compare else 1

    findings = _high_findings(results)
    if args.json:
        print(json.dumps(_payload(findings), indent=2))
        return 0

    print(f"scan_bandit_high: {len(findings)} HIGH finding(s)")

    if args.update_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(_payload(findings), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")
        return 0

    if not args.compare:
        for row in findings[:20]:
            print(f"  {row['path']}:{row['line']} {row['test_id']}")
        if len(findings) > 20:
            print(f"  ... and {len(findings) - 20} more")
        return 0

    if not BASELINE_PATH.exists():
        print("No baseline — run with --update-baseline first.")
        return 1 if findings else 0

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline_count = int(baseline.get("finding_count", 0))
    current_count = len(findings)
    if current_count > baseline_count:
        print(
            f"REGRESSION: HIGH count {current_count} > baseline {baseline_count}",
            file=sys.stderr,
        )
        baseline_keys = {
            (f["path"], f["line"], f["test_id"]) for f in baseline.get("findings", [])
        }
        current_keys = {(f["path"], f["line"], f["test_id"]) for f in findings}
        for key in sorted(current_keys - baseline_keys)[:15]:
            print(f"  NEW HIGH: {key[0]}:{key[1]} {key[2]}", file=sys.stderr)
        return 1
    print(f"scan_bandit_high --compare OK ({current_count} <= {baseline_count})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
