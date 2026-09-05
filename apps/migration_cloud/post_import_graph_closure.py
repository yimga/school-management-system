"""Full import graph closure: placement → enrollment → teaching grid.

Single entry point for UI, CLI, autopilot, and post-retag re-import so operators
never depend on a second manual "connect" step.
"""
from __future__ import annotations

from typing import Any, Optional

from apps.migration_cloud.enrollment_sync import sync_all_enrollments_for_school
from apps.migration_cloud.student_placement_backfill import (
    backfill_student_classrooms_for_school,
)
from apps.migration_cloud.teaching_graph import ensure_teaching_graph_closure


def run_post_import_graph_closure(
    school,
    *,
    bundle=None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Place students, sync enrollments, then provision the teaching graph."""
    if school is None:
        return {"skipped": True, "reason": "no_school"}

    classrooms = backfill_student_classrooms_for_school(school, dry_run=dry_run)
    enrollments = sync_all_enrollments_for_school(school, dry_run=dry_run)
    graph = ensure_teaching_graph_closure(school, dry_run=dry_run)

    outcome: dict[str, Any] = {
        "classroom_backfill": classrooms,
        "enrollment_sync": enrollments,
        "teaching_graph": graph,
    }

    if bundle is not None and not dry_run:
        summary = dict(getattr(bundle, "mapping_summary", None) or {})
        summary["post_import_graph_closure"] = outcome
        bundle.mapping_summary = summary
        bundle.save(update_fields=["mapping_summary", "updated_at"])

    return outcome
