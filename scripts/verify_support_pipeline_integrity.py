#!/usr/bin/env python3
"""
Support pipeline integrity gate: KB scope, engine room, help center contracts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "support_pipeline_integrity_audit.json"


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
        "operator_help_center_gate.sqlite3",
        "interaction_integrity_gate_v2.sqlite3",
        "manager_header_account_gate.sqlite3",
        "rmc_sqlite_test_runner.sqlite3",
    ):
        candidate = tdir / name
        if candidate.is_file():
            return candidate
    return tdir / "support_pipeline_gate.sqlite3"


def _run_tests(labels: list[str]) -> tuple[bool, str]:
    """Prefer direct runner (pre-migrated DB copy + migrate) over manage.py test recreate."""
    seed = ROOT / ".django_test_dbs" / "rmc_sqlite_test_runner.sqlite3"
    if seed.is_file():
        try:
            proc = subprocess.run(
                [sys.executable, "scripts/run_support_pipeline_tests_direct.py"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=600,
            )
            combined = ((proc.stdout or "") + (proc.stderr or "")).strip()
            tail = combined[-1200:]
            if proc.returncode == 0:
                return True, tail
            return False, tail or f"direct runner exit {proc.returncode}"
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, f"direct runner: {exc}"

    gate_db = _pick_gate_db()
    env = os.environ.copy()
    env["DJANGO_TEST_DB_FILE"] = str(gate_db)
    fresh = os.environ.get("RMC_VERIFY_SUPPORT_PIPELINE_FRESH_DB") == "1" or not gate_db.is_file()
    cmd = [
        sys.executable,
        "scripts/run_sqlite_memory_tests.py",
        *labels,
        "--verbosity=1",
        "--no-input",
    ]
    if fresh:
        cmd.insert(2, "--fresh")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=1800,
            env=env,
        )
        combined = ((proc.stdout or "") + (proc.stderr or "")).strip()
        tail = combined[-800:]
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

    add(
        "1",
        "KB school + global scope fields",
        _contains("apps/portal/models_kb.py", "is_global_article")
        and _contains("apps/portal/kb_context.py", "filter_kb_articles_by_school"),
        "models_kb + kb_context",
    )
    add(
        "2",
        "KB download uses published visibility filter",
        _contains(
            "apps/portal/views_kb.py",
            "get_object_or_404(_published_kb_for_request(request), slug=article_slug)",
        ),
        "views_kb kb_article_download_pdf",
    )
    add(
        "3",
        "Engine room code oracle + token manager",
        (ROOT / "services/ai/code_oracle.py").is_file()
        and (ROOT / "services/ai/token_manager.py").is_file(),
        "services/ai",
    )
    add(
        "4",
        "KB AI panel uses support assistant API + SSE stream",
        _contains("templates/portal/partials/kb_ai_assistant_panel.html", "ai-support-assistant")
        and _contains("templates/portal/partials/kb_ai_assistant_panel.html", "api:ai-support-assistant")
        and _contains("templates/portal/partials/kb_ai_assistant_panel.html", "ai-support-assistant-stream")
        and _contains("static/js/rmc-kb-ai-assistant.js", "escalation_required")
        and _contains("static/js/rmc-kb-ai-assistant.js", "text/event-stream"),
        "kb_ai_assistant_panel + JS",
    )
    add(
        "4b",
        "KBArticle vector_embedding + kb_embeddings module",
        _contains("apps/portal/models_kb.py", "vector_embedding")
        and (ROOT / "apps/portal/kb_embeddings.py").is_file(),
        "models_kb + kb_embeddings",
    )
    add(
        "4c",
        "SupportErrorBoundary React component",
        (ROOT / "src/components/support/SupportErrorBoundary.tsx").is_file(),
        "SupportErrorBoundary.tsx",
    )
    add(
        "4d",
        "Playwright help-center crawl spec",
        (ROOT / "tests/e2e/help-center-crawl.spec.js").is_file(),
        "help-center-crawl.spec.js",
    )
    add(
        "4e",
        "Support deflection graft (1331)",
        (ROOT / "apps/portal/support_deflection.py").is_file()
        and _contains("apps/api/urls.py", "support-deflection"),
        "support_deflection + api route",
    )
    add(
        "4f",
        "Support sanitize + intent modules (1332/1333)",
        (ROOT / "services/ai/support_sanitize.py").is_file()
        and (ROOT / "services/ai/support_intent.py").is_file(),
        "support_sanitize + support_intent",
    )
    add(
        "4g",
        "Code support index module (1335)",
        (ROOT / "services/ai/code_index.py").is_file(),
        "code_index.py",
    )
    add(
        "5",
        "Vitest support pipeline suites",
        (ROOT / "tests/support-pipeline-integrity.test.tsx").is_file()
        and (ROOT / "tests/support-ai-engine.test.tsx").is_file(),
        "tests/*.tsx",
    )

    npm = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
    vitest_timeout = int(os.environ.get("RMC_VERIFY_SUPPORT_PIPELINE_VITEST_TIMEOUT", "300"))
    vitest = subprocess.run(
        [npm, "run", "test:support-pipeline"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=vitest_timeout,
        shell=(os.name == "nt" and npm == "npm"),
    )
    add("6", "Vitest support pipeline green", vitest.returncode == 0, (vitest.stdout or vitest.stderr or "")[-400:])

    kb_contract_ok = all(
        _contains("apps/portal/tests/test_kb_audience_filters.py", token)
        for token in (
            "test_operator_request_hides_tenant_content",
            "test_tenant_request_hides_operator_content",
            "is_operator_help_request",
            "is_global_article",
        )
    )
    add(
        "7",
        "KB audience filter contracts in tree",
        kb_contract_ok,
        "test_kb_audience_filters.py",
    )

    seed_db = ROOT / ".django_test_dbs" / "rmc_sqlite_test_runner.sqlite3"
    run_db_tests = os.environ.get("RMC_VERIFY_SUPPORT_PIPELINE_RUN_DB_TESTS", "").strip()
    if run_db_tests == "":
        run_db_tests = "1" if seed_db.is_file() else "0"
    test_labels = [
        "services.ai.tests.test_code_oracle",
        "services.ai.tests.test_multitenant_isolation",
    ]
    if run_db_tests == "1" and not seed_db.is_file():
        test_labels.extend(
            [
                "apps.portal.tests.test_kb_audience_filters",
                "apps.portal.tests.test_support_ticket_portal",
            ]
        )
    if run_db_tests == "1" and os.environ.get("RMC_VERIFY_SUPPORT_PIPELINE_SKIP_FEEDBACK_TESTS", "1") == "0":
        test_labels.append("apps.feedback.tests.test_feedback_help_center_contracts")
    tests_ok, test_tail = _run_tests(test_labels)
    add("8", "Django support pipeline unit tests green", tests_ok, test_tail or "django tests")

    failures = [r for r in rows if not r.ok]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "SUPPORT_PIPELINE_PASS" if not failures else "SUPPORT_PIPELINE_FAIL",
        "pass_count": sum(1 for r in rows if r.ok),
        "fail_count": len(failures),
        "rows": [
            {"id": r.check_id, "label": r.label, "status": "PASS" if r.ok else "FAIL", "proof": r.proof}
            for r in rows
        ],
    }
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"verify_support_pipeline_integrity: {payload['verdict']}")
    for r in failures:
        print(f"  FAIL {r.check_id}: {r.label} — {r.proof}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
