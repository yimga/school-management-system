#!/usr/bin/env python3
"""
Master Implementation Pack — Phases 0–26 orchestrator.

Combines full backend A++ audit + tenant 50X audit into canonical
``docs/generated/master_*`` artifacts, runs verifiers, and writes
completion audit with honest repo vs external status.

Run: python scripts/generate_master_implementation_pack.py --write [--run-verifiers]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated"

VERIFIERS = [
    ("audit_route_surface", ["python", "scripts/audit_route_surface.py"]),
    ("audit_security_surface", ["python", "scripts/audit_security_surface.py"]),
    ("audit_tenant_isolation", ["python", "scripts/audit_tenant_isolation.py"]),
    ("verify_test_module_contract", ["python", "scripts/verify_test_module_contract.py"]),
    ("verify_tenant_lifecycle_unified", ["python", "scripts/verify_tenant_lifecycle_unified.py"]),
    ("verify_tenant_provision_progress_surface", ["python", "scripts/verify_tenant_provision_progress_surface.py"]),
    ("verify_tenant_offboarding_surface", ["python", "scripts/verify_tenant_offboarding_surface.py"]),
    ("scan_operator_shell_dead_hrefs", ["python", "scripts/scan_operator_shell_dead_hrefs.py", "--strict"]),
    ("verify_service_worker_version", ["python", "scripts/verify_service_worker_version.py", "--check-monotonic"]),
    ("audit_tenant_lifecycle_aggressive", ["python", "scripts/audit_tenant_lifecycle_aggressive.py"]),
]

TENANT_VERIFIERS = [
    "verify_tenant_lifecycle_10x.py",
    "verify_tenant_lifecycle_completion.py",
    "audit_tenant_lifecycle_full.py",
    "audit_tenant_lifecycle_workflows.py",
]

UPSTREAM_GENERATORS = [
    "generate_full_backend_audit_pack.py",
    "generate_tenant_50x_audit_pack.py",
    "generate_tenant_lifecycle_code_truth_inventory.py",
    "generate_tenant_lifecycle_completion_audits.py",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], *, timeout: int = 600) -> dict:
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-1000:],
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": " ".join(cmd),
            "exit_code": -1,
            "ok": False,
            "error": "timeout",
        }
    except OSError as exc:
        return {"command": " ".join(cmd), "exit_code": -1, "ok": False, "error": str(exc)}


def _git_snapshot() -> dict:
    snap = {"generated_at": _now()}
    for label, args in (
        ("branch", ["git", "branch", "--show-current"]),
        ("status_short", ["git", "status", "--short"]),
        ("diff_stat", ["git", "diff", "--stat"]),
    ):
        r = _run(args, timeout=120)
        snap[label] = r.get("stdout_tail", r.get("stderr_tail", ""))
    return snap


def _load_json(name: str) -> dict | None:
    p = OUT / name
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def _write_pair(stem: str, data: dict, lines: list[str] | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{stem}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    body = lines or [f"- artifact keys: {', '.join(list(data.keys())[:16])}"]
    (OUT / f"{stem}.md").write_text(
        f"# {stem.replace('_', ' ').title()}\n\nGenerated: {_now()}\n\n" + "\n".join(body) + "\n",
        encoding="utf-8",
    )


def _run_upstream_generators() -> list[dict]:
    results = []
    for script in UPSTREAM_GENERATORS:
        path = REPO / "scripts" / script
        if path.is_file():
            results.append(_run([sys.executable, str(path), "--write"]))
        else:
            results.append({"command": script, "ok": False, "error": "missing"})
    return results


def _run_verifiers() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, cmd in VERIFIERS:
        out[name] = _run(cmd)
    for script in TENANT_VERIFIERS:
        path = REPO / "scripts" / script
        if path.is_file():
            out[script.replace(".py", "")] = _run([sys.executable, str(path)])
    return out


def _file_exists(rel: str) -> bool:
    return (REPO / rel).is_file()


def build_code_truth(git: dict) -> dict:
    upstream = _load_json("full_backend_audit_code_truth_inventory.json") or {}
    tenant = _load_json("tenant_50x_code_truth_inventory.json") or {}
    return {
        "generated_at": _now(),
        "git": git,
        "module_count": upstream.get("module_count"),
        "product_apps": upstream.get("product_apps", []),
        "tenant_lifecycle_engines": tenant.get("lifecycle_engines", []),
        "boundary_guard": [
            "apps/tenancy/boundary_core_guard.py",
            "apps/tenancy/middleware_boundary_guard.py",
            "apps/tenancy/queryset_boundary.py",
        ],
        "remediation_engine": "apps/platform_runtime/remediation.py",
        "remediation_present": _file_exists("apps/platform_runtime/remediation.py"),
    }


def compute_open_repo_gaps(
    *,
    verifier_results: dict[str, dict] | None = None,
    test_matrix: dict | None = None,
    kill_test: dict | None = None,
    playwright: dict | None = None,
) -> list[dict[str, str]]:
    """Honest repo-side gaps — must align with final report section O."""
    gaps: list[dict[str, str]] = []
    phase_audits = [
        (
            "setup_studio_50x",
            "setup_studio_50x_completion_audit.json",
            "Setup Studio 50X UX",
            "apps/setup_studio/tests/test_setup_studio_50x_zero_friction.py",
        ),
        (
            "academic_year_close",
            "academic_year_lifecycle_completion_audit.json",
            "Academic year close hardening",
            "apps/academics/tests/test_academic_year_setup_lifecycle.py",
        ),
        (
            "tenant_daily_ops_50x",
            "tenant_daily_operations_50x_completion_audit.json",
            "Tenant daily operations 50X click reduction",
            "apps/platform_runtime/tests/test_tenant_ai_help_and_daily_ops.py",
        ),
        (
            "tenant_ai_help",
            "tenant_online_offline_ai_help_completion_audit.json",
            "Online/offline tenant AI help",
            "apps/platform_runtime/tests/test_tenant_ai_help_and_daily_ops.py",
        ),
        (
            "tenant_health_cs",
            "tenant_health_customer_success_completion_audit.json",
            "Tenant health / customer success / nudges",
            "apps/customersuccess/tests/test_tenant_health_customer_success_completion.py",
        ),
    ]
    for gap_id, audit_name, label, test_path in phase_audits:
        audit = _load_json(audit_name) or {}
        if audit.get("status") != "complete":
            gaps.append(
                {
                    "id": gap_id,
                    "status": audit.get("status") or "open",
                    "kind": "repo",
                    "label": label,
                    "test": test_path,
                }
            )
    tm = test_matrix or _load_json("full_50_app_test_matrix_completion.json") or {}
    if not tm.get("all_shards_green"):
        gaps.append(
            {
                "id": "full_50_app_test_matrix",
                "status": "open" if not tm.get("all_shards_green") else "closed",
                "kind": "repo",
                "label": "Full 50-app manage.py test matrix",
                "test": "scripts/run_50_app_test_shards.py",
            }
        )
    kt = kill_test or _load_json("run_kill_test_completion_audit.json") or {}
    if kt.get("result") != "PASS":
        gaps.append(
            {
                "id": "run_kill_test",
                "status": "open",
                "kind": "repo" if kt.get("failure_kind") != "environment" else "external",
                "label": "run_kill_test.py structural smoke",
                "test": "scripts/run_kill_test.py",
            }
        )
    pw = playwright or _load_json("playwright_e2e_completion_audit.json") or {}
    if not pw.get("executed"):
        gaps.append(
            {
                "id": "playwright_e2e",
                "status": "open",
                "kind": "external" if pw.get("blocker") else "repo",
                "label": "Playwright phase1/phase2 E2E execution",
                "test": "npm run test:e2e:phase1-architecture",
            }
        )
    dedup = _load_json("generated_artifact_dedup_completion_audit.json") or {}
    if not dedup.get("registry_complete"):
        gaps.append(
            {
                "id": "artifact_dedup",
                "status": "open",
                "kind": "repo",
                "label": "Generated artifact canonical registry",
                "test": "scripts/generate_generated_artifact_registry.py",
            }
        )
    deep = _load_json("deep_module_reengineering_completion_audit.json") or {}
    if deep.get("open_module_count", 1) > 0:
        gaps.append(
            {
                "id": "deep_module_reengineering",
                "status": "partial",
                "kind": "repo",
                "label": "Per-module implementation beyond audit matrix",
                "test": "docs/generated/deep_module_reengineering_completion_audit.json",
            }
        )
    vr = verifier_results or {}
    failed = [k for k, v in vr.items() if not v.get("ok")]
    if failed:
        gaps.append(
            {
                "id": "verifier_failures",
                "status": "open",
                "kind": "repo",
                "label": f"Verifier failures: {', '.join(failed)}",
                "test": "scripts/generate_master_implementation_pack.py --run-verifiers",
            }
        )
    return gaps


def build_completion(verifier_results: dict[str, dict] | None) -> dict:
    vr = verifier_results or {}
    failed = [k for k, v in vr.items() if not v.get("ok")]
    hygiene = _load_json("code_hygiene_deep_audit.json") or {}
    href_count = len(hygiene.get("must_fix_sample", {}).get("href_hash", []))
    raw_console = hygiene.get("must_fix_sample", {}).get("console_log", [])
    console_count = len(
        [
            c
            for c in raw_console
            if not any(
                x in c.get("file", "")
                for x in ("vendor/", "htmx.min.js", "dist/", ".min.js")
            )
        ]
    )

    repo_gaps = compute_open_repo_gaps(verifier_results=vr)
    repo_only = [g for g in repo_gaps if g.get("kind") == "repo" and g.get("status") != "closed"]

    external_blockers = [
        {
            "id": "public_live_sla",
            "blocker": "Public live SLA / production deployment proof",
            "proof_required": "Live host smoke + operator signoff",
            "owner": "platform_ops",
        },
        {
            "id": "object_storage_purge",
            "blocker": "S3/object storage purge live proof",
            "proof_required": "Configured bucket + purge drill log",
            "owner": "platform_ops",
        },
        {
            "id": "postgres_rls_live",
            "blocker": "Postgres RLS enforcement on production DB",
            "proof_required": "Postgres deployment; local dev uses SQLite",
            "owner": "platform_ops",
        },
        {
            "id": "playwright_e2e_live",
            "blocker": "Browser E2E at all viewports",
            "proof_required": "Django server on VISUAL_QA_PORT + Playwright run",
            "owner": "ci_or_operator",
        },
        {
            "id": "full_50_app_test_matrix",
            "blocker": "Full 50-app manage.py test matrix in one CI run",
            "proof_required": "Extended CI window or sharded runners",
            "owner": "ci",
        },
        {
            "id": "counsel_maa_v2",
            "blocker": "Migration Cloud MAA v2.0 counsel signoff",
            "proof_required": "docs/legal/maa_v2_signoff.pdf",
            "owner": "legal",
        },
        {
            "id": "native_mobile",
            "blocker": "Native iOS/Android apps",
            "proof_required": "Deferred — PWA is launch strategy",
            "owner": "product",
        },
    ]

    implementation_ready = {
        "boundary_core_guard": _file_exists("apps/tenancy/boundary_core_guard.py"),
        "remediation_engine": _file_exists("apps/platform_runtime/remediation.py"),
        "provisioning_progress": _file_exists("apps/schools/provisioning_progress.py"),
        "tenant_offboarding": _file_exists("apps/schools/tenant_offboarding.py"),
        "lifecycle_notifications": _file_exists("apps/platform_runtime/tenant_lifecycle_notifications.py"),
        "pre_deploy_summary_not_sludge": _file_exists("docs/generated/pre_deploy_gate_run_summary.json"),
    }

    all_verifiers_green = not failed
    sot_safe = all_verifiers_green and not href_count and not repo_only

    true_audit = _load_json("master_implementation_true_completion_audit.json") or {}
    if true_audit.get("recommended_verdict"):
        verdict = true_audit["recommended_verdict"]
    elif repo_only:
        verdict = "MASTER IMPLEMENTATION PARTIAL — REPO GAPS REMAIN"
    elif not failed:
        verdict = "MASTER IMPLEMENTATION PARTIAL — EXTERNAL BLOCKERS DOCUMENTED"
    else:
        verdict = "MASTER IMPLEMENTATION PARTIAL — REPO GAPS REMAIN"
    if not repo_only and sot_safe and all(implementation_ready.values()) and not true_audit:
        verdict = "MASTER BACKEND A++ HARDENING READY — REPO SCOPE"

    return {
        "generated_at": _now(),
        "implementation_ready": implementation_ready,
        "verifiers_run": bool(vr),
        "verifier_failures": failed,
        "verifier_results_summary": {k: v.get("ok") for k, v in vr.items()},
        "remaining_repo_gaps": repo_gaps,
        "remaining_repo_gaps_count": len(repo_only),
        "external_blockers": external_blockers,
        "sot_safe_to_update": sot_safe,
        "recommended_verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write artifacts")
    parser.add_argument("--run-verifiers", action="store_true", help="Run verifier bundle")
    parser.add_argument("--skip-upstream", action="store_true", help="Skip upstream generators")
    args = parser.parse_args()

    git = _git_snapshot()
    upstream_results: list[dict] = []
    if not args.skip_upstream:
        upstream_results = _run_upstream_generators()

    verifier_results: dict[str, dict] | None = None
    if args.run_verifiers:
        verifier_results = _run_verifiers()

    # Map upstream artifacts to master_* names
    mappings = [
        ("master_implementation_code_truth_inventory", build_code_truth(git)),
        ("master_release_source_hygiene_audit", _load_json("release_source_hygiene_audit.json") or {"generated_at": _now()}),
        ("master_proof_sludge_cleanup_plan", _load_json("proof_sludge_cleanup_plan.json") or {"generated_at": _now()}),
        ("master_generated_artifact_consolidation_audit", _load_json("generated_artifact_consolidation_audit.json") or {}),
        ("master_script_sprawl_consolidation_audit", _load_json("script_sprawl_consolidation_audit.json") or {}),
        ("master_code_hygiene_deep_audit", _load_json("code_hygiene_deep_audit.json") or {}),
        ("master_backend_security_deep_audit", _load_json("backend_security_deep_audit.json") or {}),
        ("master_tenant_isolation_deep_audit", _load_json("platform_tenant_isolation_deep_audit.json") or {}),
        ("master_module_audit_matrix", _load_json("module_audit_matrix.json") or {}),
        ("master_tenant_50x_journey_map", _load_json("tenant_50x_journey_map.json") or {}),
        ("master_tenant_state_machine_hardening", _load_json("tenant_50x_state_machine_hardening.json") or {}),
        ("master_tenant_provisioning_hardening", _load_json("tenant_50x_provisioning_hardening.json") or {}),
        ("master_tenant_progress_notification_engine", _load_json("tenant_50x_progress_notification_engine.json") or {}),
        ("master_setup_studio_50x_zero_friction", _load_json("setup_studio_50x_zero_friction_audit.json") or {}),
        ("master_tenant_local_first_defaults", _load_json("tenant_50x_local_first_defaults.json") or {}),
        ("master_tenant_click_reduction_remediation", {
            "generated_at": _now(),
            "engine": "apps/platform_runtime/remediation.py",
            "wired_signup": _file_exists("apps/schools/signup_views.py"),
            "wired_provisioning": _file_exists("apps/schools/provisioning_progress.py"),
            "status": "implemented_repo_scope" if _file_exists("apps/platform_runtime/remediation.py") else "gap",
        }),
        ("master_tenant_offboarding_export_purge", _load_json("tenant_50x_offboarding_export_purge.json") or {}),
        ("master_runtime_proof_depth_audit", _load_json("runtime_proof_depth_audit.json") or {}),
        ("master_pwa_offline_backend_validation", _load_json("pwa_offline_backend_validation.json") or {}),
        ("master_production_claim_honesty_audit", _load_json("production_claim_honesty_audit.json") or {}),
    ]

    for stem, data in mappings:
        if not data:
            data = {"generated_at": _now(), "status": "pending_upstream"}
        data.setdefault("generated_at", _now())
        _write_pair(stem, data)

    # Security registers — alias existing
    for stem in (
        "security_exception_register",
        "csrf_exempt_targeted_review",
        "allowany_targeted_review",
        "graphql_security_review",
    ):
        src = _load_json(f"{stem}.json")
        if src:
            _write_pair(f"master_{stem}", src)

    completion = build_completion(verifier_results)
    completion["upstream_generators"] = [{"ok": r.get("ok"), "cmd": r.get("command")} for r in upstream_results]
    _write_pair("master_implementation_completion_audit", completion)

    print(f"OK: master implementation pack — {len(mappings) + 1} artifacts")
    if verifier_results:
        failed = [k for k, v in verifier_results.items() if not v.get("ok")]
        print(f"Verifiers: {len(verifier_results) - len(failed)}/{len(verifier_results)} green")
        if failed:
            print(f"FAILED: {', '.join(failed)}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
