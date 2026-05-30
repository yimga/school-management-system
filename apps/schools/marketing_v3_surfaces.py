"""Marketing v3 surface helpers — module rail, verb nav, platform/solutions context."""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import gettext_lazy as _


def marketing_verb_nav_enabled() -> bool:
    return bool(getattr(settings, "MARKETING_VERB_NAV_ENABLED", False))


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


def marketing_solution_buyer_worlds() -> list[dict]:
    """Six institution worlds for the public Solutions operating map."""
    worlds = [
        {
            "slug": "private-schools",
            "name": _("Private Schools"),
            "lead": _("Growth, fee confidence, and parent trust without disconnected tools."),
            "problem": _("Turn inquiry pressure, tuition clarity, and family experience into one operating picture."),
            "url_name": "marketing_solutions_private_schools",
            "fallback": "/solutions/private-schools/",
            "asset": "images/marketing/solution-private-growth-engine.svg",
            "asset_alt": _("Private school growth workflow visual with inquiry, fee, and parent engagement signals."),
        },
        {
            "slug": "international-schools",
            "name": _("International Schools"),
            "lead": _("Global operating models for calendars, programs, currencies, and reporting."),
            "problem": _("Keep mobile families and multi-program campuses governed from one school core."),
            "url_name": "marketing_solutions_international_schools",
            "fallback": "/solutions/international-schools/",
            "asset": "images/marketing/solution-international-global-model.svg",
            "asset_alt": _("International school model visual with programs, currencies, and calendars."),
        },
        {
            "slug": "k12-schools",
            "name": _("K-12 Schools"),
            "lead": _("A learner lifecycle across attendance, academics, and family engagement."),
            "problem": _("Run the daily chain from register to report card without losing student context."),
            "url_name": "marketing_solutions_k12_schools",
            "fallback": "/solutions/k12-schools/",
            "asset": "images/marketing/solution-k12-lifecycle.svg",
            "asset_alt": _("K-12 learner lifecycle visual from attendance to progress and family action."),
        },
        {
            "slug": "multi-campus",
            "name": _("Multi-Campus Groups"),
            "lead": _("Network command, campus comparison, and standards with local execution."),
            "problem": _("Give leadership rollups without forcing every campus into the same operating day."),
            "url_name": "marketing_solutions_multi_campus",
            "fallback": "/solutions/multi-campus/",
            "asset": "images/marketing/solution-multi-campus-command-center.svg",
            "asset_alt": _("Multi-campus command visual comparing campus finance, academic, and attendance signals."),
        },
        {
            "slug": "faith-based-schools",
            "name": _("Faith-Based Schools"),
            "lead": _("Community operations where announcements, fees, and family responses stay clear."),
            "problem": _("Support mission-led communication with disciplined records and finance visibility."),
            "url_name": "marketing_solutions_faith_based_schools",
            "fallback": "/solutions/faith-based-schools/",
            "asset": "images/marketing/solution-faith-community-hub.svg",
            "asset_alt": _("Community operations visual showing announcements, attendance, fees, and family responses."),
        },
        {
            "slug": "growing-school-networks",
            "name": _("Growing School Networks"),
            "lead": _("Repeatable launch playbooks for every campus added to the network."),
            "problem": _("Template rollout phases and readiness checks instead of rebuilding each opening."),
            "url_name": "marketing_solutions_growing_school_networks",
            "fallback": "/solutions/growing-school-networks/",
            "asset": "images/marketing/solution-growing-network-playbook.svg",
            "asset_alt": _("Growing school network rollout visual with readiness score, phases, and template reuse."),
        },
    ]
    return [
        {
            **world,
            "url": _p(world["url_name"], world["fallback"]),
        }
        for world in worlds
    ]


def marketing_navbar_verb_primary() -> list[dict]:
    """Verb-first nav (Phase 3) — Run / Teach / Pay / Communicate / Grow."""
    run_path = _p("marketing_run_hub", "/run/")
    teach_path = _p("marketing_teach_hub", "/teach/")
    pay_path = _p("marketing_pay_hub", "/pay/")
    comm_path = _p("marketing_communicate_hub", "/communicate/")
    grow_path = _p("marketing_grow_hub", "/grow/")
    pricing_path = _p("marketing_pricing", "/pricing/")
    storefront_path = _p("marketing_intent_homepage", "/storefront/")
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
        {"label": _("Run"), "path": run_path, "mega_columns": run_mega},
        {"label": _("Teach"), "path": teach_path, "mega_columns": teach_mega},
        {"label": _("Pay"), "path": pay_path, "mega_columns": pay_mega},
        {"label": _("Communicate"), "path": comm_path, "mega_columns": comm_mega},
        {"label": _("Grow"), "path": grow_path, "mega_columns": grow_mega},
        {"label": _("Experience"), "path": storefront_path},
        {"label": _("Pricing"), "path": pricing_path},
        {"label": _("Why RunMyCampus"), "path": why_path},
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


# Retired in the enterprise marketing IA: /platform/* routes are canonical
# product pages and must not silently redirect into verb hubs.
MARKETING_PLATFORM_TO_VERB_REDIRECTS: dict[str, str] = {}
