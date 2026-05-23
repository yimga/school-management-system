#!/usr/bin/env python3
"""GEOS Lane 2 ingest: verify Render-deployed SHA matches local HEAD.

Honest contract:
  * No env credentials → `external_pending` evidence, exit 0 (gate stays soft).
  * RENDER_API_KEY + RENDER_SERVICE_ID set → query Render API, fetch latest
    succeeded deploy, compare SHA to `git rev-parse HEAD`.
    - Match → `verified_live` evidence, exit 0.
    - Mismatch → `drift` evidence, exit 1.

Evidence is written to `var/lane2-evidence/render.json`. The GEOS matrix
verifier (`verify_greatest_education_os_matrix.py`) reads
`docs/external_dependencies_register.json` for `verified_live` status — operator
reviews evidence and manually updates the register entry. This script does
NOT auto-edit the register (preserves honesty contract).

Operator workflow:
    export RENDER_API_KEY=rnd_xxx
    export RENDER_SERVICE_ID=srv-xxx
    python scripts/verify_render_live_sha.py
    # → reads evidence file, decides whether to flip register to verified_live

Usage:
    python scripts/verify_render_live_sha.py [--strict]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "var" / "lane2-evidence"
EVIDENCE_PATH = EVIDENCE_DIR / "render.json"
RENDER_API_BASE = "https://api.render.com/v1"


def _local_head_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            return None
        return (out.stdout or "").strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _fetch_latest_deploy_sha(api_key: str, service_id: str) -> tuple[str | None, str]:
    """Return (sha, note). sha is None on failure; note explains the path."""
    url = f"{RENDER_API_BASE}/services/{service_id}/deploys?limit=5"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return None, f"render_api_http_{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"render_api_unreachable: {exc}"
    except json.JSONDecodeError:
        return None, "render_api_invalid_json"

    # Render API returns either a top-level list of {deploy: {...}} envelopes
    # or a bare list of deploy dicts; handle both.
    if not isinstance(data, list):
        return None, "render_api_unexpected_shape"
    for entry in data:
        deploy = entry.get("deploy") if isinstance(entry, dict) and "deploy" in entry else entry
        if not isinstance(deploy, dict):
            continue
        if (deploy.get("status") or "").lower() != "live":
            continue
        commit = deploy.get("commit") or {}
        sha = commit.get("id") if isinstance(commit, dict) else None
        if isinstance(sha, str) and sha:
            return sha, "render_api_ok"
    return None, "render_api_no_live_deploy"


def _write_evidence(payload: dict) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when credentials are absent (forces Lane 2 evidence in CI).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("RENDER_API_KEY")
    service_id = os.environ.get("RENDER_SERVICE_ID")
    head_sha = _local_head_sha()
    now = datetime.now(timezone.utc).isoformat()

    if not api_key or not service_id:
        payload = {
            "generated_at": now,
            "status": "external_pending",
            "reason": "env_absent",
            "missing_env": [k for k, v in {
                "RENDER_API_KEY": api_key,
                "RENDER_SERVICE_ID": service_id,
            }.items() if not v],
            "local_head_sha": head_sha,
            "register_pillar": "aws",
            "register_section_id": "hosting_render_sha_parity",
        }
        _write_evidence(payload)
        print(
            f"verify_render_live_sha: external_pending "
            f"(missing {','.join(payload['missing_env'])}); "
            f"local HEAD={head_sha or 'unknown'}"
        )
        return 1 if args.strict else 0

    deployed_sha, note = _fetch_latest_deploy_sha(api_key, service_id)
    if not deployed_sha:
        payload = {
            "generated_at": now,
            "status": "external_pending",
            "reason": note,
            "local_head_sha": head_sha,
            "register_pillar": "aws",
            "register_section_id": "hosting_render_sha_parity",
        }
        _write_evidence(payload)
        print(f"verify_render_live_sha: external_pending ({note})")
        return 1 if args.strict else 0

    parity = bool(head_sha and head_sha == deployed_sha)
    payload = {
        "generated_at": now,
        "status": "verified_live" if parity else "drift",
        "reason": "sha_match" if parity else "sha_mismatch",
        "local_head_sha": head_sha,
        "deployed_sha": deployed_sha,
        "register_pillar": "aws",
        "register_section_id": "hosting_render_sha_parity",
    }
    _write_evidence(payload)

    if parity:
        print(f"verify_render_live_sha: verified_live (sha={deployed_sha[:12]})")
        return 0
    print(
        f"verify_render_live_sha: drift "
        f"(local={head_sha[:12] if head_sha else '?'} vs deployed={deployed_sha[:12]})"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
