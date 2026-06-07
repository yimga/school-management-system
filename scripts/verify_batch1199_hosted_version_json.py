#!/usr/bin/env python3
"""
Batch 1199 — hosted version JSON reachability (/-/version/ or alias paths).

Passes when remote probes return application/json with commit_sha.
SHA drift vs repo HEAD is recorded but does not fail repo-scope closure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> int:
    report_path = REPO / "docs/generated/manager_render_parity_report.json"
    if not report_path.is_file():
        if not os.environ.get("RENDER_PARITY_BASE_URL", "").strip():
            print(
                "BATCH1199_HOSTED_VERSION_JSON_SKIP (no report; set RENDER_PARITY_BASE_URL)",
                file=sys.stderr,
            )
            return 0
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts/verify_manager_render_parity.py"),
            ],
            cwd=REPO,
        )
        if proc.returncode != 0:
            print("BATCH1199_HOSTED_VERSION_JSON_FAIL", file=sys.stderr)
            return 1
        report_path = REPO / "docs/generated/manager_render_parity_report.json"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    remote = report.get("remote_version") or {}
    ok_hosts = [
        label
        for label, entry in remote.items()
        if isinstance(entry, dict) and entry.get("ok") and entry.get("commit_sha")
    ]
    if not ok_hosts and os.environ.get("RENDER_PARITY_BASE_URL", "").strip():
        print("BATCH1199_HOSTED_VERSION_JSON_FAIL (no remote JSON)", file=sys.stderr)
        return 1
    if not ok_hosts:
        print("BATCH1199_HOSTED_VERSION_JSON_SKIP (local-only; no remote env)")
        return 0

    head = _git_sha()
    deployed = remote[ok_hosts[0]].get("commit_sha", "")
    drift = head != "unknown" and deployed and head != deployed
    print(
        "BATCH1199_HOSTED_VERSION_JSON_PASS "
        f"({len(ok_hosts)} host(s); probe={remote[ok_hosts[0]].get('probe_path')}; "
        f"sha_drift={'yes' if drift else 'no'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
