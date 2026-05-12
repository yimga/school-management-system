#!/usr/bin/env python3
"""
Wave 1: Migrate orphan templates from `extends "base.html"` to a role-appropriate base.

Classification map below was hand-curated from the audit. Each path is relative to
templates/.  Templates not listed remain on base.html (they are pre-auth / public /
error / system pages where base.html is correct).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PORTAL = "portal_base.html"   # authenticated user portal (teachers, parents, staff)
BACKEND = "backend_base.html"  # school admin operational chrome
CONTROL_PLANE = "control_plane_base.html"  # platform operator chrome

# Map: template path (relative to templates/) -> new base
TARGETS: dict[str, str] = {
    # --- portal_base (authenticated, user-facing daily ops) ---
    "accounts/delegation_catch_up.html": PORTAL,
    "accounts/delegation_form.html": PORTAL,
    "accounts/direct_compose.html": PORTAL,
    "accounts/messages.html": PORTAL,
    "accounts/mfa_setup.html": PORTAL,
    "accounts/my_delegations.html": PORTAL,
    "accounts/password_change_done.html": PORTAL,
    "accounts/password_change_form.html": PORTAL,
    "accounts/profile.html": PORTAL,
    "accounts/profile_edit.html": PORTAL,
    "accounts/sessions_page.html": PORTAL,
    "academics/syllabus_builder.html": PORTAL,
    "academics/syllabus_clone.html": PORTAL,
    "academics/syllabus_preview.html": PORTAL,
    "academics/syllabus_upload.html": PORTAL,
    "academics/teacher_syllabus_hub.html": PORTAL,
    "portal/faq_detail.html": PORTAL,
    "portal/faq_list.html": PORTAL,
    "portal/faq_submit.html": PORTAL,
    "portal/kb_article_submit.html": PORTAL,
    "portal/user_contributions.html": PORTAL,
    "schools/demo_flow_attendance.html": PORTAL,
    "schools/demo_flow_complete.html": PORTAL,
    "schools/demo_flow_marks.html": PORTAL,
    "schools/demo_flow_report.html": PORTAL,

    # --- backend_base (school admin / principal / compliance officer ops) ---
    "academics/syllabus_approval_queue.html": BACKEND,
    "compliance/anomaly_detection.html": BACKEND,
    "compliance/audit_trail_report.html": BACKEND,
    "compliance/data_access_report.html": BACKEND,
    "compliance/data_rights_queue.html": BACKEND,
    "compliance/dashboard.html": BACKEND,
    "compliance/ferpa_disclosure_detail.html": BACKEND,
    "compliance/integrity_check_report.html": BACKEND,
    "compliance/permission_overview.html": BACKEND,
    "evals/audit_trail.html": BACKEND,
    "evals/compliance_dashboard.html": BACKEND,
    "evals/extend_deadline.html": BACKEND,
    "evals/grade_import_upload_v2.html": BACKEND,
    "evals/import_job_monitor.html": BACKEND,
    "evals/resolve_offline_conflict.html": BACKEND,
    "marketplace/publisher_app_detail.html": BACKEND,
    "marketplace/publisher_dashboard.html": BACKEND,
    "schools/activation_first_action.html": BACKEND,

    # --- control_plane_base (platform operator surfaces) ---
    "platform_runtime/tenant_blueprint_setup.html": CONTROL_PLANE,
    "platform_runtime/tenant_pack_setup.html": CONTROL_PLANE,
    "platform_runtime/school_configuration_center.html": CONTROL_PLANE,
}

# Regex matches  {% extends "base.html" %}  with single or double quotes,
# any inner whitespace, and the optional leading % tag style.
EXTENDS_RE = re.compile(
    r"""(\{%\s*extends\s+)(["'])base\.html(["'])(\s*%\})""",
    re.MULTILINE,
)


def migrate(root: Path) -> int:
    templates_dir = root / "templates"
    if not templates_dir.is_dir():
        print(f"error: templates dir not found: {templates_dir}", file=sys.stderr)
        return 1

    fixed = 0
    missed = 0
    skipped_no_extends = 0
    for rel, new_base in TARGETS.items():
        path = templates_dir / rel
        if not path.is_file():
            print(f"MISSING: {rel}")
            missed += 1
            continue
        original = path.read_text(encoding="utf-8")
        new_text, n = EXTENDS_RE.subn(
            lambda m: f'{m.group(1)}{m.group(2)}{new_base}{m.group(3)}{m.group(4)}',
            original,
            count=1,
        )
        if n == 0:
            print(f"NO-EXTENDS: {rel} (already migrated or different syntax)")
            skipped_no_extends += 1
            continue
        path.write_text(new_text, encoding="utf-8")
        print(f"  {rel}  ->  {new_base}")
        fixed += 1

    print(f"\nMigrated: {fixed}; missing: {missed}; no-extends: {skipped_no_extends}; total in map: {len(TARGETS)}")
    return 0 if missed == 0 and skipped_no_extends == 0 else 0  # informational


if __name__ == "__main__":
    project_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    raise SystemExit(migrate(project_root))
