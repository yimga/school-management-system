#!/usr/bin/env python3
"""Gate: all four Workflow Progress 10x waves — artifacts, wiring, URLs, registry."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WAVE_MARKERS: dict[str, tuple[str, ...]] = {
    "wave1_coverage": (
        "apps/platform_runtime/workflow_celery_bridge.py",
        "apps/platform_runtime/celery_task_events.py",
        "apps/platform_runtime/workflow_request_middleware.py",
        "apps/platform_runtime/workflow_tracker.py",
        "scripts/verify_workflow_progress_coverage.py",
    ),
    "wave2_autopilot": (
        "apps/platform_runtime/models_workflow_10x.py",
        "apps/platform_runtime/workflow_autopilot.py",
        "apps/platform_runtime/workflow_fix_handlers.py",
        "apps/platform_runtime/views_workflow_autopilot.py",
        "apps/platform_runtime/migrations/0079_workflow_10x_models.py",
    ),
    "wave3_flight_deck": (
        "apps/platform_runtime/views_workflow_flight_deck.py",
        "apps/platform_runtime/workflow_degrading.py",
        "apps/platform_runtime/workflow_duration_stats.py",
        "templates/platform_runtime/workflow_flight_deck.html",
        "static/js/rmc-workflow-flight-deck.js",
        "static/css/rmc-workflow-flight-deck.css",
        "apps/schools/control_plane_nav.py",
        "apps/platform_runtime/super_operational_frames.py",
    ),
    "wave4_trust_sla": (
        "apps/platform_runtime/workflow_tenant_trust.py",
        "apps/platform_runtime/workflow_incidents.py",
        "apps/platform_runtime/workflow_sla.py",
        "apps/platform_runtime/views_workflow_trust.py",
        "templates/components/rmc_workflow_tenant_trust_strip.html",
        "static/js/rmc-workflow-tenant-trust.js",
    ),
}

WAVE_CONTENT_MARKERS: dict[str, tuple[tuple[str, str], ...]] = {
    "wave1_coverage": (
        ("apps/platform_runtime/workflow_celery_bridge.py", "_CELERY_WORKFLOW_KEY_OVERRIDES"),
        ("config/settings.py", "WorkflowProgressRequestMiddleware"),
        ("templates/control_plane_skeleton.html", "rmc-workflow-track-headers.js"),
        ("templates/portal_base.html", "rmc-workflow-progress.js"),
        ("apps/platform_runtime/apps.py", "register_workflow_progress_assist_dock_slot"),
    ),
    "wave2_autopilot": (
        ("apps/platform_runtime/workflow_tracker.py", "try_auto_apply_on_failure"),
        ("apps/platform_runtime/admin.py", "WorkflowAutopilotPolicy"),
        ("apps/platform_runtime/admin.py", "WorkflowDurationStat"),
        ("apps/platform_runtime/models.py", "WorkflowSlaBreach"),
        ("apps/platform_runtime/migrations/0079_workflow_10x_models.py", "WorkflowAutopilotPolicy"),
        ("apps/platform_runtime/workflow_fix_handlers.py", "preview_auto_fix_kind"),
        ("apps/platform_runtime/views_workflow_progress.py", "_request_dry_run"),
        ("static/js/rmc-workflow-progress.js", "preview-fix"),
    ),
    "wave3_flight_deck": (
        ("apps/schools/control_plane_nav.py", "super_workflow_flight_deck"),
        ("apps/platform_runtime/super_operational_frames.py", "WORKFLOW_FLIGHT_DECK_NAV"),
        ("static/js/rmc-copilot-context-lens.js", "rmc-workflow-copilot-context"),
        ("static/js/rmc-workflow-flight-deck.js", "rmc-workflow-copilot-context"),
        ("templates/components/rmc_workflow_progress_strip.html", "page-data-rmc-workflow-flight-deck"),
        ("static/js/rmc-workflow-progress.js", "flightDeckPageUrl"),
    ),
    "wave4_trust_sla": (
        ("templates/portal_base.html", "rmc_workflow_tenant_trust_strip.html"),
        ("apps/platform_runtime/workflow_registry.py", "slo_seconds"),
        ("apps/platform_runtime/workflow_tracker.py", "maybe_record_sla_breach"),
        ("apps/platform_runtime/workflow_sla.py", "workflow.sla.breached"),
        ("apps/platform_runtime/events.py", "workflow.sla.breached"),
        ("templates/emails/operator_workflow_sla_breached.txt", "SLA exceeded"),
        ("apps/platform_runtime/tasks.py", "workflow_sla_breach_alert_sweep"),
        ("static/js/rmc-workflow-tenant-trust.js", "tenant-trusted/active"),
        ("config/settings.py", "platform-runtime-workflow-sla-breach-sweep"),
    ),
}

BUS_URL_NAMES = (
    "platform_runtime:workflow_progress_active_runs",
    "platform_runtime:workflow_progress_stream",
    "platform_runtime:workflow_progress_apply_fix",
    "platform_runtime:workflow_progress_cancel",
)

WAVE10X_URL_NAMES = (
    "platform_runtime:workflow_progress_flight_deck",
    "platform_runtime:workflow_progress_flight_deck_json",
    "platform_runtime:workflow_progress_tenant_trusted_active",
    "platform_runtime:workflow_progress_tenant_trusted_stream",
    "platform_runtime:workflow_progress_enable_autopilot",
    "platform_runtime:workflow_progress_autopilot_policy",
)

LIFECYCLE_SLO_KEYS = (
    "tenant_school_provision",
    "tenant_school_purge",
    "migration_bundle_apply",
    "migration_bundle_advance",
    "evals_bulk_grades",
    "finance_auto_generate_fee_invoices",
    "marketplace_webhook_deliver_due",
    "orchestration_process_due",
    "tenant_school_offboard_purge",
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []
    wave_ok: dict[str, bool] = {w: True for w in WAVE_MARKERS}

    for wave, paths in WAVE_MARKERS.items():
        for rel in paths:
            if not (ROOT / rel).is_file():
                failures.append(f"{wave}: missing file {rel}")
                wave_ok[wave] = False

    for wave, markers in WAVE_CONTENT_MARKERS.items():
        for rel, needle in markers:
            path = ROOT / rel
            if not path.is_file():
                failures.append(f"{wave}: missing file {rel} (content check)")
                wave_ok[wave] = False
                continue
            if needle not in _read(rel):
                failures.append(f"{wave}: {rel} missing `{needle}`")
                wave_ok[wave] = False

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from django.apps import apps as django_apps
    from django.db.migrations.loader import MigrationLoader
    from django.urls import reverse

    loader = MigrationLoader(None, ignore_no_migrations=False)
    if ("platform_runtime", "0079_workflow_10x_models") not in loader.graph.nodes:
        failures.append("wave2: migration 0079_workflow_10x_models not in graph")
        wave_ok["wave2_autopilot"] = False

    for model_label in (
        "platform_runtime.WorkflowAutopilotPolicy",
        "platform_runtime.WorkflowAutopilotApplyLog",
        "platform_runtime.WorkflowDurationStat",
        "platform_runtime.WorkflowSlaBreach",
    ):
        try:
            django_apps.get_model(model_label)
        except LookupError:
            failures.append(f"wave2: model not registered — {model_label}")
            wave_ok["wave2_autopilot"] = False

    from apps.platform_runtime.workflow_registry import WORKFLOWS

    keys = list(WORKFLOWS.keys())
    if len(keys) != len(set(keys)):
        failures.append("wave4: duplicate keys in WORKFLOWS dict")
        wave_ok["wave4_trust_sla"] = False

    missing_slo = [
        k for k in LIFECYCLE_SLO_KEYS
        if k in WORKFLOWS and not getattr(WORKFLOWS[k], "slo_seconds", None)
    ]
    if missing_slo:
        failures.append(f"wave4: lifecycle workflows missing slo_seconds: {missing_slo}")
        wave_ok["wave4_trust_sla"] = False

    slo_count = sum(1 for w in WORKFLOWS.values() if getattr(w, "slo_seconds", None))
    if slo_count < 8:
        failures.append(f"wave4: registry has {slo_count} slo_seconds (< 8)")
        wave_ok["wave4_trust_sla"] = False

    url_kwargs = {
        "platform_runtime:workflow_progress_apply_fix": {"run_id": 1},
        "platform_runtime:workflow_progress_cancel": {"run_id": 1},
    }

    for name in (*BUS_URL_NAMES, *WAVE10X_URL_NAMES):
        try:
            reverse(name, kwargs=url_kwargs.get(name))
        except Exception as exc:
            failures.append(f"url: {name} — {exc}")
            if name in WAVE10X_URL_NAMES:
                for wave in ("wave2_autopilot", "wave3_flight_deck", "wave4_trust_sla"):
                    if "autopilot" in name and wave == "wave2_autopilot":
                        wave_ok[wave] = False
                    elif "flight" in name and wave == "wave3_flight_deck":
                        wave_ok[wave] = False
                    elif "tenant" in name and wave == "wave4_trust_sla":
                        wave_ok[wave] = False
            else:
                wave_ok["wave1_coverage"] = False

    sw = _read("static/js/service-worker.js")
    if 'const CACHE_VERSION = "sms-v' not in sw:
        failures.append("wave1: service-worker missing sms-v CACHE_VERSION")
        wave_ok["wave1_coverage"] = False

    if failures:
        print("WORKFLOW_10X_WAVES_COMPLETE_FAIL")
        for wave, ok in wave_ok.items():
            print(f"  [{('PASS' if ok else 'FAIL')}] {wave}")
        for line in failures:
            print(f"  - {line}")
        return 1

    print("WORKFLOW_10X_WAVES_COMPLETE_PASS")
    for wave in WAVE_MARKERS:
        files_n = len(WAVE_MARKERS[wave])
        content_n = len(WAVE_CONTENT_MARKERS.get(wave, ()))
        print(f"  [PASS] {wave} ({files_n} files, {content_n} wiring markers)")
    print(f"  bus_urls: {len(BUS_URL_NAMES)}")
    print(f"  wave10x_urls: {len(WAVE10X_URL_NAMES)}")
    print(f"  lifecycle_slo_keys: {len(LIFECYCLE_SLO_KEYS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
