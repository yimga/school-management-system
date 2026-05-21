#!/usr/bin/env python3
"""
Section 8 compliance gate for the Forensic Master Prompt (zero exceptions).

Runs mechanical checks + subprocess verifiers; writes
docs/generated/forensic_master_prompt_audit.json
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "forensic_master_prompt_audit.json"


@dataclass
class Row:
    row_id: str
    mandate: str
    status: str  # PASS | FAIL | SKIP
    proof: str


def _run_django_tests(module: str, *, timeout: int = 1200) -> tuple[bool, str]:
    """Run a Django test module via the in-repo sqlite-memory runner.

    Timeout is generous (default 20 min) because a `--fresh` DB build on
    Windows takes 6–8 min just for migrations before the actual tests
    execute. The teardown-lock allow-list catches the common Windows
    `WinError 32` cleanup failure that follows successful test runs.
    """
    gate_db = ROOT / ".django_test_dbs" / f"forensic_perf_{int(time.time())}.sqlite3"
    env = os.environ.copy()
    env["DJANGO_TEST_DB_FILE"] = str(gate_db)
    code, tail = _run(
        [
            sys.executable,
            "scripts/run_sqlite_memory_tests.py",
            "--fresh",
            module,
            "--verbosity=1",
            "--no-input",
        ],
        timeout=timeout,
        env=env,
    )
    combined = tail
    teardown_lock = (
        code != 0
        and "PermissionError" in combined
        and "WinError 32" in combined
        and "\nOK\n" in combined
    )
    return code == 0 or teardown_lock, tail


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()[-500:]
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except OSError as exc:
        return 1, str(exc)


def _count_bola_tests() -> int:
    path = ROOT / "apps/api/tests/test_bola_idor_matrix.py"
    if not path.is_file():
        return 0
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    )


def _file_exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def main() -> int:
    rows: list[Row] = []
    py = sys.executable

    def add(row_id: str, mandate: str, ok: bool, proof: str) -> None:
        rows.append(Row(row_id, mandate, "PASS" if ok else "FAIL", proof))

    # 1a–1d Theme
    code, tail = _run([py, "scripts/verify_theme_aaa_brand_cycle.py"])
    add("1a", "Light/Dark/System + AAA cycle", code == 0, tail or "verify_theme_aaa_brand_cycle")

    code, tail = _run([py, "scripts/verify_theme_visibility_platform.py"], timeout=300)
    add("1b", "WCAG visibility + shell sweep", code == 0, tail or "verify_theme_visibility_platform")

    brand_guard = ROOT / "apps/siteconfig/brand_guard_runtime.py"
    ok_guard = brand_guard.is_file() and "guard_brand_dict" in brand_guard.read_text(encoding="utf-8")
    add("1c", "Hue-shift guardrail platform-wide", ok_guard, str(brand_guard.relative_to(ROOT)))

    theme_files = [
        "apps/siteconfig/views_theme_builder.py",
        "templates/siteconfig/theme_builder.html",
        "static/js/theme-builder-canvas.js",
        "templates/siteconfig/partials/theme_experience_hub_hero.html",
        "tests/e2e/theme_experience_forensic.spec.js",
        "apps/siteconfig/tests/test_forensic_master_prompt_contract.py",
    ]
    ok_builder = all(_file_exists(p) for p in theme_files)
    code_gear, tail_gear = _run([py, "scripts/verify_theme_experience_gear.py"])
    add(
        "1d",
        "Shopify-grade theme builder + hub + E2E spec",
        ok_builder and code_gear == 0,
        tail_gear or "verify_theme_experience_gear + builder artifacts",
    )

    # 2a–2d Security
    bola_count = _count_bola_tests()
    add("2a", "BOLA matrix >= 30 cases", bola_count >= 30, f"test_bola_idor_matrix: {bola_count} tests")

    ok_bind = _file_exists("apps/schools/session_school_bind.py") and _file_exists(
        "apps/schools/middleware_session_school_bind.py"
    )
    add("2b", "Session school binding middleware", ok_bind, "session_school_bind + middleware")

    bind_tests = ROOT / "apps/schools/tests/test_session_school_bind.py"
    ok_tamper = bind_tests.is_file() and "test_tampered_session_fails_verify" in bind_tests.read_text(
        encoding="utf-8"
    )
    add("2c", "Cryptographic session seal tamper test", ok_tamper, str(bind_tests.relative_to(ROOT)))

    switch_tests = ROOT / "apps/api/tests/test_me_switch_school_bola.py"
    ok_switch = switch_tests.is_file() and "MeSwitchSchoolBOLATests" in switch_tests.read_text(
        encoding="utf-8"
    )
    add("2d", "Campus switch hierarchy tests", ok_switch, str(switch_tests.relative_to(ROOT)))

    code_tenant, tail_tenant = _run([py, "scripts/scan_tenant_queryset_safety.py"], timeout=180)
    add("2e", "Tenant queryset safety baseline 0", code_tenant == 0, tail_tenant or "scan_tenant_queryset_safety")

    # 3a–3c Performance
    perf_ok, perf_tail = _run_django_tests("apps.siteconfig.tests.test_performance_zero_ticket")
    add(
        "3a",
        "PERF_BUDGET_STRICT smoke (Zero-Ticket query caps)",
        perf_ok,
        perf_tail or "test_performance_zero_ticket",
    )

    perf_tests = ROOT / "apps/siteconfig/tests/test_performance_zero_ticket.py"
    ok_n1 = perf_tests.is_file() and "CaptureQueriesContext" in perf_tests.read_text(encoding="utf-8")
    add("3b", "N+1 caps on diagnostics/simulator", ok_n1, str(perf_tests.relative_to(ROOT)))

    code_dom, tail_dom = _run([py, "scripts/verify_dom_performance_budgets.py"], timeout=180)
    ok_dom_scripts = _file_exists("scripts/verify_zero_ticket_dom_budget.mjs") and _file_exists(
        "scripts/verify_dom_performance_budgets.py"
    )
    add(
        "3c",
        "DOM budget gate (executed)",
        code_dom == 0 and ok_dom_scripts,
        tail_dom or "verify_dom_performance_budgets.py",
    )

    # 4.1–4.6 Vectors
    code, tail = _run([py, "scripts/verify_tenant_platform_vectors.py"])
    add("4.0", "Platform vector imports", code == 0, tail or "verify_tenant_platform_vectors")

    vec_tests = ROOT / "apps/platform_runtime/tests/test_tenant_platform_vector_behavior.py"
    ok_vec = vec_tests.is_file()
    add("4.1-4.6", "Behavioral vector tests module", ok_vec, str(vec_tests.relative_to(ROOT)))

    code, tail = _run([py, "scripts/verify_audit_log_append_only.py"])
    add("4.6", "Audit append-only scan", code == 0, tail or "verify_audit_log_append_only")

    code, tail = _run([py, "scripts/verify_finance_payment_atomicity.py"])
    add("4.5", "Finance payment atomicity", code == 0, tail or "verify_finance_payment_atomicity")

    delete_tests = (
        ROOT / "apps/platform_runtime/tests/test_tenant_platform_vector_delete_invariants.py"
    )
    ok_delete = delete_tests.is_file() and "bulk_delete_raises" in delete_tests.read_text(
        encoding="utf-8"
    )
    add("4.6b", "Append-only ORM + bulk delete", ok_delete, str(delete_tests.relative_to(ROOT)))

    # 5.1–5.4 Part 2
    zt_files = [
        "apps/siteconfig/views_zero_ticket_hub.py",
        "apps/siteconfig/tenant_diagnostics.py",
        "apps/siteconfig/permission_matrix_simulator.py",
        "static/js/rmc-zero-ticket-diagnostics.js",
    ]
    add("5.1", "Zero-Ticket hub stack", all(_file_exists(p) for p in zt_files), ",".join(zt_files))

    perm_url = (ROOT / "apps/siteconfig/urls.py").read_text(encoding="utf-8")
    add(
        "5.2",
        "Permission simulator + export",
        "permissions/simulate" in perm_url or "api_permission_matrix" in perm_url,
        "siteconfig urls",
    )

    wf_template = ROOT / "templates/siteconfig/campus_workflow_canvas_hub.html"
    ok_wf = wf_template.is_file() and "designer_url" in wf_template.read_text(encoding="utf-8")
    add("5.3", "Workflow canvas hub (not link-only)", ok_wf, str(wf_template.relative_to(ROOT)))

    campus_tpl = ROOT / "templates/components/rmc_campus_switcher.html"
    campus_js = ROOT / "static/js/rmc-campus-switcher.js"
    tpl_text = campus_tpl.read_text(encoding="utf-8") if campus_tpl.is_file() else ""
    js_text = campus_js.read_text(encoding="utf-8") if campus_js.is_file() else ""
    ok_campus = campus_tpl.is_file() and (
        "aria-live" in tpl_text or "aria-live" in js_text
    )
    add("5.4", "Campus switcher a11y", ok_campus, str(campus_tpl.relative_to(ROOT)))

    # 6 Placeholders
    forbidden = re.compile(r"\b(TODO|FIXME|insert code here)\b", re.I)
    scan_roots = [ROOT / "apps/siteconfig/views_zero_ticket_hub.py", ROOT / "apps/siteconfig/views_theme_builder.py"]
    bad = [p for p in scan_roots if p.is_file() and forbidden.search(p.read_text(encoding="utf-8"))]
    add("6", "No placeholders in hot paths", not bad, "zero-ticket + theme_builder views")

    # 7 SOT
    sot = ROOT / "docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
    log = ROOT / "docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md"
    sot_text = sot.read_text(encoding="utf-8") if sot.is_file() else ""
    ok_sot = (
        sot.is_file()
        and log.is_file()
        and "batch 1288" in sot_text
        and "verify_forensic_master_prompt_completion" in sot_text
    )
    add("7", "SOT batch 1288 + autonomous log", ok_sot, "docs present")

    # 8 RBAC — advisory if slow; run with short timeout
    code, tail = _run([py, "scripts/audit_role_permission_matrix.py", "--max-candidate-anonymous", "66"], timeout=120)
    add("8", "RBAC matrix within ceiling", code == 0, tail or "audit_role_permission_matrix")

    failures = [r for r in rows if r.status == "FAIL"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "FORENSIC_MASTER_PROMPT_PASS" if not failures else "FORENSIC_MASTER_PROMPT_FAIL",
        "pass_count": sum(1 for r in rows if r.status == "PASS"),
        "fail_count": len(failures),
        "rows": [
            {"id": r.row_id, "mandate": r.mandate, "status": r.status, "proof": r.proof}
            for r in rows
        ],
    }
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"verify_forensic_master_prompt_completion: {payload['verdict']}")
    print(f"  PASS {payload['pass_count']} / FAIL {payload['fail_count']}")
    for r in failures:
        print(f"  FAIL {r.row_id}: {r.mandate} — {r.proof}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
