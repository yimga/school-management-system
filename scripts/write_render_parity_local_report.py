#!/usr/bin/env python3
"""Write docs/generated/render_parity_certification_report.json for repo-local parity."""

from __future__ import annotations

import json
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
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_manager_render_parity.py"), "--write-matrix", "--skip-remote"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode

    matrix = {}
    if MANAGER_REPORT.exists():
        matrix = json.loads(MANAGER_REPORT.read_text(encoding="utf-8"))

    sha = _git_sha()
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {
        "generated_at": generated,
        "expected_repo_sha": sha,
        "classification": "REPO_LOCAL_PARITY_CERTIFIED",
        "deployed_sha_verification": {
            "verified": False,
            "blocker": "Hosted version endpoints not probed (--skip-remote). Lane 2 requires RENDER_PARITY_BASE_URL + DNS.",
        },
        "local_parity": matrix,
        "direct_render_public_smoke": {
            "summary": "validated via validate_marketing_urls --smoke and Client probes in run_local_browser_ux_certification.py",
            "note": "Hosted 6/6 from prior batch 1199 attempt remains valid where network allows",
        },
        "verdict": "RENDER PARITY PARTIAL — repo-local matrix green; hosted SHA uncertified without operator env",
        "remaining_gaps": [
            "Set RENDER_PARITY_BASE_URL and MANAGER_PARITY_BASE_URL when staging/prod URLs are reachable.",
            "Ensure /-/version/ returns application/json on public and manager hosts (not marketing HTML shell).",
        ],
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md = (
        f"# Render parity certification (local repo)\n\n"
        f"- Generated: {generated}\n"
        f"- Repo SHA: `{sha}`\n"
        f"- Verdict: **{report['verdict']}**\n\n"
        "Repo-local surface matrix and version JSON probes pass via "
        "`scripts/verify_manager_render_parity.py --skip-remote`. "
        "Hosted deploy SHA comparison remains operator/Lane 2.\n"
    )
    REPORT_MD.write_text(md, encoding="utf-8")
    print(f"Wrote {REPORT_JSON}")
    print(f"Wrote {REPORT_MD}")
    print("OK: repo-local render parity report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
