#!/usr/bin/env python3
"""Merge premium_platform_layout extras into platform-*.json (run once from repo root)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "config" / "marketing_content"

PATCHES: dict[str, dict] = {
    "platform-student-information-system": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1503676260728-1c00da094a0b?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Students collaborating in a bright classroom setting",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Student data scattered across spreadsheets and folders",
            "body": "When profiles, guardians, and academic history live in different places, teams duplicate work and visibility breaks down. RunMyCampus keeps one governed student record that admissions, academics, finance, and portals share.",
        },
        "workflow_steps": [
            "Enroll",
            "Assign classes",
            "Link guardians",
            "Sync attendance & grades",
            "Publish reports",
            "Share with families",
        ],
        "benefits_by_role": [
            {
                "role": "Administrators",
                "bullets": [
                    "Fewer reconciliation loops across departments",
                    "Configurable structures for programs and campuses",
                ],
            },
            {
                "role": "Teachers",
                "bullets": [
                    "Class lists and notes with appropriate visibility",
                    "Less time hunting for student context",
                ],
            },
            {
                "role": "Parents",
                "bullets": [
                    "One place to understand fees, attendance, and progress",
                    "Mobile-friendly access aligned to school branding",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Admissions & Enrollment", "path": "/platform/admissions/"},
            {"label": "Fees & Payments", "path": "/platform/fees-payments/"},
            {"label": "Grading & Report Cards", "path": "/platform/grading-report-cards/"},
            {"label": "Attendance", "path": "/platform/attendance/"},
        ],
    },
    "platform-admissions": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Staff reviewing enrollment paperwork at a school reception desk",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Pipeline blind spots slow enrollment",
            "body": "Without a connected admissions workflow, inquiries stall, documents scatter, and leadership lacks conversion clarity. RunMyCampus ties inquiry through enrollment to billing and class placement.",
        },
        "workflow_steps": [
            "Inquiry",
            "Application",
            "Documents",
            "Review",
            "Decision",
            "Enrollment",
            "Invoice",
            "Class placement",
        ],
        "benefits_by_role": [
            {
                "role": "Admissions teams",
                "bullets": [
                    "Stage ownership with SLAs and checklists",
                    "Families submit once and stay informed",
                ],
            },
            {
                "role": "Leadership",
                "bullets": [
                    "Visibility across campuses without manual rollups",
                    "Forecast-ready funnel signals",
                ],
            },
            {
                "role": "Finance",
                "bullets": [
                    "Clean hand-off from acceptance to billing",
                    "Fewer disputed balances at start of term",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Student Information System", "path": "/platform/student-information-system/"},
            {"label": "Communications", "path": "/platform/communications/"},
            {"label": "Fees & Payments", "path": "/platform/fees-payments/"},
            {"label": "Workflows", "path": "/platform/workflows/"},
        ],
    },
    "platform-attendance": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1427504494785-c39cd536d887?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Teacher engaging students during class",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Registers that do not reach families fast enough",
            "body": "Paper registers and disconnected apps delay visibility for parents and leaders. RunMyCampus captures attendance with audit-friendly history—online or offline—and reflects it where stakeholders already work.",
        },
        "workflow_steps": [
            "Teacher marks roll",
            "Late/absence tracked",
            "Parent visibility",
            "Admin monitors trends",
            "Reports exported",
        ],
        "benefits_by_role": [
            {
                "role": "Teachers",
                "bullets": [
                    "Fast class attendance with familiar workflows",
                    "Offline-ready capture where connectivity dips",
                ],
            },
            {
                "role": "Administrators",
                "bullets": [
                    "Campus-wide attendance posture without chasing sheets",
                    "Consistent patterns for interventions",
                ],
            },
            {
                "role": "Parents",
                "bullets": [
                    "Timely visibility into attendance patterns",
                    "Aligned with announcements and fees context",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Teacher Portal", "path": "/platform/teacher-portal/"},
            {"label": "Parent Portal", "path": "/platform/parent-portal/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
            {"label": "Offline-first", "path": "/platform/offline-first/"},
        ],
    },
    "platform-fees-payments": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Finance professional reviewing figures on a laptop",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Billing confusion strains trust",
            "body": "When invoices, receipts, and balances are fragmented, finance teams reconcile manually and parents call for the same answers. RunMyCampus brings fee setup, invoicing, receipts, and arrears into one auditable flow.",
        },
        "workflow_steps": [
            "Fee setup",
            "Invoice issued",
            "Payment recorded",
            "Receipt generated",
            "Balance updated",
            "Finance reports",
        ],
        "benefits_by_role": [
            {
                "role": "Finance teams",
                "bullets": [
                    "Structured arrears and discount handling",
                    "Payment history schools can defend in audits",
                ],
            },
            {
                "role": "Administrators",
                "bullets": [
                    "Operational clarity across campuses",
                    "Configurable currencies and fee categories",
                ],
            },
            {
                "role": "Parents",
                "bullets": [
                    "Transparent balances and receipts",
                    "Fewer surprise bills at renewal time",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Parent Portal", "path": "/platform/parent-portal/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
            {"label": "Student Information System", "path": "/platform/student-information-system/"},
            {"label": "Workflows", "path": "/platform/workflows/"},
        ],
    },
    "platform-grading-report-cards": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Books and study materials representing assessment",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Marks trapped in spreadsheets miss governance",
            "body": "Disconnected gradebooks make approvals messy and delay parent-ready reporting. RunMyCampus connects marks entry, grading scales, approvals, and published report cards.",
        },
        "workflow_steps": [
            "Marks entry",
            "Moderation",
            "Approval",
            "Report generation",
            "Publish",
            "Parent access",
        ],
        "benefits_by_role": [
            {
                "role": "Teachers",
                "bullets": [
                    "Structured scales aligned to your academic model",
                    "Comments and outcomes in one workspace",
                ],
            },
            {
                "role": "Leadership",
                "bullets": [
                    "Confidence before publish with approval rails",
                    "Performance visibility across cohorts",
                ],
            },
            {
                "role": "Parents",
                "bullets": [
                    "Official report cards in the portal",
                    "Consistent narrative alongside attendance and fees",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Teacher Portal", "path": "/platform/teacher-portal/"},
            {"label": "Parent Portal", "path": "/platform/parent-portal/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
            {"label": "Student Portal", "path": "/platform/student-portal/"},
        ],
    },
    "platform-parent-portal": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1516321497597-700fd17563d7?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Adult using a smartphone in a calm home environment",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Families deserve one coherent channel",
            "body": "When updates arrive through fragmented chats and PDFs, engagement drops. RunMyCampus concentrates fees, attendance, grades, announcements, and messages into a portal tuned for busy parents.",
        },
        "workflow_steps": [
            "School publishes update",
            "Parent notified",
            "Self-service views",
            "Action on fees/forms",
            "History retained",
        ],
        "benefits_by_role": [
            {
                "role": "Parents & guardians",
                "bullets": [
                    "Mobile-friendly clarity without chasing admin",
                    "Aligned messaging alongside billing truth",
                ],
            },
            {
                "role": "Administrators",
                "bullets": [
                    "Fewer repetitive inquiries",
                    "Delivery targeting by cohort or campus",
                ],
            },
            {
                "role": "Teachers",
                "bullets": [
                    "Share class-level context responsibly",
                    "Reduce duplicate outreach channels",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Communications", "path": "/platform/communications/"},
            {"label": "Fees & Payments", "path": "/platform/fees-payments/"},
            {"label": "Student Portal", "path": "/platform/student-portal/"},
            {"label": "Attendance", "path": "/platform/attendance/"},
        ],
    },
    "platform-teacher-portal": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1497633764215-c864088fc966?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Educator preparing materials at a desk with a laptop",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Teachers need one daily workspace",
            "body": "Switching tools for attendance, marks, assignments, and communication burns time. RunMyCampus centralizes classroom operations with role-aware visibility.",
        },
        "workflow_steps": [
            "Plan lesson",
            "Take attendance",
            "Capture marks",
            "Assign work",
            "Message families",
            "Report progress",
        ],
        "benefits_by_role": [
            {
                "role": "Teachers",
                "bullets": [
                    "Fewer disconnected tabs during class prep",
                    "Notes and outreach aligned to students",
                ],
            },
            {
                "role": "Leadership",
                "bullets": [
                    "Operational visibility without micromanagement",
                    "Consistent adoption across campuses",
                ],
            },
            {
                "role": "Parents",
                "bullets": [
                    "Updates originate from the same system of record",
                    "Less conflicting information across channels",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Attendance", "path": "/platform/attendance/"},
            {"label": "Grading & Report Cards", "path": "/platform/grading-report-cards/"},
            {"label": "Communications", "path": "/platform/communications/"},
            {"label": "Workflows", "path": "/platform/workflows/"},
        ],
    },
    "platform-student-portal": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1523580846011-d3a172bcabd9?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Student working on coursework with a laptop",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Students should see school life clearly",
            "body": "Opaque schedules and scattered assignment notices hurt accountability. RunMyCampus gives learners timetables, tasks, results, and announcements in one portal.",
        },
        "workflow_steps": [
            "Publish timetable",
            "Assign coursework",
            "Release results",
            "Announce updates",
            "Track engagement",
        ],
        "benefits_by_role": [
            {
                "role": "Students",
                "bullets": [
                    "Predictable place for deadlines and grades",
                    "Better readiness for parent conversations",
                ],
            },
            {
                "role": "Teachers",
                "bullets": [
                    "Assignments appear where students already look",
                    "Less chasing via unofficial channels",
                ],
            },
            {
                "role": "Administrators",
                "bullets": [
                    "Guardrails on what learners can see",
                    "Operational continuity across divisions",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Parent Portal", "path": "/platform/parent-portal/"},
            {"label": "Teacher Portal", "path": "/platform/teacher-portal/"},
            {"label": "Communications", "path": "/platform/communications/"},
            {"label": "Grading & Report Cards", "path": "/platform/grading-report-cards/"},
        ],
    },
    "platform-communications": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1533750516457-a7bb904ebb62?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Hands typing on a laptop representing messaging workflows",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Announcements should reach the right audience",
            "body": "Broadcast-only tools miss nuance; chat threads lose governance. RunMyCampus combines targeting, templates, and history so communications stay accountable.",
        },
        "workflow_steps": [
            "Compose message",
            "Target audience",
            "Schedule/send",
            "Track delivery context",
            "Archive & audit",
        ],
        "benefits_by_role": [
            {
                "role": "Administrators",
                "bullets": [
                    "School-wide or segmented broadcasting",
                    "Consistent tone through templates",
                ],
            },
            {
                "role": "Teachers",
                "bullets": [
                    "Class-scoped updates without leaking data",
                    "Shared operational narrative with leadership",
                ],
            },
            {
                "role": "Families",
                "bullets": [
                    "Fewer missed signals across portals",
                    "Transparency aligned with billing and academics",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Parent Portal", "path": "/platform/parent-portal/"},
            {"label": "Workflows", "path": "/platform/workflows/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
            {"label": "Security & Governance", "path": "/platform/security/"},
        ],
    },
    "platform-workflows": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Team collaborating around a laptop in an office setting",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Manual routing hides delays",
            "body": "Approvals trapped in email chains break SLAs. RunMyCampus routes admissions, finance, academic, and publishing tasks with notifications and trails.",
        },
        "workflow_steps": [
            "Define stages",
            "Assign owners",
            "Automate hand-offs",
            "Notify stakeholders",
            "Audit outcomes",
        ],
        "benefits_by_role": [
            {
                "role": "Leadership",
                "bullets": [
                    "Predictable throughput across campuses",
                    "Evidence for governance conversations",
                ],
            },
            {
                "role": "Operators",
                "bullets": [
                    "Queues instead of inbox archaeology",
                    "Less rework when roles change",
                ],
            },
            {
                "role": "Finance & admissions",
                "bullets": [
                    "Aligned checkpoints before money moves",
                    "Cleaner transitions between teams",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Admissions & Enrollment", "path": "/platform/admissions/"},
            {"label": "Fees & Payments", "path": "/platform/fees-payments/"},
            {"label": "Security & Governance", "path": "/platform/security/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
        ],
    },
    "platform-offline-first": {
        "premium_platform_layout": True,
        "suppress_footer_clusters": True,
        "stock_photo_url": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Mobile devices representing resilient connectivity",
        "stock_photo_credit": "Photo via Unsplash",
        "problem_section": {
            "title": "Connectivity should not halt school operations",
            "body": "Attendance and capture moments happen everywhere—from buses to rural campuses. RunMyCampus queues work offline and reconciles with governance when connections return.",
        },
        "workflow_steps": [
            "Capture offline",
            "Queue securely",
            "Reconnect",
            "Sync",
            "Review conflicts",
            "Retain audit trail",
        ],
        "benefits_by_role": [
            {
                "role": "Teachers",
                "bullets": [
                    "Keep marking attendance without guessing later",
                    "Less stress during outages",
                ],
            },
            {
                "role": "Finance",
                "bullets": [
                    "Receipt capture that survives sketchy networks",
                    "Traceable reconciliation windows",
                ],
            },
            {
                "role": "Leadership",
                "bullets": [
                    "Operational resilience as a design choice",
                    "Not a regional compromise story",
                ],
            },
        ],
        "related_platform_links": [
            {"label": "Attendance", "path": "/platform/attendance/"},
            {"label": "Security & Governance", "path": "/platform/security/"},
            {"label": "Teacher Portal", "path": "/platform/teacher-portal/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
        ],
    },
}


def main() -> None:
    for slug, patch in PATCHES.items():
        path = ROOT / f"{slug}.json"
        if not path.is_file():
            raise SystemExit(f"missing {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        extras = data.setdefault("extras", {})
        extras.update(patch)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("updated", path.name)


if __name__ == "__main__":
    main()
