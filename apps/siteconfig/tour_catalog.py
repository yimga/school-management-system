"""
Default guided-tour step catalogs per context.

DB TourStep rows override these when present for the same context.
Selectors must match template ``data-tour`` attributes (not step codes).
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _


def catalog_step(
    code: str,
    title: str,
    *,
    selector: str = "",
    body: str = "",
) -> dict:
    sel = selector or f"[data-tour='{code}']"
    return {"code": code, "title": title, "body": body, "selector": sel}


# Tenant backend command center — shared steps (included in all admin variants)
_BACKEND_CORE = [
    catalog_step(
        "dashboard-main",
        _("Your command center"),
        selector="[data-tour='dashboard-main']",
        body=_("Overview of school health, KPIs, and what needs attention."),
    ),
    catalog_step(
        "quick-actions",
        _("Quick actions"),
        selector="[data-tour='quick-actions']",
        body=_("Jump to frequent tasks without leaving the dashboard."),
    ),
    catalog_step(
        "setup-studio-link",
        _("Setup Studio"),
        selector="[data-tour='setup-studio-link']",
        body=_("Guided setup for academics, people, and go-live readiness."),
    ),
    catalog_step(
        "school-configuration-link",
        _("School configuration"),
        selector="[data-tour='school-configuration-link']",
        body=_("Branding, terms, grading, and tenant-wide settings."),
    ),
]

BACKEND_DASHBOARD_ADMIN = list(_BACKEND_CORE) + [
    catalog_step(
        "launch-studio-link",
        _("Launch Studio"),
        selector="[data-tour='launch-studio-link']",
        body=_("Preview readiness, migration, and role-based walkthroughs."),
    ),
]

BACKEND_DASHBOARD_LEADERSHIP = list(_BACKEND_CORE) + [
    catalog_step(
        "backend-kpi-strip",
        _("Leadership KPIs"),
        selector="[data-tour='backend-kpi-strip']",
        body=_("Enrollment, collection, and academic signals for board-ready conversations."),
    ),
]

BACKEND_DASHBOARD_OPERATIONS = list(_BACKEND_CORE) + [
    catalog_step(
        "backend-integrations",
        _("Integrations & health"),
        selector="[data-tour='school-configuration-link']",
        body=_("Connect SIS exports, webhooks, and monitor sync posture."),
    ),
]

# Legacy alias
BACKEND_DASHBOARD = BACKEND_DASHBOARD_ADMIN

TEACHER_PORTAL = [
    catalog_step(
        "teacher-attention",
        _("What needs attention"),
        selector="[data-tour='teacher-attention']",
        body=_("Marks, attendance, and workflow signals prioritized for today."),
    ),
    catalog_step(
        "teacher-fast-workflows",
        _("Fast workflows"),
        selector="[data-tour='teacher-fast-workflows']",
        body=_("One tap to attendance, marks, syllabus, and messaging."),
    ),
    catalog_step(
        "teacher-today",
        _("Today's classes"),
        selector="[data-tour='teacher-today']",
        body=_("Your schedule and class list for the current day."),
    ),
    catalog_step(
        "teacher-section-nav",
        _("Dashboard sections"),
        selector="[data-tour='teacher-section-nav']",
        body=_("Jump between attention, today, metrics, and classes."),
    ),
]

PARENT_PORTAL = [
    catalog_step(
        "parent-header",
        _("Family home"),
        selector="[data-tour='parent-header']",
        body=_("Your children's status, fees, and school messages in one place."),
    ),
    catalog_step(
        "parent-quick-actions",
        _("Quick actions"),
        selector="[data-tour='parent-quick-actions']",
        body=_("Pay fees, view results, and message the school without hunting menus."),
    ),
    catalog_step(
        "parent-children",
        _("My children"),
        selector="[data-tour='parent-children']",
        body=_("Switch between learners linked to your account."),
    ),
]

STUDENT_PORTAL = [
    catalog_step(
        "student-header",
        _("Your learning home"),
        selector="[data-tour='student-header']",
        body=_("Today's priorities and announcements from your school."),
    ),
    catalog_step(
        "student-decision-strip",
        _("Next steps"),
        selector="[data-tour='student-decision-strip']",
        body=_("Assignments and tasks surfaced by your teachers."),
    ),
]

MARKETING_HOME = [
    catalog_step(
        "mkt-hero",
        _("Welcome"),
        selector="[data-tour='mkt-hero']",
        body=_("How RunMyCampus connects admissions, classrooms, fees, and family messaging."),
    ),
    catalog_step(
        "mkt-roi",
        _("Outcomes"),
        selector="[data-tour='mkt-roi']",
        body=_("Time saved and operational clarity schools report after switching."),
    ),
    catalog_step(
        "mkt-walkthrough",
        _("Product walkthrough"),
        selector="[data-tour='mkt-walkthrough']",
        body=_("A quick visual tour of the platform surfaces."),
    ),
    catalog_step(
        "mkt-pricing",
        _("Pricing"),
        selector="[data-tour='mkt-pricing']",
        body=_("Plans scale with enrollment — confirm details during your demo."),
    ),
]

STUDIO_OS = [
    catalog_step(
        "studio-toolbar",
        _("Studio toolbar"),
        selector="[data-tour='studio-toolbar']",
        body=_("Search, commands, and quick navigation across Studio modes."),
    ),
    catalog_step(
        "studio-rail",
        _("Work modes"),
        selector="[data-tour='studio-rail']",
        body=_("Switch between Experience, Automation, Outputs, Launch, and Control."),
    ),
    catalog_step(
        "studio-canvas",
        _("Studio canvas"),
        selector="[data-tour='studio-canvas']",
        body=_("The active workspace for the mode you selected."),
    ),
]

FINANCE_INVOICES = [
    catalog_step(
        "finance-filters",
        _("Invoice filters"),
        selector="[data-tour='finance-filters']",
        body=_("Search and narrow invoices by status or student."),
    ),
    catalog_step(
        "finance-table",
        _("Invoice list"),
        selector="[data-tour='finance-table']",
        body=_("Open an invoice to record payments or print receipts."),
    ),
]

ADMISSIONS_QUEUE = [
    catalog_step(
        "admissions-search",
        _("Applicant search"),
        selector="[data-tour='admissions-search']",
        body=_("Find applicants by name, reference, or status."),
    ),
    catalog_step(
        "admissions-table",
        _("Applicant queue"),
        selector="[data-tour='admissions-table']",
        body=_("Review, advance, or message applicants from this list."),
    ),
]

TEACHER_GRADEBOOK = [
    catalog_step(
        "gradebook-header",
        _("Gradebook"),
        selector="[data-tour='gradebook-header']",
        body=_("Enter and review marks for your classes."),
    ),
    catalog_step(
        "gradebook-grid",
        _("Marks grid"),
        selector="[data-tour='gradebook-grid']",
        body=_("Tab through cells; save when you are done editing."),
    ),
]

NOTIFICATIONS_INBOX = [
    catalog_step(
        "inbox-filters",
        _("Inbox filters"),
        selector="[data-tour='inbox-filters']",
        body=_("Show unread or all notifications."),
    ),
    catalog_step(
        "inbox-list",
        _("Notification list"),
        selector="[data-tour='inbox-list']",
        body=_("Open items to jump to the related record or action."),
    ),
]

# Control-plane super-operator surfaces (BR-13)
SUPER_TRUST = [
    catalog_step(
        "cp-trust-header",
        _("Trust center overview"),
        selector="[data-tour='cp-trust-header']",
    ),
    catalog_step(
        "cp-trust-cards",
        _("Compliance and audit entry points"),
        selector="[data-tour='cp-trust-cards']",
    ),
    catalog_step(
        "cp-trust-migration-link",
        _("Migration CSV diff"),
        selector="[data-tour='cp-trust-migration-link']",
    ),
]

SUPER_MIGRATION = [
    catalog_step(
        "cp-migration-intro",
        _("Migration CSV diff"),
        selector="[data-tour='cp-migration-intro']",
        body=_("Upload two CSVs to compare keys and spot migration risk."),
    ),
    catalog_step(
        "cp-migration-form",
        _("Baseline vs candidate"),
        selector="[data-tour='cp-migration-form']",
    ),
]

SUPER_GOVERNED = [
    catalog_step(
        "cp-gov-intro",
        _("Governed query"),
        selector="[data-tour='cp-gov-intro']",
        body=_("Whitelisted intents only — every run is audited."),
    ),
    catalog_step(
        "cp-gov-form",
        _("Run an intent"),
        selector="[data-tour='cp-gov-form']",
    ),
]

def marketing_product_tour_steps() -> list:
    """Build tour steps from resources-product-tour.json stops."""
    import json
    from pathlib import Path

    from django.conf import settings

    path = (
        Path(settings.BASE_DIR)
        / "config"
        / "marketing_content"
        / "resources-product-tour.json"
    )
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    stops = (data.get("extras") or {}).get("product_tour_stops") or []
    steps = []
    for i, stop in enumerate(stops):
        code = f"product-tour-{i}"
        steps.append(
            catalog_step(
                code,
                stop.get("title") or code,
                selector=f"[data-tour='{code}']",
                body=stop.get("body") or "",
            )
        )
    return steps


CATALOGS: dict[str, list] = {
    "backend_dashboard": BACKEND_DASHBOARD,
    "backend_dashboard_admin": BACKEND_DASHBOARD_ADMIN,
    "backend_dashboard_leadership": BACKEND_DASHBOARD_LEADERSHIP,
    "backend_dashboard_operations": BACKEND_DASHBOARD_OPERATIONS,
    "teacher_portal": TEACHER_PORTAL,
    "parent_portal": PARENT_PORTAL,
    "student_portal": STUDENT_PORTAL,
    "marketing_home": MARKETING_HOME,
    "marketing_product_tour": [],  # filled at runtime via marketing_product_tour_steps()
    "studio_os": STUDIO_OS,
    "finance_invoices": FINANCE_INVOICES,
    "admissions_queue": ADMISSIONS_QUEUE,
    "teacher_gradebook": TEACHER_GRADEBOOK,
    "notifications_inbox": NOTIFICATIONS_INBOX,
    "super_trust": SUPER_TRUST,
    "super_migration": SUPER_MIGRATION,
    "super_governed": SUPER_GOVERNED,
}

# Maps ``data-rmc-page`` slug on DOM to tour API context.
PAGE_SLUG_TO_CONTEXT: dict[str, str] = {
    "studio-os": "studio_os",
    "finance-invoices": "finance_invoices",
    "admissions-queue": "admissions_queue",
    "teacher-gradebook": "teacher_gradebook",
    "notifications-inbox": "notifications_inbox",
    "teacher-portal": "teacher_portal",
    "parent-portal": "parent_portal",
    "student-portal": "student_portal",
}

MARKETING_SLUG_TO_CONTEXT: dict[str, str] = {
    "marketing": "marketing_home",
    "resources-product-tour": "marketing_product_tour",
}


def default_steps_for_context(context: str) -> list[dict]:
    """Return a shallow copy of catalog steps for *context* (may be empty)."""
    if context == "marketing_product_tour":
        raw = marketing_product_tour_steps()
    else:
        raw = CATALOGS.get(context) or []
    return [
        {
            "code": s["code"],
            "title": str(s["title"]),
            "body": str(s.get("body") or ""),
            "selector": s["selector"],
        }
        for s in raw
    ]
