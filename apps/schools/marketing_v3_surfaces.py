"""Marketing v3 surface helpers — module rail, verb nav, platform/solutions context."""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import gettext_lazy as _


def marketing_verb_nav_enabled() -> bool:
    return bool(getattr(settings, "MARKETING_VERB_NAV_ENABLED", True))


def _p(name: str, fallback: str, **kwargs) -> str:
    from django.urls import NoReverseMatch, reverse

    try:
        return reverse(name, kwargs=kwargs if kwargs else None)
    except NoReverseMatch:
        return fallback


def _nav_link(label, path, blurb):
    return {"label": label, "path": path, "blurb": blurb}


def marketing_module_rail_modules() -> list[dict]:
    """Eight-module tour for the platform overview (Phase 2)."""
    modules = [
        (
            "1.0",
            "admissions",
            _("Admissions"),
            _("Pipeline from enquiry through enrollment."),
            "marketing_platform_admissions",
            "/platform/admissions/",
            "schools/_v2/_artifact_leader_overview.svg.html",
            [
                _("Stage conversion without spreadsheet drift."),
                _("Readiness board for every open seat."),
                _("Family thread stays on one record."),
            ],
        ),
        (
            "2.0",
            "academics",
            _("Academics"),
            _("Curriculum, assessment, and reporting on one spine."),
            "marketing_platform_grading_report_cards",
            "/platform/grading-report-cards/",
            "schools/_v2/_artifact_teacher_attendance.svg.html",
            [
                _("Class cards tied to live enrollments."),
                _("Assessment ladder parents can follow."),
                _("Report packs without Friday-night exports."),
            ],
        ),
        (
            "3.0",
            "attendance",
            _("Attendance"),
            _("Daily rhythm register class by class."),
            "marketing_platform_attendance",
            "/platform/attendance/",
            "schools/_v2/_artifact_teacher_attendance.svg.html",
            [
                _("Nine-second roll marks."),
                _("Late patterns surfaced early."),
                _("Office and classroom share one register."),
            ],
        ),
        (
            "4.0",
            "fees",
            _("Fees"),
            _("Finance cockpit for the bursar's day."),
            "marketing_platform_fees_payments",
            "/platform/fees-payments/",
            "schools/_v2/_artifact_finance_dashboard.svg.html",
            [
                _("Collected vs outstanding — hourly."),
                _("Reconciliation against the ledger."),
                _("Reminders in the family's channel."),
            ],
        ),
        (
            "5.0",
            "communications",
            _("Communications"),
            _("Message orchestration across channels."),
            "marketing_platform_communications",
            "/platform/communications/",
            "schools/_v2/_artifact_parent_phone_compact.svg.html",
            [
                _("Email, SMS, and inbox in one thread."),
                _("Permission slips without paper chase."),
                _("Delivery telemetry operators trust."),
            ],
        ),
        (
            "6.0",
            "portals",
            _("Portals"),
            _("Parent, teacher, and student command centers."),
            "marketing_platform_parent_portal",
            "/platform/parent-portal/",
            "schools/_v2/_artifact_parent_phone_compact.svg.html",
            [
                _("Role-specific surfaces, one sign-in story."),
                _("No extra app install for families."),
                _("Official channel beats group chat."),
            ],
        ),
        (
            "7.0",
            "analytics",
            _("Analytics"),
            _("Leadership intelligence without tab hunting."),
            "marketing_platform_analytics",
            "/platform/analytics/",
            "schools/_v2/_artifact_leader_overview.svg.html",
            [
                _("Heads-view dashboards."),
                _("Cohort drill-downs."),
                _("Early-warning panels."),
            ],
        ),
        (
            "8.0",
            "marketplace",
            _("Marketplace"),
            _("Governed apps and integration depth."),
            "marketing_platform_marketplace",
            "/platform/marketplace/",
            "schools/_v2/_artifact_it_health.svg.html",
            [
                _("Curated partner tiles."),
                _("Integration tags operators understand."),
                _("Governance console for IT."),
            ],
        ),
    ]
    out: list[dict] = []
    for index, slug, name, lead, url_name, fallback, partial, bullets in modules:
        out.append(
            {
                "index": index,
                "slug": slug,
                "name": name,
                "lead": lead,
                "url": _p(url_name, fallback),
                "dashboard_partial": partial,
                "bullets": bullets,
            }
        )
    return out


