#!/usr/bin/env python3
"""Glocal adoption — row-detail drawer on every operational rmc-data-table."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

EXCLUDE_REL = frozenset(
    {
        "templates/portal_base.html",
        "templates/control_plane_skeleton.html",
        "templates/admin/base_site.html",
        "templates/base.html",
        "templates/customersuccess/guided_onboarding.html",
        "templates/siteconfig/partials/reportcard_style_preview_body.html",
        "templates/admin/partials/admin_v1_index_surface_previews.html",
        "templates/partials/cockpit/_churn_scorecard.html",
        "templates/components/rmc_skeleton.html",
    }
)

CONFLICT_CARD_TARGETS: tuple[tuple[str, str], ...] = (
    ("templates/portal/offline_sync_conflicts.html", "offline_sync_conflicts"),
)

# Explicitly wired surfaces (manual title/meta) — must keep data-rmc-row-detail rows.
EXPLICIT_ROW_DETAIL_TARGETS: frozenset[str] = frozenset(
    {
        "templates/teacher/marks_entry.html",
        "templates/teacher/marks_list.html",
        "templates/teacher/attendance.html",
        "templates/teacher/pay_history.html",
        "templates/teacher/leave.html",
        "templates/teacher/timetable.html",
        "templates/parent/finance.html",
        "templates/parent/results.html",
        "templates/parent/attendance_discipline.html",
        "templates/parent/wallet.html",
        "templates/portal/roll_call_student.html",
        "templates/portal/roll_call_teacher.html",
        "templates/portal/cahier_list.html",
        "templates/portal/cahier_verify_list.html",
        "templates/portal/office_document_list.html",
        "templates/portal/partials/document_library_manage_inner.html",
        "templates/portal/user_contributions.html",
        "templates/portal/offline_sync_queue.html",
        "templates/portal/signature_requests_manage.html",
        "templates/portal/at_risk_labeling/queue.html",
        "templates/portal/configure/lexicon_settings.html",
        "templates/people/backend_student_list.html",
        "templates/people/backend_guardian_list.html",
        "templates/people/backend_teacher_list.html",
        "templates/people/backend_applicant_list.html",
        "templates/people/backend_classroom_list.html",
        "templates/accounts/tenant_identity_roster.html",
        "templates/finance/invoices.html",
        "templates/finance/global_payment_command_center.html",
        "templates/finance/offline_payment_intent_queue.html",
        "templates/finance/requests.html",
    }
)

CANVAS_ROLE_HOMES: tuple[tuple[str, str, str], ...] = (
    ("templates/teacher/dashboard.html", "canvas", "dashboard-page-teacher"),
    ("templates/parent/dashboard.html", "canvas", "dashboard-page-parent"),
)

ROLE_LITERAL = re.compile(
    r">\s*(Administrator|Headteacher|Teacher|Parent|Student)\s*<",
    re.IGNORECASE,
)

DRAWER_JS_MARKERS = (
    "portal_row_detail_drawer",
    "portal_row_detail_drawer_bundle",
    "rmc-portal-row-detail-drawer.js",
)

SHELL_EXTENDS_MARKERS = (
    'extends "base.html"',
    "extends 'base.html'",
    'extends "portal_base',
    "extends 'portal_base",
    'extends "control_plane_base',
    "extends 'control_plane_base",
    'extends "control_plane_skeleton',
    "extends 'control_plane_skeleton",
    'extends "backend_base',
    "extends 'backend_base",
    'extends "migration_cloud/connector/_wizard_base',
    "extends 'migration_cloud/connector/_wizard_base",
    'extends "marketing/base_marketing',
    "extends 'marketing/base_marketing",
)

IAM_LEXICON_MARKERS = (
    "glocal_token",
    "localized_role",
    "trans_term",
    '{% term "',
)


TABLE_WITH_RMC_RE = re.compile(r"<table\b[^>]*\brmc-data-table\b", re.IGNORECASE)


def _discover_drawer_targets() -> tuple[tuple[str, str], ...]:
    targets: list[tuple[str, str]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXCLUDE_REL:
            continue
        text = path.read_text(encoding="utf-8")
        if not TABLE_WITH_RMC_RE.search(text):
            continue
        label = path.stem
        targets.append((rel, label))
    return tuple(targets)


def _inherits_shell_drawer(text: str) -> bool:
    return any(marker in text for marker in SHELL_EXTENDS_MARKERS)


def _has_drawer_bundle(text: str) -> bool:
    return any(marker in text for marker in DRAWER_JS_MARKERS) or _inherits_shell_drawer(text)


def _table_row_detail_ok(text: str, rel: str) -> bool:
    if "data-rmc-row-detail-table" not in text:
        return False
    if rel in EXPLICIT_ROW_DETAIL_TARGETS:
        return 'data-rmc-row-detail="1"' in text or "data-rmc-row-detail='1'" in text
    return (
        'data-rmc-row-detail="1"' in text
        or "data-rmc-row-detail='1'" in text
        or 'data-rmc-row-detail-auto="1"' in text
    )


def _check_drawer_targets(targets: tuple[tuple[str, str], ...]) -> list[str]:
    findings: list[str] = []
    for rel, label in targets:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        is_partial = "/partials/" in rel
        if not is_partial and not _has_drawer_bundle(text):
            findings.append(f"{label}: missing row-detail drawer bundle")
        if not _table_row_detail_ok(text, rel):
            findings.append(f"{label}: rmc-data-table missing row-detail wiring")
    return findings


def _check_conflict_card_targets() -> list[str]:
    findings: list[str] = []
    for rel, label in CONFLICT_CARD_TARGETS:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if not _has_drawer_bundle(text):
            findings.append(f"{label}: missing row-detail drawer bundle")
        if 'data-rmc-row-detail-cards="1"' not in text:
            findings.append(f"{label}: missing data-rmc-row-detail-cards surface")
        if 'data-rmc-row-detail="1"' not in text:
            findings.append(f"{label}: missing data-rmc-row-detail cards")
    return findings


def _check_iam_targets(targets: tuple[tuple[str, str], ...]) -> list[str]:
    findings: list[str] = []
    vocab = ROOT / "apps/platform_runtime/glocal_vocabulary.py"
    tags = ROOT / "apps/platform_runtime/templatetags/glocal_tags.py"
    if not vocab.is_file() or not tags.is_file():
        findings.append("glocal vocabulary kernel missing")
    for rel, _label in targets:
        if "/partials/" in rel:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "glocal_tags" not in text:
            findings.append(f"{rel}: missing glocal_tags load")
        if ROLE_LITERAL.search(text) and not any(
            marker in text for marker in IAM_LEXICON_MARKERS
        ):
            findings.append(f"{rel}: hardcoded role label without glocal_token")
    return findings


def _check_canvas_role_homes() -> list[str]:
    findings: list[str] = []
    css = ROOT / "static/css/rmc-tenant-workspace-canvas.css"
    if not css.is_file():
        findings.append("missing rmc-tenant-workspace-canvas.css")
    for rel, policy, body_class in CANVAS_ROLE_HOMES:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if "body_scroll_policy" not in text or policy not in text:
            findings.append(f"{rel}: missing body_scroll_policy {policy}")
        if body_class not in text:
            findings.append(f"{rel}: missing {body_class}")
        if "rmc-tenant-workspace-canvas.css" not in text:
            findings.append(f"{rel}: missing workspace canvas stylesheet")
    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    if "body_scroll_policy" not in portal:
        findings.append("portal_base missing body_scroll_policy block")
    return findings


def main() -> int:
    drawer_targets = _discover_drawer_targets()
    findings: list[str] = []
    findings.extend(_check_drawer_targets(drawer_targets))
    findings.extend(_check_conflict_card_targets())
    findings.extend(_check_iam_targets(drawer_targets))
    findings.extend(_check_canvas_role_homes())

    if findings:
        print("verify_glocal_adoption_tranche: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_glocal_adoption_tranche: GLOCAL_ADOPTION_TRANCHE_PASS "
        f"({len(drawer_targets)} drawer tables, {len(CONFLICT_CARD_TARGETS)} card surfaces)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
