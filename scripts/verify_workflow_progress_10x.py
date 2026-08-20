#!/usr/bin/env python3
"""Workflow Progress 10x gate — smoke + coverage + shell wiring markers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUBPROCESS_SCRIPTS = (
    "scripts/smoke_workflow_progress_bus.py",
    "scripts/verify_workflow_progress_coverage.py",
    "scripts/verify_workflow_10x_waves_complete.py",
    "scripts/verify_workflow_progress_shell_strip.py",
    "scripts/verify_workflow_telemetry_coverage.py",
)

STATIC_MARKERS = (
    ("apps/platform_runtime/models_workflow_10x.py", "WorkflowAutopilotPolicy"),
    ("apps/platform_runtime/workflow_autopilot.py", "try_auto_apply_on_failure"),
    ("apps/platform_runtime/workflow_degrading.py", "is_degrading"),
    ("apps/platform_runtime/workflow_fix_handlers.py", "preview_auto_fix_kind"),
    ("apps/platform_runtime/workflow_sla.py", "publish_sla_breach_event"),
    ("templates/emails/operator_workflow_sla_breached.txt", "SLA exceeded"),
    ("apps/platform_runtime/tasks.py", "workflow_sla_breach_alert_sweep"),
    ("static/js/rmc-workflow-progress.js", "preview-fix"),
    ("apps/platform_runtime/views_workflow_flight_deck.py", "flight_deck_view"),
    ("apps/platform_runtime/views_workflow_trust.py", "tenant_trusted_stream_view"),
    ("apps/platform_runtime/workflow_incidents.py", "cluster_recent_incidents"),
    ("apps/platform_runtime/workflow_sla.py", "slo_seconds_for_key"),
    ("apps/platform_runtime/views_workflow_autopilot.py", "enable_autopilot_view"),
    ("apps/platform_runtime/workflow_tenant_trust.py", "list_tenant_trusted_runs"),
    ("apps/platform_runtime/views_workflow_trust.py", "tenant_trusted_active_view"),
    ("templates/components/rmc_workflow_tenant_trust_strip.html", "rmc-wfp-tenant-trust"),
    ("static/js/rmc-workflow-tenant-trust.js", "tenant-trusted/active"),
    ("apps/schools/control_plane_nav.py", "super_workflow_flight_deck"),
    ("apps/platform_runtime/migrations/0079_workflow_10x_models.py", "WorkflowAutopilotPolicy"),
    ("templates/platform_runtime/workflow_flight_deck.html", "rmc-wfp-flight-deck"),
    ("templates/platform_runtime/workflow_flight_deck.html", "data-rmc-flight-simulate"),
    ("static/js/rmc-workflow-flight-deck.js", "rmc-workflow-copilot-context"),
    ("static/js/rmc-workflow-flight-deck.js", "data-rmc-flight-tab"),
    ("static/css/rmc-workflow-flight-deck.css", "rmc-wfp-flight-deck"),
    ("static/css/rmc-workflow-flight-deck.css", "rmc-wfp-remediator"),
    ("apps/platform_runtime/workflow_attention_gateway.py", "action_required"),
    ("apps/platform_runtime/workflow_kickoff_live.py", "compose_engine_attention"),
    ("apps/platform_runtime/workflow_simulation.py", "SIMULATION_WORKFLOW_KEY"),
    ("config/settings.py", "WorkflowProgressRequestMiddleware"),
    ("templates/control_plane_skeleton.html", "rmc-workflow-track-headers.js"),
    ("templates/partials/rmc_tools_tray_context_stack.html", "data-rmc-wfp-tray-slot"),
    ("templates/partials/rmc_tools_tray_context_stack.html", "rmc_workflow_progress_strip.html"),
    ("templates/portal_base.html", "rmc-workflow-track-headers.js"),
    ("static/js/rmc-workflow-progress.js", "progress_percent"),
    ("static/js/rmc-workflow-track-headers.js", "X-RMC-Workflow-Track"),
    ("apps/platform_runtime/workflow_tracker.py", "active_workflow_run"),
    ("apps/platform_runtime/workflow_celery_bridge.py", "_CELERY_WORKFLOW_KEY_OVERRIDES"),
    ("apps/platform_runtime/workflow_telemetry.py", "update_and_broadcast_progress"),
    ("templates/components/rmc_workflow_progress_canvas.html", "rmc-wfp-canvas"),
    ("static/js/rmc-workflow-progress-canvas.js", "ws/workflow-progress/"),
    ("apps/migration_cloud/celery_tasks.py", "migration_bundle_apply"),
    ("apps/evals/tasks.py", "evals_bulk_grades"),
    ("apps/finance/tasks.py", "finance_auto_generate_fee_invoices"),
    ("apps/marketplace/tasks.py", "marketplace_webhook_deliver_due"),
    ("apps/platform_runtime/views_workflow_progress.py", "e2e_demo_start_view"),
    ("apps/platform_runtime/workflow_tracker.py", "_visible_in_progress_chip"),
    ("apps/platform_runtime/workflow_guidance.py", "normalize_path_for_workflow_registry"),
    ("apps/platform_runtime/workflow_request_middleware.py", "resolve_workflow_for_route"),
    ("tests/e2e/workflow-progress.spec.js", "e2e-demo/start"),
    ("apps/platform_runtime/tests/test_workflow_progress_http.py", "_should_track_request"),
    ("scripts/smoke_render_workflow_progress_deploy.py", "RENDER_WORKFLOW_PROGRESS_SMOKE_PASS"),
)


def _run(script: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def main() -> int:
    failures: list[str] = []

    for script in SUBPROCESS_SCRIPTS:
        code, out = _run(script)
        if code != 0:
            failures.append(f"{script}:\n{out[-800:]}")

    for rel, needle in STATIC_MARKERS:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing file: {rel}")
            continue
        if needle not in path.read_text(encoding="utf-8", errors="replace"):
            failures.append(f"{rel}: missing `{needle}`")

    if failures:
        print("WORKFLOW_PROGRESS_10X_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("WORKFLOW_PROGRESS_10X_PASS")
    print(f"  subprocess gates: {len(SUBPROCESS_SCRIPTS)}")
    print(f"  static markers: {len(STATIC_MARKERS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
