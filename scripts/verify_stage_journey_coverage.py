#!/usr/bin/env python3
"""Verify orchestrator journey manifest coverage (27 journeys).

Usage:
  python scripts/verify_stage_journey_coverage.py
  python scripts/verify_stage_journey_coverage.py --run
  python scripts/verify_stage_journey_coverage.py --json --write
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "generated" / "orchestrator_journey_manifest.json"
OUT = ROOT / "docs" / "generated" / "orchestrator_journey_coverage.json"

VERIFIER_SCRIPTS: dict[str, list[str]] = {
    "manage.py check": [sys.executable, "manage.py", "check", "--no-input"],
    "verify_migration_files_tracked": [
        sys.executable,
        "scripts/verify_migration_files_tracked.py",
    ],
    "audit_tenant_isolation": [sys.executable, "scripts/audit_tenant_isolation.py"],
    "scan_tenant_queryset_safety": [
        sys.executable,
        "scripts/scan_tenant_queryset_safety.py",
    ],
    "audit_route_surface": [sys.executable, "scripts/audit_route_surface.py"],
    "verify_platform_chromatic_compliance": [
        sys.executable,
        "scripts/verify_platform_chromatic_compliance.py",
    ],
    "verify_nav_resolves_to_named_route": [
        sys.executable,
        "scripts/verify_nav_resolves_to_named_route.py",
    ],
    "audit_security_surface": [sys.executable, "scripts/audit_security_surface.py"],
    "verify_five_pillar_platform_completion": [
        sys.executable,
        "scripts/verify_five_pillar_platform_completion.py",
    ],
    "scan_money_float": [sys.executable, "scripts/scan_money_float.py"],
    "verify_page_fold_standards": [
        sys.executable,
        "scripts/verify_page_fold_standards.py",
    ],
    "verify_phases_3_11_gates": [
        sys.executable,
        "scripts/verify_phases_3_11_gates.py",
    ],
    "verify_migration_cloud_connectors": [
        sys.executable,
        "scripts/verify_migration_cloud_connectors.py",
    ],
    "verify_migration_cloud_intake_experience": [
        sys.executable,
        "scripts/verify_migration_cloud_intake_experience.py",
    ],
    "verify_interaction_integrity_completion": [
        sys.executable,
        "scripts/verify_interaction_integrity_completion.py",
    ],
    "audit_luxury_ui_surface": [sys.executable, "scripts/audit_luxury_ui_surface.py"],
    "verify_ai_engine_room": [sys.executable, "scripts/verify_ai_engine_room.py"],
    "verify_ollama_live": [sys.executable, "scripts/verify_ollama_live.py"],
}


def _django_test_module(dotted: str) -> bool:
    parts = dotted.split(".")
    if len(parts) < 3 or parts[0] != "apps":
        return False
    mod_path = ROOT / "/".join(parts[:-1]) / f"{parts[-1]}.py"
    pkg_init = ROOT / "/".join(parts) / "__init__.py"
    return mod_path.is_file() or pkg_init.is_file()


def _run_cmd(cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        ok = proc.returncode == 0
        tail = (proc.stdout or proc.stderr or "")[-500:]
        return ok, tail.strip() or f"exit {proc.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except FileNotFoundError as e:
        return False, str(e)


def _check_journey(j: dict, *, do_run: bool) -> dict:
    proof = j.get("proof") or {}
    status = "PASS"
    detail = "ok"
    verifier = proof.get("verifier")
    spec = proof.get("spec")
    django_test = proof.get("django_test")

    if verifier:
        script = ROOT / "scripts" / f"{verifier}.py"
        if verifier == "manage.py check":
            script = ROOT / "manage.py"
        if verifier not in VERIFIER_SCRIPTS and not script.is_file():
            return {
                "journey_id": j["journey_id"],
                "status": "FAIL",
                "detail": f"unknown verifier {verifier}",
            }
        if do_run and verifier in VERIFIER_SCRIPTS:
            ok, detail = _run_cmd(VERIFIER_SCRIPTS[verifier])
            status = "PASS" if ok else "FAIL"
        elif not do_run:
            status = "PASS" if verifier == "manage.py check" or script.is_file() else "FAIL"
            if status == "FAIL":
                detail = f"missing script {verifier}"
    elif spec:
        path = ROOT / spec
        status = "PASS" if path.is_file() else "FAIL"
        detail = str(path) if path.is_file() else "missing spec"
    elif django_test:
        status = "PASS" if _django_test_module(django_test) else "FAIL"
        detail = django_test if status == "PASS" else f"missing {django_test}"
        if do_run and status == "PASS":
            ok, detail = _run_cmd(
                [sys.executable, "manage.py", "test", django_test, "--no-input", "-v0"],
                timeout=600,
            )
            status = "PASS" if ok else "FAIL"
    else:
        status = "FAIL"
        detail = "no proof"

    return {"journey_id": j["journey_id"], "stage": j["stage"], "status": status, "detail": detail}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Execute verifiers/tests (slow)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    if not MANIFEST.is_file():
        print(f"Missing {MANIFEST}; run generate_orchestrator_journey_manifest.py --write")
        return 1

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    journeys = data.get("journeys") or []
    results = [_check_journey(j, do_run=args.run) for j in journeys]
    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] != "PASS"]
    by_stage: dict[int, dict] = {}
    for r in results:
        st = int(r["stage"])
        by_stage.setdefault(st, {"pass": 0, "total": 0})
        by_stage[st]["total"] += 1
        if r["status"] == "PASS":
            by_stage[st]["pass"] += 1

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "journey_count": len(journeys),
        "pass_count": len(passed),
        "fail_count": len(failed),
        "journey_coverage_pct": round(100 * len(passed) / len(journeys), 1) if journeys else 0,
        "by_stage": by_stage,
        "results": results,
        "verdict": "JOURNEY_COVERAGE_PASS" if not failed else "JOURNEY_COVERAGE_FAIL",
    }
    if args.write or True:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    elif failed:
        print(f"JOURNEY_COVERAGE_FAIL ({len(failed)}/{len(journeys)})")
        for r in failed[:15]:
            print(f"  {r['journey_id']}: {r['detail']}")
    else:
        print(
            f"JOURNEY_COVERAGE_PASS ({len(passed)}/{len(journeys)}, "
            f"{payload['journey_coverage_pct']}%)"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
