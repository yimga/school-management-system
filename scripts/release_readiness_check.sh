#!/usr/bin/env bash
set -euo pipefail

echo "== 0) Environment =="
python --version
echo "PWD: $(pwd)"

python_text_check() {
  local mode="$1"
  local pattern="$2"
  shift 2
  python - "$mode" "$pattern" "$@" <<'PY'
import pathlib
import re
import sys

mode = sys.argv[1]
pattern = re.compile(sys.argv[2])
paths = [pathlib.Path(p) for p in sys.argv[3:]]

if mode == "forbid":
    hits = []
    for root in paths:
        if root.is_dir():
            for p in root.rglob("*.py"):
                text = p.read_text(encoding="utf-8", errors="ignore")
                if pattern.search(text):
                    hits.append(str(p))
        elif root.is_file():
            text = root.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text):
                hits.append(str(root))
    if hits:
        print("Forbidden pattern matches found:")
        for h in hits:
            print(h)
        sys.exit(1)
    print("OK: no forbidden direct provider patterns in apps/")
    sys.exit(0)

if mode == "require":
    missing = []
    for p in paths:
        text = p.read_text(encoding="utf-8", errors="ignore")
        if not pattern.search(text):
            missing.append(str(p))
    if missing:
        print("Required pattern missing from:")
        for m in missing:
            print(m)
        sys.exit(1)
    for p in paths:
        print(f"OK: required pattern found in {p}")
    sys.exit(0)

print(f"Unknown mode: {mode}")
sys.exit(2)
PY
}

echo "== 1) Lint/grep enforcement: no forbidden direct cloud AI in apps =="
python_text_check "forbid" "google\.generativeai|generativelanguage\.googleapis|anthropic|openai\.OpenAI\(" apps

echo "== 2) Config/flag presence checks =="
python_text_check "require" "ENABLE_AI_KNOWLEDGE_INDEX_BEAT|ENABLE_AI_QUALITY_SCORECARD_BEAT|ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT|ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT|ENABLE_AUTOMATION_FAILURE_TREND_BEAT" config/settings.py
python_text_check "require" "MIGRATION_PLAYBOOK_MIN_CONFIDENCE_SCORE|ENABLE_AI_KNOWLEDGE_INDEX_BEAT|ENABLE_AI_QUALITY_SCORECARD_BEAT|ENABLE_OPERATOR_VISIBILITY_HEARTBEAT_BEAT|ENABLE_DATABASE_CONNECTIVITY_HEARTBEAT_BEAT|ENABLE_AUTOMATION_FAILURE_TREND_BEAT" .env.example

echo "== 3) Docs/SOT evidence checks =="
python_text_check "require" "ai_quality_scorecard|/api/ai/feedback|MIGRATION_PLAYBOOK_MIN_CONFIDENCE_SCORE|preflight confidence|automation_failure_trend_signal" docs/architecture/ai_orchestration.md
python_text_check "require" "ENABLE_AI_QUALITY_SCORECARD_BEAT|ENABLE_AI_KNOWLEDGE_INDEX_BEAT" docs/OLLAMA_OPERATIONS_AND_UPDATES.md
python_text_check "require" "A \(RAG \+ eval\)|B \(Migration\)|C \(Non-migration beats\)" docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md

echo "== 4) Python compile sanity (changed core files) =="
python -m py_compile \
  apps/automation/playbook_executor.py \
  apps/platform_runtime/tasks.py \
  apps/siteconfig/tasks.py \
  apps/siteconfig/management/commands/ai_quality_scorecard.py \
  services/ai_gateway.py \
  services/ai_memory.py

echo "== 5) Targeted test suite (strict) =="
python -m pytest \
  apps/automation/tests/test_playbook_quarantine_and_logs.py \
  apps/automation/tests/test_migration_cloud_phase_a.py::PlaybookExecutorTests \
  apps/platform_runtime/tests/test_health_heartbeat_tasks.py \
  apps/siteconfig/tests/test_ai_quality_scorecard.py \
  apps/siteconfig/tests/test_ai_gateway_metrics.py \
  services/tests/test_ai_gateway.py \
  services/tests/test_ai_gateway_invoke_regression.py \
  services/tests/test_ai_memory.py \
  services/tests/test_open_source_ai_enforcement.py \
  apps/portal/tests/test_ai_feedback.py \
  apps/siteconfig/tests/test_index_ai_knowledge_beat_task.py \
  apps/automation/tests/test_outcomes_console_quarantine.py \
  -q --tb=short

echo "== 6) Optional: aggregate/scorecard smoke (non-fatal if no metrics) =="
python manage.py ai_quality_scorecard --days 7 || true

echo "== 7) Collabora blocker reducer (internal preflight) =="
python scripts/verify_kb_libreoffice_stack.py

if [[ -n "${APP_BASE_URL:-}" && -n "${COLLABORA_BASE_URL:-}" ]]; then
  echo "Running Collabora/WOPI smoke with provided APP_BASE_URL/COLLABORA_BASE_URL..."
  python scripts/verify_collabora_wopi_smoke.py \
    --app-base "${APP_BASE_URL}" \
    --collabora-base "${COLLABORA_BASE_URL}" \
    --office-doc-id "${WOPI_OFFICE_DOC_ID:-}" \
    --session-cookie "${APP_SESSION_COOKIE:-}"
else
  echo "Skipping live Collabora/WOPI smoke (set APP_BASE_URL and COLLABORA_BASE_URL to enable)."
fi

echo "== 8) Clever/ClassLink blocker reducer (internal readiness) =="
python scripts/verify_clever_classlink_readiness.py
python -m pytest apps/interop/tests/test_clever_classlink_client.py -q --tb=short

echo "== DONE: Release readiness checks passed for A/B/C/D =="
