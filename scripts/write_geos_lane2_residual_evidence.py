#!/usr/bin/env python3
"""Write on-disk GEOS Lane 2 evidence for batches 1170, 1199, and 1175 intake.

Honest contract: never fabricates Stripe charge IDs or hosted deploy SHA matches.
Metadata health and repo-local parity may be recorded as repo_complete / repo_verified.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "var" / "evidence" / "geos-99"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)}")


def capture_batch_1170(school: str, *, production_ping: bool) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_lane2_operator_playbook.py"),
        f"--school={school}",
        "--batch=1170",
        "--init-evidence",
        "--write-report",
    ]
    if production_ping:
        cmd.append("--production-ping")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    preflight_path = ROOT / "docs" / "generated" / "lane2_operator_preflight.json"
    preflight: dict = {}
    if preflight_path.is_file():
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))

    stripe_checks = []
    for batch in preflight.get("batches") or []:
        if batch.get("batch") == "1170":
            stripe_checks = batch.get("gateway_checks") or []
            break

    def _stripe_metadata_healthy(check: dict) -> bool:
        if check.get("provider") != "stripe" or check.get("mode") != "metadata":
            return False
        if check.get("exit_code") != 0:
            return False
        result = check.get("result") or {}
        rows = result.get("results") if isinstance(result, dict) else []
        if not rows:
            return False
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "").lower()
            if status in {"ok", "healthy", "configured", "ready"}:
                return True
            if status in {"missing_credentials", "error", "failed", "unconfigured"}:
                return False
        return False

    metadata_ok = any(_stripe_metadata_healthy(c) for c in stripe_checks)

    stamp = _utc_now()[:10]
    out_path = EVIDENCE / "psp" / "stripe" / f"lane2_batch1170_preflight_{stamp}.json"
    payload = {
        "schema_version": 1,
        "batch": "1170",
        "school_slug": school,
        "recorded_at": _utc_now(),
        "evidence_status": "verified_live" if metadata_ok else "repo_complete",
        "evidence_kind": "stripe_metadata_gateway_health",
        "metadata_gateway_ok": metadata_ok,
        "playbook_exit_code": proc.returncode,
        "phase1_charge_evidence": "var/evidence/geos-99/psp/stripe/phase1_platform_charge_evidence.json",
        "phase1_charge_status": "pending_operator",
        "phase2_connect_evidence": "var/evidence/geos-99/psp/stripe/phase2_connect_pilot_evidence.json",
        "phase2_connect_status": "pending_operator",
        "gateway_checks": stripe_checks,
        "notes": (
            "verified_live here means metadata health check passed for the tenant; "
            "stripe_global_cards flip still requires supervised phase1 charge JSON."
        ),
    }
    _write_json(out_path, payload)
    return {"path": str(out_path.relative_to(ROOT)), "metadata_ok": metadata_ok, "exit_code": proc.returncode}


def capture_batch_1199() -> dict:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "write_render_parity_local_report.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    cert_path = ROOT / "docs" / "generated" / "render_parity_certification_report.json"
    cert: dict = {}
    if cert_path.is_file():
        cert = json.loads(cert_path.read_text(encoding="utf-8"))

    sha = cert.get("expected_repo_sha") or _git_sha()
    deployed = cert.get("deployed_sha_verification") or {}
    sha_match = bool(deployed.get("verified"))
    remote_probed = bool(deployed.get("remote_probed"))

    stamp = _utc_now()[:10]
    out_path = EVIDENCE / "render" / f"sha_parity_{stamp}.json"
    if sha_match:
        status = "verified_live"
        parity = "hosted_matches_repo_head"
    elif remote_probed:
        status = "repo_complete"
        parity = "drift"
    else:
        status = "repo_complete"
        parity = "repo_local_certified"

    payload = {
        "schema_version": 2,
        "batch": "1199",
        "recorded_at": _utc_now(),
        "local_head_sha": sha,
        "evidence_status": status,
        "local_vs_deployed_parity": parity,
        "hosted_commit_sha": (deployed.get("deployed_shas") or [None])[0],
        "hosted_verified_live": sha_match,
        "classification": cert.get("classification"),
        "verdict": cert.get("verdict"),
        "notes": cert.get("remaining_gaps") or [],
    }
    _write_json(out_path, payload)
    return {
        "path": str(out_path.relative_to(ROOT)),
        "sha_match": sha_match,
        "exit_code": proc.returncode,
    }


def capture_batch_1175(school: str) -> dict:
    stamp = _utc_now()[:10]
    out_dir = EVIDENCE / "pilot" / school
    backlog_path = out_dir / "defect_backlog.json"
    if not backlog_path.is_file():
        _write_json(
            backlog_path,
            {
                "schema_version": 1,
                "school_slug": school,
                "recorded_at": _utc_now(),
                "evidence_status": "repo_complete",
                "defects": [],
                "notes": "Append pilot-reported defects after real school feedback; use PilotDefect model in prod.",
            },
        )

    intake_path = out_dir / f"intake_ready_{stamp}.json"
    payload = {
        "schema_version": 1,
        "batch": "1175",
        "school_slug": school,
        "recorded_at": _utc_now(),
        "evidence_status": "repo_complete",
        "defect_backlog_path": str(backlog_path.relative_to(ROOT)),
        "dashboard_route": "platform_runtime:pilot_defect_dashboard",
        "scorecard_slot": 2,
        "notes": "Repo intake scaffold; flip to verified_live after slot-2 pilot feedback is filed.",
    }
    _write_json(intake_path, payload)
    return {"path": str(intake_path.relative_to(ROOT)), "backlog": str(backlog_path.relative_to(ROOT))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--school", default="gilead-school")
    parser.add_argument("--production-ping", action="store_true")
    parser.add_argument("--skip-1170", action="store_true")
    parser.add_argument("--skip-1199", action="store_true")
    parser.add_argument("--skip-1175", action="store_true")
    args = parser.parse_args()

    results: dict = {"generated_at": _utc_now(), "captures": {}}
    failures = 0

    if not args.skip_1170:
        block = capture_batch_1170(args.school, production_ping=args.production_ping)
        results["captures"]["1170"] = block
        if block.get("exit_code") not in (0, 2):
            failures += 1

    if not args.skip_1199:
        block = capture_batch_1199()
        results["captures"]["1199"] = block
        if block.get("exit_code") not in (0, 1):
            failures += 1

    if not args.skip_1175:
        results["captures"]["1175"] = capture_batch_1175(args.school)

    out = ROOT / "docs" / "generated" / "geos_lane2_residual_evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}")

    if failures:
        print("write_geos_lane2_residual_evidence: FAIL (subcommand)", file=sys.stderr)
        return 1
    print("write_geos_lane2_residual_evidence: GEOS_LANE2_RESIDUAL_EVIDENCE_WRITTEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
