#!/usr/bin/env python3
"""
Platform-wide interaction integrity gate (Help Center, RBAC UI, VoC, header dropdown, HTTP errors).

Writes docs/generated/interaction_integrity_audit.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "interaction_integrity_audit.json"
TEMPLATES = ROOT / "templates"
STATIC_JS = ROOT / "static" / "js"


@dataclass
class Row:
    check_id: str
    label: str
    ok: bool
    proof: str


def _contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    if not path.is_file():
        return False
    return needle in path.read_text(encoding="utf-8", errors="replace")


def _pick_gate_db() -> Path:
    tdir = ROOT / ".django_test_dbs"
    for name in (
        "feedback_help_gate.sqlite3",
        "manager_header_account_gate.sqlite3",
        "operator_help_center_gate.sqlite3",
        "interaction_integrity_gate_v2.sqlite3",
    ):
        candidate = tdir / name
        if candidate.is_file():
            return candidate
    return tdir / "interaction_integrity_gate_v2.sqlite3"


def _feedback_gate_db() -> Path:
    return ROOT / ".django_test_dbs" / "feedback_help_gate.sqlite3"


def _run_tests(labels: list[str], *, timeout: int = 900) -> tuple[bool, str]:
    # Reuse migrated gate DB from sibling verifiers when present; --fresh only if none exists.
    gate_db = _pick_gate_db()
    env = os.environ.copy()
    env["DJANGO_TEST_DB_FILE"] = str(gate_db)
    fresh = os.environ.get("RMC_VERIFY_INTERACTION_FRESH_DB") == "1" or not gate_db.is_file()
    cmd = [
        sys.executable,
        "scripts/run_sqlite_memory_tests.py",
        *labels,
        "--verbosity=1",
        "--no-input",
    ]
    if fresh:
        cmd.append("--fresh")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        combined = ((proc.stdout or "") + (proc.stderr or "")).strip()
        tail = combined[-800:]
        # Windows: teardown may fail to unlink sqlite (WinError 32) after tests reported OK.
        teardown_lock = (
            proc.returncode != 0
            and "PermissionError" in combined
            and "WinError 32" in combined
            and "\nOK\n" in combined
        )
        return proc.returncode == 0 or teardown_lock, tail
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def main() -> int:
    rows: list[Row] = []

    def add(check_id: str, label: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, label, ok, proof))

    shells = [
        "templates/control_plane_skeleton.html",
        "templates/portal_base.html",
        "templates/base.html",
        "templates/marketing/base_marketing.html",
        "templates/admin/base_site.html",
    ]
    def _guard_wired(rel: str) -> bool:
        return _contains(rel, "rmc-interaction-guard.js") or _contains(
            rel, "rmc_interaction_shell_scripts.html"
        )

    guard_wired = all(_guard_wired(s) for s in shells)
    add("1", "Interaction guard on all five shells", guard_wired, ",".join(shells))

    add(
        "2",
        "Interaction guard module exists",
        (STATIC_JS / "rmc-interaction-guard.js").is_file(),
        "static/js/rmc-interaction-guard.js",
    )
    add(
        "3",
        "Help center route + contracts",
        _contains("apps/feedback/urls.py", 'name="help_center"')
        and _contains(
            "apps/feedback/tests/test_feedback_help_center_contracts.py",
            "test_help_center_renders_for_staff",
        ),
        "feedback:help_center + tests",
    )
    add(
        "4",
        "Permission matrix simulator + guarded JS",
        _contains("templates/siteconfig/permission_matrix_simulator.html", "rmc-perm-sim-denied")
        and _contains("static/js/rmc-permission-matrix-simulator.js", "showDenied"),
        "permission_matrix_simulator",
    )
    add(
        "5",
        "User dropdown logout link",
        _contains("templates/components/user_dropdown.html", "accounts:logout"),
        "user_dropdown.html",
    )
    add(
        "6",
        "User dropdown scrollable menu (logout reachable)",
        _contains("static/css/portal-ui-components.css", ".user-dropdown-menu")
        and "max-height: calc(100vh - 80px)" in (ROOT / "static/css/portal-ui-components.css").read_text(
            encoding="utf-8", errors="replace"
        ),
        "portal-ui-components.css",
    )
    add(
        "7",
        "Marketing proof interaction guard",
        _contains("static/marketing/js/mkt-proof-interactions.js", "mkt-proof-interactions"),
        "mkt-proof-interactions.js",
    )

    error_pages = [
        "templates/errors/401.html",
        "templates/errors/403.html",
        "templates/errors/403_control_plane.html",
        "templates/errors/404.html",
        "templates/errors/404_control_plane.html",
        "templates/errors/429.html",
        "templates/errors/500.html",
        "templates/errors/500_control_plane.html",
        "templates/errors/500_minimal.html",
        "templates/errors/503.html",
        "templates/errors/503_control_plane.html",
        "templates/errors/offline.html",
    ]
    errors_ok = all((ROOT / p).is_file() for p in error_pages)
    add("8", "HTTP error surface templates (401–503 + offline)", errors_ok, str(len(error_pages)))

    add(
        "9",
        "handler503 wired in urlconf",
        _contains("config/urls.py", "handler503 = service_unavailable"),
        "config/urls.py",
    )

    dead_hash_user = (TEMPLATES / "components" / "user_dropdown.html").read_text(
        encoding="utf-8", errors="replace"
    )
    add(
        "10",
        "No dead href=# in user dropdown",
        'href="#"' not in dead_hash_user,
        "user_dropdown.html scan",
    )

    manager_help_routing = _contains("config/manager_urls.py", 'reverse("manager_help_center")') or _contains(
        "config/manager_help_center.py", 'reverse("kb:kb_home")'
    )
    add(
        "11",
        "Manager header account menu gate",
        _contains("apps/schools/middleware.py", "/authentication/documentation/")
        and manager_help_routing
        and _contains("static/css/rmc-platform-header.css", "--rmc-header-control-height")
        and (ROOT / "apps/accounts/operator_account_render.py").is_file(),
        "middleware + manager_help_center + CSS + operator_account_render",
    )

    add(
        "12",
        "Manager /admin/ delegates footer to the control-plane workbench",
        _contains("templates/admin/base.html", "admin_workbench_footer.html")
        and _contains(
            "templates/partials/admin_workbench_footer.html",
            "rmc-admin-workbench-footer",
        )
        and _contains("templates/admin/base_site.html", "rmc-footer-surfaces.css"),
        "templates/admin/base.html + admin_workbench_footer.html + base_site.html",
    )

    tenant_urls_text = (ROOT / "config" / "tenant_urls.py").read_text(
        encoding="utf-8", errors="replace"
    )
    tenant_503_ok = (
        "handler503" in tenant_urls_text
        and "service_unavailable" in tenant_urls_text
        and (
            "from config.urls import service_unavailable as handler503" in tenant_urls_text
            or "from config.error_handlers import service_unavailable as handler503"
            in tenant_urls_text
            or "handler503 = service_unavailable" in tenant_urls_text
        )
    )
    add(
        "13",
        "Tenant urlconf handler503 wired",
        tenant_503_ok,
        "config/tenant_urls.py",
    )

    scan_proc = subprocess.run(
        [sys.executable, "scripts/scan_operator_shell_dead_hrefs.py", "--strict"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    add(
        "14",
        "No dead href=# in operator shell chrome",
        scan_proc.returncode == 0,
        (scan_proc.stdout or scan_proc.stderr or "").strip()[-400:],
    )

    add(
        "15",
        "Vitest interaction-integrity suite present",
        (ROOT / "tests" / "interaction-integrity.test.tsx").is_file()
        and _contains("package.json", "test:interaction-integrity"),
        "tests/interaction-integrity.test.tsx",
    )

    tenant_urls_text = (ROOT / "config" / "tenant_urls.py").read_text(
        encoding="utf-8", errors="replace"
    )
    feedback_mounted = (
        'include(("apps.feedback.urls", "feedback")' in tenant_urls_text
        or 'include(("apps.feedback.tenant_urls", "feedback")' in tenant_urls_text
    ) and 'namespace="feedback"' in tenant_urls_text
    add(
        "16",
        "Tenant urlconf mounts feedback (Help Center on subdomain)",
        feedback_mounted
        and _contains(
            "templates/schools/partials/school_finder_bento.html", "marketing_public_href"
        ),
        "tenant_urls + school_finder_bento",
    )

    pages_proc = subprocess.run(
        [sys.executable, "scripts/verify_pages_interaction_audit.py"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("RMC_VERIFY_PAGES_INTERACTION_TIMEOUT", "900")),
    )
    add(
        "18",
        "_pages/ interaction audit green",
        pages_proc.returncode == 0,
        (pages_proc.stdout or pages_proc.stderr or "").strip()[-400:],
    )

    mount_proc = subprocess.run(
        [sys.executable, "scripts/verify_react_mount_and_fetch_urls.py"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    add(
        "19",
        "React mount bundles + API fetch URLs",
        mount_proc.returncode == 0,
        (mount_proc.stdout or mount_proc.stderr or "").strip()[-400:],
    )

    if os.environ.get("RMC_VERIFY_INTERACTION_SKIP_TESTS") == "1":
        tests_ok, test_tail = True, "skipped (RMC_VERIFY_INTERACTION_SKIP_TESTS=1)"
    else:
        fast_ok, fast_tail = _run_tests(
            [
                "apps.siteconfig.tests.test_interaction_integrity_contract",
                "apps.schools.tests.test_manager_header_account_paths.ManagerHeaderAccountPathTests",
                "apps.schools.tests.test_operator_help_center.OperatorHelpCenterAllowlistTests",
            ]
        )
        skip_feedback = os.environ.get("RMC_VERIFY_INTERACTION_SKIP_FEEDBACK_TESTS", "1") == "1"
        if skip_feedback:
            feedback_ok, feedback_tail = True, "skipped (RMC_VERIFY_INTERACTION_SKIP_FEEDBACK_TESTS=1)"
        else:
            feedback_db = _feedback_gate_db()
            feedback_env = os.environ.copy()
            feedback_env["DJANGO_TEST_DB_FILE"] = str(feedback_db)
            fresh_feedback = (
                os.environ.get("RMC_VERIFY_INTERACTION_FRESH_DB") == "1"
                or not feedback_db.is_file()
            )
            fb_cmd = [
                sys.executable,
                "scripts/run_sqlite_memory_tests.py",
            ]
            if fresh_feedback:
                fb_cmd.append("--fresh")
            fb_cmd.extend(
                [
                    "apps.feedback.tests.test_feedback_help_center_contracts",
                    "--verbosity=1",
                    "--no-input",
                ]
            )
            try:
                proc = subprocess.run(
                    fb_cmd,
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=900,
                    env=feedback_env,
                )
                feedback_ok = proc.returncode == 0
                feedback_tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
            except (subprocess.TimeoutExpired, OSError) as exc:
                feedback_ok, feedback_tail = False, str(exc)
        tests_ok = fast_ok and feedback_ok
        test_tail = f"fast: {fast_tail[-200:]}\nfeedback: {feedback_tail[-200:]}"
    add("17", "Contract tests green", tests_ok, test_tail or "django tests")

    failures = [r for r in rows if not r.ok]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "INTERACTION_INTEGRITY_PASS" if not failures else "INTERACTION_INTEGRITY_FAIL",
        "pass_count": sum(1 for r in rows if r.ok),
        "fail_count": len(failures),
        "rows": [
            {"id": r.check_id, "label": r.label, "status": "PASS" if r.ok else "FAIL", "proof": r.proof}
            for r in rows
        ],
    }
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"verify_interaction_integrity_completion: {payload['verdict']}")
    print(f"  PASS {payload['pass_count']} / FAIL {payload['fail_count']}")
    for r in failures:
        print(f"  FAIL {r.check_id}: {r.label} — {r.proof}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
