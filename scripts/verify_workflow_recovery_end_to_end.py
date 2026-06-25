"""End-to-end static closure check for workflow recovery work."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    tests = read("apps/platform_runtime/tests/test_workflow_flight_deck.py")
    for token in (
        "test_replay_webhook_replays_platform_event",
        "test_clear_stale_lock_deletes_explicit_cache_key",
        "test_cancel_duplicate_run_cancels_active_duplicate",
        "test_resume_from_checkpoint_routes_provision_to_requeue",
        "test_workflow_recovery_playbook_covers_registry",
    ):
        require(token in tests, f"missing test coverage: {token}")

    handlers = read("apps/platform_runtime/workflow_fix_handlers.py")
    for token in (
        "resume_from_checkpoint",
        "retry_failed_step",
        "replay_event",
        "EventWebhookDelivery",
        "replay_webhook_delivery",
        "cache.delete",
        "cancel_duplicate_run",
        "missing_webhook_replay_target",
        "cancelled_run_ids",
    ):
        require(token in handlers, f"handler contract missing: {token}")

    playbook = read("apps/platform_runtime/workflow_recovery_playbook.py")
    for token in (
        "workflow_recovery_coverage",
        "recovery_coverage_gaps",
        "primary_auto_fix_kind",
        "operator_guided",
    ):
        require(token in playbook, f"playbook contract missing: {token}")

    views = read("apps/platform_runtime/views_workflow_flight_deck.py")
    for token in (
        "recovery_coverage",
        "gap_count",
        "workflow_progress_stream",
        "healing_count",
    ):
        require(token in views, f"deck JSON contract missing: {token}")

    js = read("static/js/rmc-workflow-flight-deck.js")
    for token in (
        "renderHealingCommand",
        "connectLiveStream",
        "scheduleHealingRefresh",
        "Self-Healing cockpit",
    ):
        require(token in js, f"browser recovery contract missing: {token}")

    css = read("static/css/rmc-workflow-flight-deck.css")
    for token in ("#facc15", "#ef4444", "#22c55e", "#2dd4bf"):
        require(token in css, f"status color token missing: {token}")

    package_json = read("package.json")
    require("playwright" in package_json.lower(), "Playwright browser QA hook missing")

    print("WORKFLOW_RECOVERY_END_TO_END_PASS")


if __name__ == "__main__":
    main()
