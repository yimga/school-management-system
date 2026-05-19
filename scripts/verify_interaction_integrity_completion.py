#!/usr/bin/env python3
"""
Platform-wide interaction integrity gate (Help Center, RBAC UI, VoC, header dropdown, HTTP errors).

Writes docs/generated/interaction_integrity_audit.json
"""

from __future__ import annotations

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


def _run_tests(labels: list[str]) -> tuple[bool, str]:
    # Isolated fresh DB per gate run — avoids Windows keepdb lock / stale schema flakes.
    gate_db = ROOT / ".django_test_dbs" / f"interaction_integrity_gate_{int(time.time())}.sqlite3"
    env = os.environ.copy()
    env["DJANGO_TEST_DB_FILE"] = str(gate_db)
    cmd = [sys.executable, "scripts/run_sqlite_memory_tests.py", "--fresh", *labels]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-800:]
        return proc.returncode == 0, tail
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

    add(
        "11",
        "Manager header account menu gate",
        _contains("apps/schools/middleware.py", "/authentication/documentation/")
        and _contains("config/manager_urls.py", 'reverse("kb:kb_home")')
        and _contains("static/css/rmc-platform-header.css", "--rmc-header-control-height")
        and (ROOT / "apps/accounts/operator_account_render.py").is_file(),
        "middleware + manager_urls + CSS + operator_account_render",
    )

    add(
        "12",
        "Manager /admin/ compact operator footer",
        _contains("templates/admin/base.html", "rmc_operator_footer_compact.html")
        and _contains("templates/admin/base.html", 'data-rmc-footer-surface="operator-compact"')
        and _contains("templates/admin/base_site.html", "rmc-footer-surfaces.css"),
        "templates/admin/base.html + base_site.html",
    )

    tenant_503_ok = _contains(
        "config/tenant_urls.py",
        "from config.urls import service_unavailable as handler503",
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

    tests_ok, test_tail = _run_tests(
        [
            "apps.siteconfig.tests.test_interaction_integrity_contract",
            "apps.feedback.tests.test_feedback_help_center_contracts",
            "apps.schools.tests.test_manager_header_account_paths",
        ]
    )
    add("16", "Contract tests green", tests_ok, test_tail or "django tests")

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
