"""
Premium layout fields merged into institution (solution segment) marketing pages.

Keeps INSTITUTION_LANDING_DEFINITIONS readable; paths match config/public_urls.py.
"""

from __future__ import annotations

INSTITUTION_PREMIUM_LAYER: dict[str, dict] = {
    "private-schools": {
        "problem_section": {
            "title": "Independent schools juggle admissions, advancement, and academics in disconnected tools",
            "body": "When enquiries, tuition, grading, and family communication live in separate systems, teams duplicate data and leadership loses a single operational picture. RunMyCampus connects those workflows with configurable calendars, currencies, and portals.",
        },
        "recommended_modules": [
            {"label": "Admissions", "path": "/platform/admissions/"},
            {"label": "Student Information System", "path": "/platform/student-information-system/"},
            {"label": "Fees & Payments", "path": "/platform/fees-payments/"},
            {"label": "Parent Portal", "path": "/platform/parent-portal/"},
            {"label": "Grading & Report Cards", "path": "/platform/grading-report-cards/"},
            {"label": "Communications", "path": "/platform/communications/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
        ],
        "stock_photo_static": "images/marketing/module-admissions.svg",
        "stock_photo_alt": "Stylized admissions workflow representing school staff welcoming families",
        "workflow_diagram_static": "images/marketing/module-admissions.svg",
        "global_config_note": "Academic calendars, grading scales, fee rules, portals, and branding configure per campus—built for schools worldwide without one-country assumptions.",
    },
    "international-schools": {
        "problem_section": {
            "title": "International cohorts need flexible curricula without fragmented operations",
            "body": "Multiple languages, diploma pathways, and mobile families amplify complexity when records and finance sit outside one governed core. RunMyCampus aligns admissions through billing with audit-ready visibility.",
        },
        "recommended_modules": [
            {"label": "Student Information System", "path": "/platform/student-information-system/"},
            {"label": "Admissions", "path": "/platform/admissions/"},
            {"label": "Grading & Report Cards", "path": "/platform/grading-report-cards/"},
            {"label": "Communications", "path": "/platform/communications/"},
            {"label": "Parent Portal", "path": "/platform/parent-portal/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
            {"label": "Security & Governance", "path": "/platform/security/"},
            {"label": "Global configuration", "path": "/platform/"},
        ],
        "stock_photo_static": "images/marketing/illustration-globe.svg",
        "stock_photo_alt": "Globe illustration representing international school configuration and cohorts",
        "workflow_diagram_static": "images/marketing/platform-diagram-marketing.svg",
        "global_config_note": "Terms, grading scales, currencies, languages, and campuses tune per school—multi-campus and multi-country ready.",
    },
    "k12": {
        "problem_section": {
            "title": "K–12 teams need everyday reliability across attendance, grading, and family visibility",
            "body": "Spreadsheet drift and disconnected portals slow administrators and frustrate families. RunMyCampus keeps daily operations—attendance through report cards—in one configurable operating layer.",
        },
        "recommended_modules": [
            {"label": "Student Information System", "path": "/platform/student-information-system/"},
            {"label": "Attendance", "path": "/platform/attendance/"},
            {"label": "Grading & Report Cards", "path": "/platform/grading-report-cards/"},
            {"label": "Parent Portal", "path": "/platform/parent-portal/"},
            {"label": "Student Portal", "path": "/platform/student-portal/"},
            {"label": "Communications", "path": "/platform/communications/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
        ],
        "stock_photo_url": "https://images.unsplash.com/photo-1580582932707-520aed937b7b?auto=format&fit=crop&w=1600&q=75",
        "stock_photo_alt": "Students engaged in a K–12 classroom lesson",
        "stock_photo_credit": "Photo via Unsplash",
        "workflow_diagram_static": "images/marketing/module-academics.svg",
        "global_config_note": "Your academic calendar, grading model, and fee structures configure once—scalable across campuses when you grow.",
    },
    "k12-schools": {
        "problem_section": {
            "title": "K–12 teams need everyday reliability across attendance, grading, and family visibility",
            "body": "Spreadsheet drift and disconnected portals slow administrators and frustrate families. RunMyCampus keeps daily operations—attendance through report cards—in one configurable operating layer.",
        },
        "recommended_modules": [
            {"label": "Student Information System", "path": "/platform/student-information-system/"},
            {"label": "Attendance", "path": "/platform/attendance/"},
            {"label": "Grading & Report Cards", "path": "/platform/grading-report-cards/"},
            {"label": "Parent Portal", "path": "/platform/parent-portal/"},
            {"label": "Student Portal", "path": "/platform/student-portal/"},
            {"label": "Communications", "path": "/platform/communications/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
        ],
        "stock_photo_static": "images/marketing/module-academics.svg",
        "stock_photo_alt": "Illustration of K–12 academics, attendance, and grading in one workspace",
        "workflow_diagram_static": "images/marketing/module-academics.svg",
        "global_config_note": "Your academic calendar, grading model, and fee structures configure once—scalable across campuses when you grow.",
    },
    "multi-campus": {
        "problem_section": {
            "title": "Networks need consistent policy without killing campus agility",
            "body": "When each campus runs separate tools, finance and enrollment visibility collapse into manual rollups. RunMyCampus balances central governance with campus execution.",
        },
        "recommended_modules": [
            {"label": "Analytics", "path": "/platform/analytics/"},
            {"label": "Security & Governance", "path": "/platform/security/"},
            {"label": "Workflows", "path": "/platform/workflows/"},
            {"label": "Student Information System", "path": "/platform/student-information-system/"},
            {"label": "Fees & Payments", "path": "/platform/fees-payments/"},
            {"label": "Communications", "path": "/platform/communications/"},
            {"label": "Configuration engine", "path": "/platform/"},
        ],
        "stock_photo_static": "images/marketing/ecosystem-diagram.svg",
        "stock_photo_alt": "Diagram-style illustration of coordinated multi-campus governance and analytics",
        "workflow_diagram_static": "images/marketing/viz-admin.svg",
        "global_config_note": "Ready-made setups, policies, and portals propagate network-wide while campuses retain operational autonomy.",
    },
    "faith-based-schools": {
        "problem_section": {
            "title": "Mission-driven schools still need disciplined finance and communications",
            "body": "Community trust depends on clarity across tuition, pastoral messaging, and academics. Fragmented channels undermine stewardship and transparency.",
        },
        "recommended_modules": [
            {"label": "Communications", "path": "/platform/communications/"},
            {"label": "Parent Portal", "path": "/platform/parent-portal/"},
            {"label": "Fees & Payments", "path": "/platform/fees-payments/"},
            {"label": "Student Information System", "path": "/platform/student-information-system/"},
            {"label": "Grading & Report Cards", "path": "/platform/grading-report-cards/"},
            {"label": "Attendance", "path": "/platform/attendance/"},
        ],
        "stock_photo_static": "images/marketing/module-communication.svg",
        "stock_photo_alt": "Illustration of communications between school, families, and pastoral messaging channels",
        "workflow_diagram_static": "images/marketing/module-communication.svg",
        "global_config_note": "Configure terminology, calendars, and roles to reflect denominational or mission-aligned operating models globally.",
    },
    "growing-school-networks": {
        "problem_section": {
            "title": "Adding campuses should not multiply operational chaos",
            "body": "Without repeatable onboarding and governance rails, each new school reinvents workflows. RunMyCampus templates rollout while preserving oversight.",
        },
        "recommended_modules": [
            {"label": "Student Information System", "path": "/platform/student-information-system/"},
            {"label": "Workflows", "path": "/platform/workflows/"},
            {"label": "Analytics", "path": "/platform/analytics/"},
            {"label": "Security & Governance", "path": "/platform/security/"},
            {"label": "Multi-campus configuration", "path": "/platform/control-plane/"},
            {"label": "Admissions", "path": "/platform/admissions/"},
            {"label": "Fees & Payments", "path": "/platform/fees-payments/"},
        ],
        "stock_photo_static": "images/marketing/migration-flow.svg",
        "stock_photo_alt": "Workflow illustration for repeatable onboarding across growing school networks",
        "workflow_diagram_static": "images/marketing/setup-studio-flow.svg",
        "global_config_note": "Provision templates, marketplace extensions, and policy bundles scale networks across regions—same codebase, localized configuration.",
    },
}
