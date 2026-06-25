"""Static contract verifier for Workflow Recovery Command Center."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, needle: str, *, path: str) -> None:
    if needle not in text:
        raise AssertionError(f"{path} is missing {needle!r}")


def main() -> None:
    taxonomy_path = "apps/platform_runtime/workflow_status_taxonomy.py"
    taxonomy = read(taxonomy_path)
    for token in (
        "WORKFLOW_STATUS_TAXONOMY",
        '"stuck"',
        '"yellow"',
        '"failed"',
        '"red"',
        '"cancelled"',
        '"healing"',
        '"teal"',
        '"succeeded"',
        '"green"',
        '"superseded"',
        "recovery_context_for_run",
    ):
        require(taxonomy, token, path=taxonomy_path)

    handlers_path = "apps/platform_runtime/workflow_fix_handlers.py"
    handlers = read(handlers_path)
    for token in (
        "AUTO_FIX_HANDLER_CATALOG",
        "_mark_run_remediated",
        "workflow_fix_remediation",
        "repair_tenant_schema_drift",
        "run_tenant_migrations",
        "resume_from_checkpoint",
        "retry_failed_step",
        "replay_webhook",
        "clear_stale_lock",
        "mark_superseded",
        "heal_tenant_schema_drift",
        "auto_fix_kind_is_executable",
        "missing_webhook_replay_target",
        "cancel_duplicate_run",
        "resume_from_checkpoint",
    ):
        require(handlers, token, path=handlers_path)

    actions_path = "apps/platform_runtime/workflow_flight_deck_actions.py"
    actions = read(actions_path)
    for token in (
        "auto_fix_kind_is_executable",
        "copilot_recovery_context",
        "workflow_run_is_remediated",
        "Open AI diagnosis",
    ):
        require(actions, token, path=actions_path)

    playbook_path = "apps/platform_runtime/workflow_recovery_playbook.py"
    playbook = read(playbook_path)
    for token in (
        "recovery_strategy_for_workflow",
        "workflow_recovery_coverage",
        "recovery_coverage_gaps",
        "tenant_school_provision",
        "replay_webhook",
        "operator_guided",
    ):
        require(playbook, token, path=playbook_path)

    views_path = "apps/platform_runtime/views_workflow_flight_deck.py"
    views = read(views_path)
    for token in (
        "status_taxonomy",
        "status_taxonomy_payload",
        "workflow_progress_stream",
        "recovery_queue",
        "healing_count",
    ):
        require(views, token, path=views_path)

    detail_path = "apps/platform_runtime/views_workflow_progress.py"
    detail = read(detail_path)
    for token in (
        "status_meta",
        "remediation_stamp",
        "refresh_deck",
        "healing_poll_ms",
        "copilot_recovery_context",
    ):
        require(detail, token, path=detail_path)

    js_path = "static/js/rmc-workflow-flight-deck.js"
    js = read(js_path)
    for token in (
        "connectLiveStream",
        "scheduleHealingRefresh",
        "renderHealingCommand",
        "status_meta",
        "stopped_count",
        "capability",
    ):
        require(js, token, path=js_path)

    css_path = "static/css/rmc-workflow-flight-deck.css"
    css = read(css_path)
    for token in (
        "rmc-wf-status--running",
        "rmc-wf-status--stuck",
        "#facc15",
        "rmc-wf-status--failed",
        "rmc-wf-status--cancelled",
        "#ef4444",
        "rmc-wf-status--healing",
        "#2dd4bf",
        "rmc-wf-status--succeeded",
        "#22c55e",
        "rmc-wf-status--superseded",
    ):
        require(css, token, path=css_path)

    tests_path = "apps/platform_runtime/tests/test_workflow_flight_deck.py"
    tests = read(tests_path)
    for token in (
        "test_apply_fix_removes_remediated_run_from_failure_deck",
        "test_flight_deck_json_includes_status_taxonomy",
        "test_status_taxonomy_matches_recovery_colors",
        "test_replay_webhook_requires_target_metadata",
        "test_replay_webhook_replays_platform_event",
        "test_clear_stale_lock_deletes_explicit_cache_key",
        "test_cancel_duplicate_run_cancels_active_duplicate",
        "test_resume_from_checkpoint_routes_provision_to_requeue",
        "test_workflow_recovery_playbook_covers_registry",
    ):
        require(tests, token, path=tests_path)

    print("WORKFLOW_RECOVERY_COMMAND_CENTER_PASS")


if __name__ == "__main__":
    main()
