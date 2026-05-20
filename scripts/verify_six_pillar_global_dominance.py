#!/usr/bin/env python3
"""
Six-pillar global dominance orchestrator (Tenant Sovereignty + AWS + Shopify +
Salesforce + Linux + Google + AI engine room).

Runs mechanical child verifiers; writes docs/generated/six_pillar_global_dominance_audit.json.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "six_pillar_global_dominance_audit.json"


def _contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8")


def _wiring_checks() -> list[tuple[str, str, bool, str]]:
    """CI / release / SOT hooks — regression guard for batch 1296."""
    return [
        (
            "WIRING",
            "ci_platform_pillar_gates",
            _contains(".github/workflows/architectural-boundaries.yml", "verify_six_pillar_global_dominance.py")
            and _contains(".github/workflows/architectural-boundaries.yml", "verify_tenant_sovereignty_pillar.py"),
            "architectural-boundaries.yml platform-pillar-gates",
        ),
        (
            "WIRING",
            "phases_gate_bundle",
            _contains("scripts/verify_phases_3_11_gates.py", "verify_six_pillar_global_dominance.py"),
            "verify_phases_3_11_gates.py",
        ),
        (
            "WIRING",
            "release_readiness",
            _contains("scripts/release_readiness_check.sh", "verify_six_pillar_global_dominance.py"),
            "release_readiness_check.sh §4c",
        ),
        (
            "WIRING",
            "npm_script",
            _contains("package.json", '"verify:six-pillar"'),
            "package.json verify:six-pillar",
        ),
        (
            "WIRING",
            "sot_batch_1296",
            _contains("docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md", "batch 1296"),
            "SOT §11.4 batch 1296",
        ),
        (
            "WIRING",
            "sot_vectors_json",
            (ROOT / "docs/generated/tenant_sovereignty_platform_vectors.json").is_file(),
            "tenant_sovereignty_platform_vectors.json",
        ),
    ]


@dataclass
class Row:
    pillar: str
    gate: str
    status: str
    proof: str


def _run(cmd: list[str], *, timeout: int = 1200) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode, out[-400:] if out else ""
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except OSError as exc:
        return 1, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write JSON audit artifact.")
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Include five-pillar Django proof subset (slower).",
    )
    args = parser.parse_args()
    py = sys.executable
    rows: list[Row] = []

    for pillar, gate, ok, proof in _wiring_checks():
        rows.append(Row(pillar=pillar, gate=gate, status="PASS" if ok else "FAIL", proof=proof))

    def add(pillar: str, gate: str, code: int, tail: str) -> None:
        rows.append(
            Row(
                pillar=pillar,
                gate=gate,
                status="PASS" if code == 0 else "FAIL",
                proof=tail or gate,
            )
        )

    code, tail = _run([py, "scripts/verify_tenant_sovereignty_pillar.py", "--write"])
    add("TENANT_SOVEREIGNTY", "verify_tenant_sovereignty_pillar", code, tail)

    five_cmd = [py, "scripts/verify_five_pillar_platform_completion.py", "--write"]
    if args.run_tests:
        five_cmd.append("--run-tests")
    code, tail = _run(five_cmd, timeout=1200)
    add("AWS_SHOPIFY_SALESFORCE_LINUX_GOOGLE", "verify_five_pillar_platform_completion", code, tail)

    code, tail = _run([py, "scripts/verify_ai_engine_room.py"])
    add("GOOGLE_AI_ENGINE", "verify_ai_engine_room", code, tail)

    code, tail = _run([py, "scripts/verify_forensic_master_prompt_completion.py"], timeout=1200)
    add("FORENSIC_ZERO_EXCEPTION", "verify_forensic_master_prompt_completion", code, tail)

    failed = [r for r in rows if r.status == "FAIL"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "SIX_PILLAR_GLOBAL_DOMINANCE_PASS"
        if not failed
        else "SIX_PILLAR_GLOBAL_DOMINANCE_FAIL",
        "passed": sum(1 for r in rows if r.status == "PASS"),
        "failed": len(failed),
        "foundational_layer_first": "TENANT_SOVEREIGNTY",
        "rows": [asdict(r) for r in rows],
        "sot_artifacts": [
            "docs/generated/tenant_sovereignty_platform_vectors.json",
            "docs/generated/tenant_sovereignty_pillar_audit.json",
            "docs/generated/five_pillar_platform_audit.json",
            "docs/generated/forensic_master_prompt_audit.json",
        ],
    }

    if args.write:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for row in failed:
        print(
            f"FAIL [{row.pillar}] {row.gate}: {row.proof}",
            file=sys.stderr,
        )

    if failed:
        print(f"verify_six_pillar_global_dominance: {len(failed)} FAIL", file=sys.stderr)
        return 1

    print(
        f"verify_six_pillar_global_dominance: {payload['verdict']} "
        f"({payload['passed']}/{len(rows)} checks; first layer={payload['foundational_layer_first']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