def _solutions_persona_catalog() -> list[dict]:
    return [
        {
            "slug": "head",
            "name": _("Head of school"),
            "lead": _("One honest summary — attendance, fees, behaviour, staffing."),
            "url_name": "marketing_solutions_persona_head",
            "dashboard_partial": "schools/_v2/_artifact_leader_overview.svg.html",
            "bullets": [
                _("Morning brief with live attendance and fee posture."),
                _("Staffing gaps surfaced before the first bell."),
                _("One board-ready export — no spreadsheet stitching."),
            ],
        },
        {
            "slug": "bursar",
            "name": _("Bursar"),
            "lead": _("Collected, outstanding, reconciled — hourly."),
            "url_name": "marketing_solutions_persona_bursar",
            "dashboard_partial": "schools/_v2/_artifact_finance_dashboard.svg.html",
            "bullets": [
                _("Fee plans, receipts, and arrears on one ledger."),
                _("Gateway reconciliation without end-of-month panic."),
                _("Audit trail finance leadership can defend."),
            ],
        },
        {
            "slug": "teacher",
            "name": _("Teacher"),
            "lead": _("Roll mark in nine seconds between lessons."),
            "url_name": "marketing_solutions_persona_teacher",
            "dashboard_partial": "schools/_v2/_artifact_teacher_attendance.svg.html",
            "bullets": [
                _("Register that survives spotty Wi‑Fi."),
                _("Grades and comments without leaving the class view."),
                _("Parents see the same facts the teacher recorded."),
            ],
        },
        {
            "slug": "parent",
            "name": _("Parent"),
            "lead": _("Today's slip, attendance, and fee in one card."),
            "url_name": "marketing_solutions_persona_parent",
            "dashboard_partial": "schools/_v2/_artifact_parent_phone_compact.svg.html",
            "bullets": [
                _("One card for attendance, fees, and messages."),
                _("Push-friendly alerts — not another portal maze."),
                _("Pays or acknowledges fees without calling the office."),
            ],
        },
        {
            "slug": "it",
            "name": _("IT lead"),
            "lead": _("SSO and tenant health before staff feel a blip."),
            "url_name": "marketing_solutions_persona_it",
            "dashboard_partial": "schools/_v2/_artifact_it_health.svg.html",
            "bullets": [
                _("SAML/OIDC and scoped API keys in one trust surface."),
                _("Webhook delivery health with replay and remediation."),
                _("Tenant isolation posture procurement can verify."),
            ],
        },
    ]


def marketing_solutions_personas() -> list[dict]:
    out: list[dict] = []
    for row in _solutions_persona_catalog():
        slug = row["slug"]
        out.append(
            {
                **row,
                "url": _p(row["url_name"], f"/solutions/{slug}/"),
            }
        )
    return out


def marketing_solutions_persona_by_slug(slug: str) -> dict | None:
    normalized = (slug or "").strip().lower()
    for row in _solutions_persona_catalog():
        if row["slug"] == normalized:
            return {
                **row,
                "url": _p(row["url_name"], f"/solutions/{normalized}/"),
            }
    return None


