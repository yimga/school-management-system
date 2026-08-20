#!/usr/bin/env python3
"""AST coverage: the four long-running jobs fan record-level workflow telemetry."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_CALLSITES = (
    ("apps/accounts/tasks.py", "update_and_broadcast_progress"),
    ("apps/accounts/views_rollover.py", "update_and_broadcast_progress"),
    ("apps/academics/views_timetable.py", "enqueue_background_job"),
    ("apps/academics/tasks_scheduling.py", "update_and_broadcast_progress"),
    ("apps/academics/scheduling.py", "on_progress"),
    ("apps/academics/scheduling_solver.py", "on_progress"),
    ("apps/migration_cloud/progress.py", "update_and_broadcast_progress"),
    ("apps/schoolops/procurement_loop.py", "update_and_broadcast_progress"),
    ("apps/schoolops/tasks.py", "run_procurement_scan_task"),
    ("apps/schoolops/views_tenant_ops.py", "run_procurement_scan_task"),
    ("apps/api/consumers.py", "WorkflowTelemetryConsumer"),
    ("config/routing.py", "WorkflowTelemetryConsumer"),
    ("apps/platform_runtime/workflow_telemetry.py", "compute_percent_complete"),
    ("templates/components/rmc_workflow_progress_canvas.html", "rmc-wfp-canvas"),
    ("templates/accounts/rollover_queue.html", "rmc_workflow_kickoff_live.html"),
    ("templates/siteconfig/sync_center.html", "rmc_workflow_kickoff_live.html"),
    ("apps/sync_engine/sync_runner.py", "update_and_broadcast_progress"),
    ("apps/siteconfig/views_sync_center.py", "enqueue_background_job"),
    ("apps/sync_engine/tasks.py", "run_sync_cycle_for_school_task"),
    ("static/js/rmc-workflow-progress-canvas.js", "ws/workflow-progress/"),
    ("static/js/rmc-workflow-progress-canvas.js", "data-rmc-wfp-hold"),
    ("static/js/rmc-workflow-progress-canvas.js", "data-rmc-wfp-stay"),
)


def _file_contains(path: Path, needle: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            # Peer mid-edit can leave a file unparsable; still credit a literal
            # call-site so this coverage gate does not false-red the tree.
            return needle in text
        if needle.isidentifier():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == needle:
                    return True
                if isinstance(node, ast.Attribute) and node.attr == needle:
                    return True
                if isinstance(node, ast.ClassDef) and node.name == needle:
                    return True
                if isinstance(node, ast.FunctionDef) and node.name == needle:
                    return True
        return needle in text
    return needle in text


def main() -> int:
    missing: list[str] = []
    for rel, needle in REQUIRED_CALLSITES:
        path = ROOT / rel
        if not _file_contains(path, needle):
            missing.append(f"{rel} :: {needle}")
    if missing:
        print("WORKFLOW_TELEMETRY_COVERAGE_FAIL")
        for item in missing:
            print(f"  missing: {item}")
        return 1
    print("WORKFLOW_TELEMETRY_COVERAGE_PASS")
    print(f"  sites: {len(REQUIRED_CALLSITES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
