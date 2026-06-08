#!/usr/bin/env python3
"""
Verify Zero-Friction OS Phases 2–6 journey closures (repo-scope).

Checks shipped primitives for:
  Phase 2 — homework offline handler, attendance QR primary, parent 1-click pay
  Phase 3 — Studio OS overview workflow info chips
  Phase 4 — Copilot rail posture tier labels (health poll path)
  Phase 5 — Session school bind + middleware order evidence
  Phase 6 — Top-friction marks_list 5-column table contract

Run: python scripts/verify_zero_friction_journeys.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-subprocess-gates",
        action="store_true",
        help="Also run verify_middleware_stack_order.py and scan_tenant_queryset_safety --compare",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []

    offline_queue = _read("apps/platform_runtime/offline_queue.py")
    if "def _apply_homework_submission" not in offline_queue:
        errors.append("missing _apply_homework_submission in offline_queue.py")
    if "HOMEWORK_SUBMISSION" not in _read("apps/platform_runtime/models.py"):
        errors.append("missing OfflineAction.ActionType.HOMEWORK_SUBMISSION")

    bundle = _read("apps/platform_runtime/offline_mode_bundle.py")
    if "enable_offline_homework_sync" not in bundle:
        errors.append("missing enable_offline_homework_sync in offline_mode_bundle.py")

    surface = _read("apps/siteconfig/platform_surface_config.py")
    if "homeworkSyncEnabled" not in surface:
        errors.append("missing homeworkSyncEnabled in platform_surface_config.py")

    roll_call = _read("templates/portal/roll_call_student.html")
    if 'data-rmc-attendance-primary="qr"' not in roll_call:
        errors.append("roll_call_student.html missing data-rmc-attendance-primary=qr")

    finance = _read("templates/parent/finance.html")
    if 'data-rmc-one-click-pay="1"' not in finance:
        errors.append("parent/finance.html missing data-rmc-one-click-pay")

    overview = _read("templates/studio_os/partials/overview_command_cockpit.html")
    if "rmc-workflow-info-chip" not in overview:
        errors.append("overview_command_cockpit.html missing workflow info chips")

    copilot_js = _read("static/js/rmc-copilot-rail.js")
    if "live_cloud" not in copilot_js or "renderPosture" not in copilot_js:
        errors.append("rmc-copilot-rail.js missing tier posture rendering")

    marks = _read("templates/teacher/marks_list.html")
    if 'data-rmc-table-5col="1"' not in marks:
        errors.append("teacher/marks_list.html missing 5-column table contract")

    for rel, needle in (
        ("templates/teacher/marks_entry.html", 'data-rmc-table-5col="1"'),
        ("templates/evals/evaluation_admin.html", 'data-rmc-table-5col="1"'),
        ("templates/evals/grade_approval_detail.html", 'data-rmc-table-5col="1"'),
        ("templates/parent/results.html", 'data-rmc-table-5col="1"'),
        ("templates/evals/grade_import_upload_v2.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/teacher/timetable.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/teacher/feed.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/teacher/dashboard.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/evals/compliance_dashboard.html", 'data-rmc-table-5col="1"'),
        ("templates/evals/resolve_offline_conflict.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/evals/audit_trail.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/portal/partials/document_library_manage_inner.html", 'data-rmc-table-5col="1"'),
        ("templates/schoolops/super/email_health.html", 'data-rmc-table-5col="1"'),
        ("templates/schoolops/super/signup_diagnostics.html", 'data-rmc-table-5col="1"'),
        ("templates/evals/grade_approval_list.html", 'data-rmc-table-5col="1"'),
        ("templates/portal/at_risk_labeling/queue.html", 'data-rmc-table-5col="1"'),
        ("templates/parent/finance.html", 'data-rmc-table-5col="1"'),
        ("templates/parent/wallet.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/evals/class_ranking.html", "data-rmc-row-detail-table"),
        ("templates/evals/evidence_upload.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/portal/signature_requests_manage.html", 'data-rmc-table-5col="1"'),
        ("templates/schoolops/ops_pos.html", 'data-rmc-table-5col="1"'),
        ("templates/portal/user_contributions.html", 'data-rmc-table-5col="1"'),
        ("templates/schoolops/ops_canteen.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/portal/roll_call_student.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/parent/feed.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/people/backend_classroom_list.html", 'data-rmc-table-5col="1"'),
        ("templates/people/employer_dashboard.html", "data-rmc-row-detail-table"),
        ("templates/portal/kb_docs_hub.html", "data-rmc-row-detail-table"),
        ("templates/portal/student_transcript_vault.html", "data-rmc-row-detail-table"),
        ("templates/accounts/my_delegations.html", 'data-rmc-table-5col="1"'),
        ("templates/schools/super_blueprints_catalog.html", "data-rmc-row-detail-table"),
        ("templates/schools/super_migration_cloud.html", "data-rmc-row-detail-table"),
        ("templates/schools/super_offboarding_queue.html", 'data-rmc-table-5col="1"'),
        ("templates/siteconfig/partials/tag_manager_body.html", "data-rmc-row-detail-table"),
        ("templates/siteconfig/partials/term_publish_status_evidence_body.html", 'data-rmc-table-5col="1"'),
        ("templates/finance/payments.html", "data-rmc-row-detail-table"),
        ("templates/finance/requests.html", 'data-rmc-table-5col="1"'),
        ("templates/finance/offline_payment_intent_queue.html", 'data-rmc-table-5col="1"'),
        ("templates/platform_runtime/pack_installations.html", "data-rmc-row-detail-table"),
        ("templates/platform_runtime/registry_health.html", "portal_row_detail_drawer_bundle.html"),
        ("templates/analytics/master_sheet.html", "table-column-budget-allow:"),
        ("templates/analytics/dashboard.html", "data-rmc-row-detail-table"),
        ("templates/analytics/at_risk_dashboard.html", 'data-rmc-table-5col="1"'),
        ("templates/analytics/deadlines.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/evals/school_ranking.html", "data-rmc-row-detail-table"),
        ("templates/accounts/backend_dashboard.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/accounts/certification_session_detail.html", "table-column-budget-allow:"),
        ("templates/accounts/migration_run_list.html", "portal_row_detail_drawer_bundle.html"),
        ("templates/migration_cloud/operator/webhook_audit.html", "table-column-budget-allow:"),
        ("templates/migration_cloud/operator/command_center.html", "data-rmc-row-detail-table"),
        ("templates/siteconfig/metadata_dynamic_fields_operator.html", "metadata-dynamic-fields-six-column-lens"),
        ("templates/siteconfig/grading_scale_bands.html", "portal_row_detail_drawer_bundle.html"),
        ("templates/social_media/proud_campus_feed.html", "data-rmc-social-feed"),
        ("templates/student360/student_360_page.html", "rmc-section-nav"),
        ("templates/teacher/leave.html", "next_action_strip"),
        ("templates/teacher/marks_entry.html", "next_action_strip"),
        ("templates/teacher/marks_list.html", "next_action_strip"),
        ("templates/teacher/timetable.html", "next_action_strip"),
        ("templates/teacher/attendance.html", "next_action_strip"),
        ("templates/teacher/leave.html", 'data-rmc-table-5col="1"'),
        ("templates/teacher/marks_entry.html", 'data-rmc-table-5col="1"'),
        ("templates/teacher/pay_history.html", "portal_row_detail_drawer_bundle.html"),
        ("templates/parent/dashboard.html", "next_action_strip"),
        ("templates/parent/finance.html", "next_action_strip"),
        ("templates/parent/results.html", "next_action_strip"),
        ("templates/parent/wallet.html", "next_action_strip"),
        ("templates/parent/attendance_discipline.html", 'data-rmc-table-5col="1"'),
        ("templates/parent/feed.html", 'data-rmc-scroll-policy="paginate"'),
        ("templates/accounts/backend_dashboard.html", "next_action_strip"),
        ("templates/people/backend_student_list.html", "next_action_strip"),
        ("templates/people/backend_student_list.html", "data-page-critical-read"),
        ("templates/people/backend_classroom_list.html", 'data-rmc-table-5col="1"'),
        ("templates/people/backend_teacher_list.html", "portal_row_detail_drawer_bundle.html"),
        ("templates/evals/evaluation_admin.html", "next_action_strip"),
        ("templates/evals/compliance_dashboard.html", "next_action_strip"),
        ("templates/evals/grade_approval_list.html", "next_action_strip"),
        ("templates/portal/kb_home.html", "next_action_strip"),
        ("templates/portal/support_help_hub.html", "next_action_strip"),
        ("templates/portal/unified_calendar.html", "next_action_strip"),
        ("templates/portal/at_risk_labeling/queue.html", "next_action_strip"),
        ("templates/portal/signature_requests_manage.html", "next_action_strip"),
        ("templates/portal/kb_home.html", "data-page-critical-read"),
        ("templates/evals/evaluation_admin.html", "data-page-critical-read"),
    ):
        if needle not in _read(rel):
            errors.append(f"{rel} missing {needle}")

    for path in (
        "apps/schools/session_school_bind.py",
        "apps/schools/middleware_session_school_bind.py",
    ):
        if not (ROOT / path).is_file():
            errors.append(f"missing session bind module: {path}")

    gap_register = _read("apps/schools/feature_gap_register.py")
    if 'feature_slug="zero-data-homework-buffer"' not in gap_register:
        errors.append("feature_gap_register missing zero-data-homework-buffer row")
    if 'status="shipped"' not in gap_register.split("zero-data-homework-buffer")[1][:400]:
        errors.append("zero-data-homework-buffer not marked shipped")

    portal_forms = _read("static/js/rmc-offline-portal-forms.js")
    if 'homework_submission' not in portal_forms:
        errors.append("rmc-offline-portal-forms.js missing homework_submission wiring")

    if errors:
        for err in errors:
            print(f"verify_zero_friction_journeys: {err}", file=sys.stderr)
        return 1

    if args.run_subprocess_gates:
        for cmd in (
            [sys.executable, str(ROOT / "scripts/verify_middleware_stack_order.py")],
            [
                sys.executable,
                str(ROOT / "scripts/scan_tenant_queryset_safety.py"),
                "--compare",
            ],
        ):
            rc = subprocess.call(cmd, cwd=str(ROOT))
            if rc != 0:
                return rc

    print("ZERO_FRICTION_JOURNEYS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
