#!/usr/bin/env python3
"""
Operator Help Center + KB control-plane completion gate.

Writes docs/generated/operator_help_center_audit.json
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
GENERATED = ROOT / "docs" / "generated" / "operator_help_center_audit.json"


@dataclass
class Row:
    check_id: str
    label: str
    ok: bool
    proof: str


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _contains(rel: str, needle: str) -> bool:
    return needle in _read(rel)


def _run_tests(labels: list[str]) -> tuple[bool, str]:
    gate_db = ROOT / ".django_test_dbs" / "operator_help_center_gate.sqlite3"
    cmd = [sys.executable, "scripts/run_sqlite_memory_tests.py", *labels, "--verbosity=1", "--no-input"]
    env = {**os.environ, "DJANGO_TEST_DB_FILE": str(gate_db)}
    try:
        proc = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600, env=env
        )
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-800:]
        return proc.returncode == 0, tail
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def main() -> int:
    rows: list[Row] = []

    def add(check_id: str, label: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, label, ok, proof))

    add(
        "help-center-module",
        "manager_help_center view module",
        (ROOT / "config/manager_help_center.py").is_file(),
        "manager_help_center.py",
    )
    add(
        "help-center-url",
        "manager_urls registers help-center + manager_help redirect",
        _contains("config/manager_urls.py", 'name="manager_help_center"')
        and _contains("config/manager_urls.py", 'reverse("manager_help_center")'),
        "manager_urls.py",
    )
    add(
        "middleware-help-center",
        "Manager allowlist includes /help-center/",
        _contains("apps/schools/middleware.py", '"/help-center/"'),
        "middleware.py",
    )
    add(
        "dropdown-help-center",
        "User dropdown Help uses manager_help_center on manager",
        _contains("templates/components/user_dropdown.html", "manager_help_center"),
        "user_dropdown.html",
    )
    add(
        "kb-operator-render",
        "Operator KB render helper",
        (ROOT / "apps/portal/operator_kb_render.py").is_file(),
        "operator_kb_render.py",
    )
    for partial in (
        "templates/portal/operator/kb_home_body.html",
        "templates/portal/operator/kb_article_body.html",
        "templates/portal/operator/kb_category_body.html",
        "templates/portal/operator/kb_search_body.html",
        "templates/portal/operator/office_list_body.html",
        "templates/portal/operator/faq_list_body.html",
        "templates/schools/partials/manager_help_center_body.html",
        "templates/schools/partials/manager_feedback_loop_body.html",
    ):
        add(
            f"partial-{Path(partial).stem}",
            f"Template exists: {partial}",
            (ROOT / partial).is_file(),
            partial,
        )
    add(
        "kb-ai-panel",
        "KB AI assistant panel + JS",
        (ROOT / "templates/portal/partials/kb_ai_assistant_panel.html").is_file()
        and (ROOT / "static/js/rmc-kb-ai-assistant.js").is_file(),
        "kb_ai_assistant",
    )
    add(
        "kb-views-wired",
        "KB views use render_kb_if_operator",
        all(
            needle in _read("apps/portal/views_kb.py")
            for needle in (
                "render_kb_if_operator",
                "portal/operator/kb_home_body.html",
                "portal/operator/kb_article_body.html",
                "portal/operator/faq_list_body.html",
            )
        ),
        "views_kb.py",
    )
    add(
        "report-pages-cp-base",
        "Operator report pages extend control_plane_base",
        all(
            _contains(t, "control_plane_base.html")
            for t in (
                "templates/schools/manager_feature_gap_register.html",
                "templates/schools/manager_lane2_readiness.html",
                "templates/schools/manager_public_to_product_matrix.html",
            )
        ),
        "manager report templates",
    )
    add(
        "feedback-loop-render",
        "Feedback loop uses render_manager_report_page",
        _contains("config/manager_feedback_loop.py", "render_manager_report_page"),
        "manager_feedback_loop.py",
    )
    add(
        "help-signals-module",
        "Shared operator help signals module",
        (ROOT / "apps/schools/operator_help_signals.py").is_file()
        and _contains("config/manager_help_center.py", "operator_help_signal_bundle")
        and _contains("config/manager_help_center.py", "help_sections"),
        "operator_help_signals.py",
    )
    add(
        "help-center-v2-ui",
        "Help hub search + AI + metrics + grouped sections",
        (ROOT / "static/js/rmc-operator-help-center.js").is_file()
        and _contains(
            "templates/schools/partials/manager_help_center_body.html",
            "kb_ai_assistant_panel",
        )
        and _contains(
            "templates/schools/partials/manager_help_center_body.html",
            "rmc-help-center__metrics",
        ),
        "manager_help_center_body.html",
    )
    add(
        "faq-detail-operator",
        "FAQ detail uses operator control-plane shell",
        (ROOT / "templates/portal/operator/faq_detail_body.html").is_file()
        and _contains("apps/portal/views_kb.py", "portal/operator/faq_detail_body.html"),
        "views_kb.py faq_detail",
    )

    # HTTP integration lives in OperatorHelpCenterHttpTests (run locally after migrate).
    tests_ok, tail = _run_tests(
        [
            "apps.schools.tests.test_operator_help_center.OperatorHelpCenterAllowlistTests",
            "apps.schools.tests.test_operator_help_signals",
            "apps.schools.tests.test_manager_header_account_paths.ManagerHeaderAccountPathTests",
        ]
    )
    add("tests", "Operator help center + manager path tests", tests_ok, tail or "django tests")

    failures = [r for r in rows if not r.ok]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "OPERATOR_HELP_CENTER_PASS" if not failures else "OPERATOR_HELP_CENTER_FAIL",
        "pass_count": sum(1 for r in rows if r.ok),
        "fail_count": len(failures),
        "rows": [
            {"id": r.check_id, "label": r.label, "status": "PASS" if r.ok else "FAIL", "proof": r.proof}
            for r in rows
        ],
    }
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(payload["verdict"], f"({payload['pass_count']} pass / {payload['fail_count']} fail)")
    for r in failures:
        print(f"  FAIL {r.check_id}: {r.label} — {r.proof}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
