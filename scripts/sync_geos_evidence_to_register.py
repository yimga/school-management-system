#!/usr/bin/env python3
"""Sync external_dependencies_register.json from var/evidence/geos-99/ artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apps.platform_runtime.geos_lane2_evidence import (  # noqa: E402
    EVIDENCE_ROOT,
    evidence_json_complete,
    flip_register_entry,
    utc_now_iso,
)


def _write_ai_posture_evidence() -> Path:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_render_online_ai_posture.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    path = EVIDENCE_ROOT / "ai" / "option_a_posture_evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "evidence_status": "verified_live" if proc.returncode == 0 else "pending_operator",
        "verifier": "scripts/verify_render_online_ai_posture.py",
        "verifier_exit_code": proc.returncode,
        "proof": (proc.stdout or proc.stderr or "").strip()[-200:],
        "notes": "Repo Option A posture; production live_cloud probe is additive Lane 2.",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_data_residency_evidence() -> Path:
    path = EVIDENCE_ROOT / "compliance" / "data_residency_repo_evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "evidence_status": "repo_complete",
        "proof": "apps/schools/data_residency_settings.py + docs/compliance/DATA_RESIDENCY_LEGAL_GUIDE.md",
        "notes": "Repo cascade complete; corridor legal opinion remains operator/counsel.",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply register flips when evidence JSON is complete.",
    )
    args = parser.parse_args()
    changes: list[str] = []

    manual = EVIDENCE_ROOT / "psp" / "manual_fallback_internal_pilot.json"
    if evidence_json_complete(manual):
        if args.write:
            flip_register_entry(
                "manual_fallback_operations",
                status="verified_live",
                evidence_notes=manual.relative_to(ROOT).as_posix(),
            )
        changes.append("manual_fallback_operations->verified_live")
        if args.write:
            flip_register_entry(
                "sfdp_lane2_pilot_corridors",
                status="verified_live",
                evidence_notes=manual.relative_to(ROOT).as_posix(),
            )
        changes.append("sfdp_lane2_pilot_corridors->verified_live")

    ai_path = _write_ai_posture_evidence()
    if evidence_json_complete(ai_path):
        if args.write:
            flip_register_entry(
                "openai_litellm_option_a",
                status="verified_live",
                evidence_notes=ai_path.relative_to(ROOT).as_posix(),
            )
        changes.append("openai_litellm_option_a->verified_live")

    residency_path = _write_data_residency_evidence()
    if args.write:
        flip_register_entry(
            "data_localization_placeholder",
            status="repo_complete",
            evidence_notes=residency_path.relative_to(ROOT).as_posix(),
        )
    changes.append("data_localization_placeholder->repo_complete")

    sovereign = EVIDENCE_ROOT / "offline" / "sovereign_delivery_e2e_2026-05-23.json"
    if sovereign.is_file() and args.write:
        flip_register_entry(
            "sovereign_offline_delivery_platform",
            status="repo_complete",
            evidence_notes=sovereign.relative_to(ROOT).as_posix(),
        )
        changes.append("sovereign_offline_delivery_platform->repo_complete")

    sha = EVIDENCE_ROOT / "render" / "sha_parity_2026-05-23.json"
    if evidence_json_complete(sha) and args.write:
        flip_register_entry(
            "hosting_render_sha_parity",
            status="verified_live",
            evidence_notes=sha.relative_to(ROOT).as_posix(),
        )
        changes.append("hosting_render_sha_parity->verified_live")

    if args.write and changes:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "generate_external_dependencies_register.py"),
                "--write",
            ],
            cwd=str(ROOT),
            check=False,
        )

    print("sync_geos_evidence_to_register:", ", ".join(changes) or "no-op")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
