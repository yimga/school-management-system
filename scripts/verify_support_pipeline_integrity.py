#!/usr/bin/env python3
"""
Support pipeline integrity gate: KB scope, engine room, help center contracts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
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


def _run_tests(labels: list[str]) -> tuple[bool, str]:
    gate_db = ROOT / ".django_test_dbs" / f"support_pipeline_gate_{int(time.time())}.sqlite3"
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
        "KB AI panel uses support assistant API",
        _contains("templates/portal/partials/kb_ai_assistant_panel.html", "ai-support-assistant")
        and _contains("static/js/rmc-kb-ai-assistant.js", "escalation_required"),
        "kb_ai_assistant_panel + JS",
    )
    add(
        "5",
        "Vitest support pipeline suites",
        (ROOT / "tests/support-pipeline-integrity.test.tsx").is_file()
        and (ROOT / "tests/support-ai-engine.test.tsx").is_file(),
        "tests/*.tsx",
    )

    vitest = subprocess.run(
        ["npm", "run", "test:support-pipeline"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    add("6", "Vitest support pipeline green", vitest.returncode == 0, (vitest.stdout or vitest.stderr or "")[-400:])

    tests_ok, test_tail = _run_tests(
        [
            "apps.portal.tests.test_kb_audience_filters",
            "apps.feedback.tests.test_feedback_help_center_contracts",
            "services.ai.tests.test_multitenant_isolation",
            "services.ai.tests.test_code_oracle",
        ]
    )
    add("7", "Django support pipeline tests green", tests_ok, test_tail or "django tests")

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
