#!/usr/bin/env python3
"""Prove broker-up topology keeps a Celery worker + beat for provisioning heals.

When ``CELERY_BROKER_URL`` is set on the web service (Render blueprint), inline
web migrate is banned (batch 1781). Provisioning then REQUIRES:
  * a worker service that drains the broker
  * a beat service (or equivalent) that schedules stuck/failed/reconcile heals
  * the four heal tasks present in ``CELERY_BEAT_SCHEDULE``

This gate is static (stdlib + settings AST) — it does not ping live Render.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "render.yaml"
SETTINGS = ROOT / "config" / "settings.py"
TASKS = ROOT / "apps" / "schools" / "tasks.py"

REQUIRED_BEAT_TASK_FRAGMENTS = (
    "schools.resume_stuck_provisions",
    "schools.reconcile_half_provisioned_tenants",
    "platform_runtime.workflow_failed_provision_auto_requeue_sweep",
    "platform-runtime-workflow-stuck-sweep",
)


def _render_findings() -> list[str]:
    findings: list[str] = []
    if not RENDER.is_file():
        return ["render_yaml_missing"]
    text = RENDER.read_text(encoding="utf-8")
    # Web service wires broker from redis.
    web_has_broker = bool(
        re.search(
            r"CELERY_BROKER_URL[\s\S]{0,120}fromService:[\s\S]{0,80}redis",
            text,
        )
        or (
            "CELERY_BROKER_URL" in text
            and "school-management-system-worker" in text
        )
    )
    if not web_has_broker:
        # Broker-less topology is valid; no worker required.
        return findings
    if "name: school-management-system-worker" not in text:
        findings.append("render_missing_celery_worker_service")
    if "name: school-management-system-beat" not in text:
        findings.append("render_missing_celery_beat_service")
    if "celery -A config worker" not in text and "celery -A config  worker" not in text:
        if "celery -A config worker" not in text.replace("  ", " "):
            # startCommand line
            if not re.search(r"celery\s+-A\s+config\s+worker", text):
                findings.append("render_worker_start_command_missing")
    if not re.search(r"celery\s+-A\s+config\s+beat", text):
        findings.append("render_beat_start_command_missing")
    return findings


def _beat_schedule_findings() -> list[str]:
    findings: list[str] = []
    if not SETTINGS.is_file():
        return ["settings_missing"]
    text = SETTINGS.read_text(encoding="utf-8")
    if "CELERY_BEAT_SCHEDULE" not in text:
        return ["celery_beat_schedule_missing"]
    for frag in REQUIRED_BEAT_TASK_FRAGMENTS:
        if frag not in text:
            findings.append(f"beat_schedule_missing:{frag}")
    return findings


def _code_contract_findings() -> list[str]:
    findings: list[str] = []
    if not TASKS.is_file():
        return ["tasks_missing"]
    text = TASKS.read_text(encoding="utf-8")
    if "sync_deferred_to_worker" not in text:
        findings.append("complete_provisioning_missing_sync_deferred_to_worker")
    # Guard: queued path must not call provision_school_sync after dispatch success.
    # Heuristic: the function body after "sync_deferred_to_worker" should not
    # invoke provision_school_sync before the next top-level def.
    try:
        start = text.index("def complete_provisioning_for_school")
        end = text.index("\ndef kick_complete_provisioning_background", start)
        body = text[start:end]
    except ValueError:
        findings.append("complete_provisioning_body_unparseable")
        return findings
    if "sync_deferred_to_worker" not in body:
        findings.append("complete_provisioning_missing_defer_flag_in_body")
    # After setting defer flag, calling provision_school_sync would reintroduce SIGKILL risk.
    defer_idx = body.find("sync_deferred_to_worker")
    if defer_idx >= 0 and "provision_school_sync(" in body[defer_idx:]:
        findings.append("complete_provisioning_still_syncs_after_defer")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    findings = (
        _render_findings() + _beat_schedule_findings() + _code_contract_findings()
    )
    if findings:
        print(f"PROVISIONING_BROKER_TOPOLOGY_FAIL: {len(findings)} finding(s)")
        for row in findings:
            print(f"  - {row}")
        return 1
    print("PROVISIONING_BROKER_TOPOLOGY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
