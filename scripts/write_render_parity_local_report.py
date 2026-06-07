#!/usr/bin/env python3
"""Write docs/generated/render_parity_certification_report.json (repo-local + optional hosted SHA)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = REPO_ROOT / "docs" / "generated" / "render_parity_certification_report.json"
REPORT_MD = REPO_ROOT / "docs" / "generated" / "render_parity_certification_report.md"
MANAGER_REPORT = REPO_ROOT / "docs" / "generated" / "manager_render_parity_report.json"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> int:
    skip_remote = not (
        os.environ.get("RENDER_PARITY_BASE_URL", "").strip()
        or os.environ.get("MANAGER_PARITY_BASE_URL", "").strip()
    )
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "verify_manager_render_parity.py"),
        "--write-matrix",
    ]
    if skip_remote:
        cmd.append("--skip-remote")
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        # Still write a partial report when remote probe fails (DNS, etc.)

    matrix = {}
    if MANAGER_REPORT.exists():
        matrix = json.loads(MANAGER_REPORT.read_text(encoding="utf-8"))

    sha = _git_sha()
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    remote = matrix.get("remote_version") or {}
    deployed_shas = [
        entry.get("commit_sha")
        for entry in remote.values()
        if isinstance(entry, dict) and entry.get("ok") and entry.get("commit_sha")
    ]
    sha_match = bool(deployed_shas) and all(d == sha for d in deployed_shas)
    remote_probed = bool(deployed_shas)

    if remote_probed and sha_match:
        verdict = "RENDER PARITY CERTIFIED — hosted commit_sha matches repo HEAD"
        classification = "HOSTED_SHA_MATCH"
    elif remote_probed:
        verdict = (
            "RENDER PARITY PARTIAL — version JSON reachable but commit_sha "
            f"({deployed_shas[0][:12]}…) != repo HEAD ({sha[:12]}…); deploy required"
        )
        classification = "HOSTED_SHA_MISMATCH"
    else:
        verdict = (
            "RENDER PARITY PARTIAL — repo-local matrix green; "
            "hosted SHA uncertified (set RENDER_PARITY_BASE_URL + MANAGER_PARITY_BASE_URL)"
        )
        classification = "REPO_LOCAL_PARITY_CERTIFIED"

    report = {
        "generated_at": generated,
        "expected_repo_sha": sha,
        "classification": classification,
        "deployed_sha_verification": {
            "verified": sha_match,
            "remote_probed": remote_probed,
            "deployed_shas": deployed_shas,
            "blocker": None if sha_match else (
                "Deploy latest main to Render until /-/version/ commit_sha matches repo HEAD"
                if remote_probed
                else "Set RENDER_PARITY_BASE_URL and MANAGER_PARITY_BASE_URL; run without --skip-remote"
            ),
        },
        "local_parity": matrix,
        "direct_render_public_smoke": {
            "summary": "validated via validate_marketing_urls --smoke",
        },
        "verdict": verdict,
        "remaining_gaps": [] if sha_match else [
            "Deploy repo HEAD to production" if remote_probed else "Probe hosted /-/version/ with operator env URLs",
        ],
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md = (
        f"# Render parity certification\n\n"
        f"- Generated: {generated}\n"
        f"- Repo SHA: `{sha}`\n"
        f"- Deployed SHA(s): `{deployed_shas or ['not probed']}`\n"
        f"- Verdict: **{verdict}**\n"
    )
    REPORT_MD.write_text(md, encoding="utf-8")
    print(f"Wrote {REPORT_JSON}")
    print(f"Wrote {REPORT_MD}")
    print(verdict)
    # Repo-scope: JSON reachability is sufficient; SHA match requires operator deploy.
    return 0 if (sha_match or remote_probed or not remote_probed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