def marketing_navbar_verb_primary() -> list[dict]:
    """Verb-first nav (Phase 3) — Run / Teach / Pay / Communicate / Grow."""
    run_path = _p("marketing_run_hub", "/run/")
    teach_path = _p("marketing_teach_hub", "/teach/")
    pay_path = _p("marketing_pay_hub", "/pay/")
    comm_path = _p("marketing_communicate_hub", "/communicate/")
    grow_path = _p("marketing_grow_hub", "/grow/")
    pricing_path = _p("marketing_pricing", "/pricing/")
    why_path = _p("marketing_why_switch", "/why-switch/")

    run_mega = [
        {
            "title": _("Run the school"),
            "links": [
                _nav_link(_("Admissions"), _p("marketing_run_admissions", "/run/admissions/"), _("Pipeline and readiness board.")),
                _nav_link(_("Attendance"), _p("marketing_run_attendance", "/run/attendance/"), _("Daily register and late patterns.")),
                _nav_link(_("Analytics"), _p("marketing_run_analytics", "/run/analytics/"), _("Leadership intelligence center.")),
                _nav_link(_("Workflows"), _p("marketing_run_workflows", "/run/workflows/"), _("Automation without shadow IT.")),
                _nav_link(_("Multi-school networks"), _p("marketing_solutions_multi_campus", "/solutions/multi-campus/"), _("Roll-ups across campuses.")),
            ],
        },
    ]
    teach_mega = [
        {
            "title": _("Teach"),
            "links": [
                _nav_link(_("Gradebook"), _p("marketing_teach_gradebook", "/teach/gradebook/"), _("Marks and comments between lessons.")),
                _nav_link(_("Academics"), _p("marketing_teach_academics", "/teach/academics/"), _("Curriculum on the learner spine.")),
                _nav_link(_("Teacher workspace"), _p("marketing_teach_workspace", "/teach/workspace/"), _("Classroom command center.")),
            ],
        },
    ]
    pay_mega = [
        {
            "title": _("Pay"),
            "links": [
                _nav_link(_("Fees & invoicing"), _p("marketing_pay_fees", "/pay/fees/"), _("Term status and collections.")),
                _nav_link(_("Reconciliation"), _p("marketing_pay_reconciliation", "/pay/reconciliation/"), _("Ledger ties out hourly.")),
                _nav_link(_("Finance cockpit"), _p("marketing_pricing", "/pricing/"), _("Bursar's daily dashboard.")),
            ],
        },
    ]
    comm_mega = [
        {
            "title": _("Communicate"),
            "links": [
                _nav_link(_("Parent inbox"), _p("marketing_communicate_inbox", "/communicate/inbox/"), _("Single-thread family view.")),
                _nav_link(_("Announcements"), _p("marketing_communicate_announcements", "/communicate/announcements/"), _("School-wide and targeted sends.")),
                _nav_link(_("Newsletters"), _p("marketing_communicate_newsletters", "/communicate/newsletters/"), _("Editorial rhythm without Mailchimp.")),
            ],
        },
    ]
    grow_mega = [
        {
            "title": _("Grow"),
            "links": [
                _nav_link(_("Marketplace"), _p("marketing_grow_marketplace", "/grow/marketplace/"), _("Governed app catalog.")),
                _nav_link(_("Migration Cloud"), _p("marketing_grow_migration", "/grow/migration/"), _("Phased cutover playbooks.")),
                _nav_link(_("Developers"), _p("marketing_developers", "/developers/"), _("API and webhooks.")),
            ],
        },
    ]

    return [
        {"label": _("Run"), "path": run_path, "mega_columns": run_mega, "bridge_label": _("was: Platform")},
        {"label": _("Teach"), "path": teach_path, "mega_columns": teach_mega, "bridge_label": _("was: Platform")},
        {"label": _("Pay"), "path": pay_path, "mega_columns": pay_mega, "bridge_label": _("was: Platform")},
        {"label": _("Communicate"), "path": comm_path, "mega_columns": comm_mega, "bridge_label": _("was: Platform")},
        {"label": _("Grow"), "path": grow_path, "mega_columns": grow_mega, "bridge_label": _("was: Platform")},
        {"label": _("Pricing"), "path": pricing_path},
        {"label": _("Why switch"), "path": why_path},
    ]


def marketing_verb_hub_links(verb: str) -> list[dict]:
    """Flatten mega-menu links for a verb hub landing page."""
    normalized = (verb or "").strip().lower()
    path_suffix = f"/{normalized}/"
    for item in marketing_navbar_verb_primary():
        path = (item.get("path") or "").rstrip("/") + "/"
        if not path.endswith(path_suffix):
            continue
        links: list[dict] = []
        for col in item.get("mega_columns") or []:
            links.extend(col.get("links") or [])
        return links
    return []


# Legacy /platform/* → verb paths (Phase 3 redirects).
MARKETING_PLATFORM_TO_VERB_REDIRECTS: dict[str, str] = {
    "platform/admissions/": "run/admissions/",
    "platform/attendance/": "run/attendance/",
    "platform/analytics/": "run/analytics/",
    "platform/workflows/": "run/workflows/",
    "platform/offline-first/": "run/offline/",
    "platform/grading-report-cards/": "teach/gradebook/",
    "platform/student-information-system/": "teach/academics/",
    "platform/teacher-portal/": "teach/workspace/",
    "platform/fees-payments/": "pay/fees/",
    "platform/parent-portal/": "communicate/inbox/",
    "platform/communications/": "communicate/announcements/",
    "platform/marketplace/": "grow/marketplace/",
    "platform/migration-cloud/": "grow/migration/",
}
