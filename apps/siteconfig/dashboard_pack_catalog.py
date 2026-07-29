"""
Pure (model-free) catalog data for dashboard packs + their default templates.

Kept import-clean of any Django model so it can be safely imported by BOTH the
seed command and the data migration (migrations must not import live models —
scan_migration_model_imports). See docs/DASHBOARD_PACKS_REVIVAL_PLAN.md.
"""

from __future__ import annotations

# === Dashboard packs (per-role + per-domain coverage). Idempotent by code. ===
DASHBOARD_PACKS = [
    {
        "code": "school-admin-executive",
        "name": "School Admin Executive",
        "family": "admin",
        "description": "Executive summary and KPIs for school admins.",
    },
    {
        "code": "school-admin-operations",
        "name": "School Admin Operations",
        "family": "admin",
        "description": "Day-to-day operations and tasks.",
    },
    {
        "code": "admissions-operations",
        "name": "Admissions Operations",
        "family": "admissions",
        "description": "Pipeline and application queue for admissions team.",
    },
    {
        "code": "admissions-analytics",
        "name": "Admissions Analytics",
        "family": "admissions",
        "description": "Application metrics and funnel view.",
    },
    {
        "code": "teacher-command-center",
        "name": "Teacher Command Center",
        "family": "teacher",
        "description": "Classes, grading, and attendance for teachers.",
    },
    {
        "code": "teacher-gradebook-quick",
        "name": "Teacher Gradebook Quick",
        "family": "teacher",
        "description": "Quick grade entry and class roster.",
    },
    {
        "code": "teacher-planner",
        "name": "Teacher Planner",
        "family": "teacher",
        "description": "Lesson plans and calendar view.",
    },
    {
        "code": "parent-mobile-feed",
        "name": "Parent Mobile Feed",
        "family": "parent",
        "description": "Mobile-friendly parent dashboard.",
    },
    {
        "code": "parent-student-progress",
        "name": "Parent Student Progress",
        "family": "parent",
        "description": "Grades, attendance, and feedback.",
    },
    {
        "code": "parent-payments",
        "name": "Parent Payments",
        "family": "parent",
        "description": "Fees, payments, and payment history.",
    },
    {
        "code": "finance-office-ledger",
        "name": "Finance Office Ledger",
        "family": "finance",
        "description": "Invoices, payments, and outstanding fees.",
    },
    {
        "code": "finance-reconciliation",
        "name": "Finance Reconciliation",
        "family": "finance",
        "description": "Bank reconciliation and audit view.",
    },
    {
        "code": "finance-aid",
        "name": "Finance Aid Overview",
        "family": "finance",
        "description": "Financial aid and scholarship dashboard.",
    },
    {
        "code": "low-bandwidth-compact",
        "name": "Low-Bandwidth Compact",
        "family": "compact",
        "description": "Minimal widgets for low-bandwidth users.",
    },
    {
        "code": "counselor-caseload",
        "name": "Counselor Caseload",
        "family": "counselor",
        "description": "Student caseload and intervention tracking.",
    },
    {
        "code": "counselor-attendance-alerts",
        "name": "Counselor Attendance Alerts",
        "family": "counselor",
        "description": "At-risk and attendance alerts.",
    },
    {
        "code": "principal-school-summary",
        "name": "Principal School Summary",
        "family": "principal",
        "description": "School-wide metrics and alerts.",
    },
    {
        "code": "principal-discipline",
        "name": "Principal Discipline",
        "family": "principal",
        "description": "Discipline incidents and follow-ups.",
    },
    {
        "code": "registrar-enrollment",
        "name": "Registrar Enrollment",
        "family": "registrar",
        "description": "Enrollment and schedule management.",
    },
    {
        "code": "registrar-transcripts",
        "name": "Registrar Transcripts",
        "family": "registrar",
        "description": "Transcript requests and fulfillment.",
    },
    {
        "code": "nurse-health-log",
        "name": "Nurse Health Log",
        "family": "nurse",
        "description": "Health room visits and medication log.",
    },
    {"code": "principal-academic-pulse", "name": "Principal — Academic Pulse", "family": "principal", "description": "Grade-distribution heatmap + on-track / at-risk band per cohort."},
    {"code": "principal-parent-engagement", "name": "Principal — Parent Engagement", "family": "principal", "description": "Parent-portal adoption + outbound message reach."},
    {"code": "vice-principal-discipline-trends", "name": "Vice Principal — Discipline Trends", "family": "principal", "description": "Discipline incident heatmap by grade / classroom / category."},
    {"code": "bursar-collection-rate", "name": "Bursar — Collection Rate", "family": "finance", "description": "Real-time collection rate by term + cohort with aging buckets."},
    {"code": "bursar-aging-report", "name": "Bursar — Aging Report", "family": "finance", "description": "Outstanding-balance aging report drilling into 30/60/90+ buckets."},
    {"code": "it-admin-system-health", "name": "IT Admin — System Health", "family": "it_admin", "description": "Health probes, integration sync state, AI provider reachability."},
    {"code": "it-admin-audit-trail", "name": "IT Admin — Audit Trail", "family": "it_admin", "description": "Recent admin actions, login anomalies, RBAC change feed."},
    {"code": "hr-staff-pipeline", "name": "HR — Staff Pipeline", "family": "hr", "description": "Open positions, candidates, onboarding/offboarding in flight."},
    {"code": "transport-fleet-status", "name": "Transport — Fleet Status", "family": "transport", "description": "Bus location, route on-time %, driver shift state."},
    {"code": "library-circulation", "name": "Library — Circulation", "family": "library", "description": "Active loans, overdue items, top-circulated titles."},
    {"code": "nurse-clinic-pulse", "name": "Nurse — Clinic Pulse", "family": "nurse", "description": "Visits today, recurring complaints, immunization due."},
    {"code": "boarding-house-summary", "name": "Boarding — House Summary", "family": "boarding", "description": "Occupancy, visitor count, leave-permission requests pending."},
    {"code": "cafeteria-meal-uptake", "name": "Cafeteria — Meal Uptake", "family": "cafeteria", "description": "Plan subscribers, daily uptake %, allergen incidents."},
    {"code": "student-self-service", "name": "Student — Self Service", "family": "student", "description": "Today's classes, assignments due, attendance % to date."},
    {"code": "student-focus-today", "name": "Student — Focus Today", "family": "student", "description": "A calm, single-column view of what's due today and your next class."},
    {"code": "student-progress-tracker", "name": "Student — Progress Tracker", "family": "student", "description": "Grades, attendance trend, and goal progress over the term."},
    {"code": "admissions-funnel-conversion", "name": "Admissions — Funnel Conversion", "family": "admissions", "description": "Inquiry → application → offer → enrol conversion with stage SLAs."},
    {"code": "alumni-engagement-summary", "name": "Alumni — Engagement Summary", "family": "alumni", "description": "Alumni roster activity + donation flow + event RSVP."},
    {"code": "compliance-evidence-room", "name": "Compliance — Evidence Room", "family": "compliance", "description": "SOC 2 / ISO evidence collection status by control."},
]


# Each pack gets ONE default DashboardTemplate so a TenantLayoutAssignment (PROTECT FK
# → DashboardTemplate) can be created. config_schema carries the header/footer chrome
# (consumed by portal_chrome.resolve_portal_chrome) plus a thin role_home overlay
# (consumed by dashboard_pack_resolver.overlay_role_home). No widget layouts are
# fabricated — the overlay refines the eyebrow/purpose copy + chrome only.
FAMILY_HEADER_VARIANT = {
    "admin": "standard",
    "principal": "wide",
    "teacher": "standard",
    "parent": "card",
    "student": "card",
    "finance": "standard",
    "it_admin": "wide",
    "compact": "minimal",
    "counselor": "standard",
    "registrar": "standard",
    "nurse": "card",
    "admissions": "standard",
    "hr": "standard",
    "transport": "card",
    "library": "card",
    "boarding": "card",
    "cafeteria": "card",
    "alumni": "card",
    "compliance": "wide",
}

# recommended_sectors lets the config cascade (default_pack_for_role) prefer a pack for
# a school's primary_sector. Keyed per-pack so it can discriminate WITHIN a family that
# has several packs (e.g. the admin family: operations for resource-constrained/public
# systems, executive for private/international). Sector codes match
# School.primary_sector (wedge 14–22). Packs not listed are sector-neutral.
PACK_RECOMMENDED_SECTORS = {
    "school-admin-operations": ["PUBLIC", "GOVERNMENT_MINISTRY", "NGO", "CHARTER"],
    "school-admin-executive": ["PRIVATE", "INTERNATIONAL", "FAITH_BASED", "MULTI_CAMPUS"],
    "finance-office-ledger": ["PUBLIC", "GOVERNMENT_MINISTRY", "NGO"],
    "finance-reconciliation": ["PRIVATE", "INTERNATIONAL", "MULTI_CAMPUS"],
    "principal-school-summary": ["PUBLIC", "GOVERNMENT_MINISTRY", "CHARTER"],
    "principal-academic-pulse": ["PRIVATE", "INTERNATIONAL", "FAITH_BASED"],
    "low-bandwidth-compact": ["NGO", "GOVERNMENT_MINISTRY"],
}


def recommended_sectors_for(row: dict) -> list:
    """Per-pack recommended sector codes (empty = sector-neutral)."""
    return PACK_RECOMMENDED_SECTORS.get(row.get("code", ""), [])


# === DEPTH: each pack drives WHAT renders, not just chrome. =================
# `modules` overrides backend dashboard module visibility (keys map to
# build_dashboard_extras `module_visibility`); only the keys that DIFFER from the
# all-on default are listed (False hides a module). `kpis` is the ordered KPI-strip
# priority (ids: top_performing / attendance_today / recent_admissions / weekly_presence).
# `theme` is a visual preset slug (soft-glass / crisp-professional / high-contrast).
# `focus_areas` replaces the role-home focus chips. Profiles are per-FAMILY; a few packs
# add a per-PACK override so same-family packs still render distinctly.
FAMILY_DASHBOARD_PROFILE: dict[str, dict] = {
    "admin": {"modules": {}, "kpis": ["recent_admissions", "attendance_today", "top_performing"], "theme": "crisp-professional", "focus_areas": ["School pulse", "Approvals", "Operations"]},
    "finance": {"modules": {"top_performing": False, "attendance_today": False, "enrollment_trends": False, "outstanding_fees": True, "ops_watch": True}, "kpis": ["recent_admissions", "weekly_presence", "attendance_today"], "theme": "crisp-professional", "focus_areas": ["Collections", "Approvals", "Reconciliation"]},
    "teacher": {"modules": {"admin_portal": False, "outstanding_fees": False, "top_performing": True, "attendance_today": True}, "kpis": ["top_performing", "attendance_today", "recent_admissions"], "theme": "soft-glass", "focus_areas": ["Class flow", "Assessment", "Family comms"]},
    "parent": {"modules": {"admin_portal": False, "ops_watch": False, "enrollment_trends": False, "top_performing": False, "at_risk_students": False}, "kpis": ["attendance_today", "recent_admissions", "weekly_presence"], "theme": "soft-glass", "focus_areas": ["Child context", "Fees", "Messages"]},
    "student": {"modules": {"admin_portal": False, "ops_watch": False, "outstanding_fees": False, "enrollment_trends": False, "recent_admissions": False}, "kpis": ["attendance_today", "weekly_presence", "top_performing"], "theme": "soft-glass", "focus_areas": ["Schedule", "Deadlines", "Progress"]},
    "principal": {"modules": {"admin_portal": True, "ops_watch": True, "at_risk_students": True}, "kpis": ["top_performing", "attendance_today", "recent_admissions"], "theme": "crisp-professional", "focus_areas": ["School pulse", "Decision queue", "Escalations"]},
    "it_admin": {"modules": {"top_performing": False, "outstanding_fees": False, "recent_admissions": False, "enrollment_trends": False, "ops_watch": True, "recent_activity": True}, "kpis": ["weekly_presence", "attendance_today", "recent_admissions"], "theme": "crisp-professional", "focus_areas": ["System health", "Audit", "Integrations"]},
    "compact": {"modules": {"enrollment_trends": False, "at_risk_students": False, "top_performing": False, "recent_activity": False, "ops_watch": False, "admin_portal": False}, "kpis": ["attendance_today", "recent_admissions", "weekly_presence"], "theme": "high-contrast", "focus_areas": ["Essentials"]},
    "counselor": {"modules": {"outstanding_fees": False, "top_performing": False, "at_risk_students": True, "attendance_today": True}, "kpis": ["attendance_today", "weekly_presence", "recent_admissions"], "theme": "soft-glass", "focus_areas": ["Caseload", "At-risk", "Interventions"]},
    "registrar": {"modules": {"outstanding_fees": False, "enrollment_trends": True, "recent_admissions": True}, "kpis": ["recent_admissions", "attendance_today", "weekly_presence"], "theme": "crisp-professional", "focus_areas": ["Enrollment", "Records", "Transcripts"]},
    "nurse": {"modules": {"outstanding_fees": False, "top_performing": False, "enrollment_trends": False, "attendance_today": True}, "kpis": ["attendance_today", "weekly_presence", "recent_admissions"], "theme": "soft-glass", "focus_areas": ["Clinic", "Immunizations", "Follow-ups"]},
    "admissions": {"modules": {"outstanding_fees": False, "recent_admissions": True, "enrollment_trends": True}, "kpis": ["recent_admissions", "attendance_today", "weekly_presence"], "theme": "crisp-professional", "focus_areas": ["Applicant flow", "Onboarding", "Record quality"]},
    "hr": {"modules": {"outstanding_fees": False, "top_performing": False, "recent_admissions": False, "recent_activity": True}, "kpis": ["weekly_presence", "attendance_today", "recent_admissions"], "theme": "crisp-professional", "focus_areas": ["Pipeline", "Onboarding", "Reviews"]},
    "transport": {"modules": {"outstanding_fees": False, "top_performing": False, "enrollment_trends": False, "attendance_today": True}, "kpis": ["attendance_today", "weekly_presence", "recent_admissions"], "theme": "soft-glass", "focus_areas": ["Routes", "On-time", "Incidents"]},
    "library": {"modules": {"outstanding_fees": False, "top_performing": False, "enrollment_trends": False}, "kpis": ["recent_admissions", "weekly_presence", "attendance_today"], "theme": "soft-glass", "focus_areas": ["Circulation", "Overdue", "Acquisitions"]},
    "boarding": {"modules": {"outstanding_fees": False, "top_performing": False, "attendance_today": True}, "kpis": ["attendance_today", "weekly_presence", "recent_admissions"], "theme": "soft-glass", "focus_areas": ["Occupancy", "Visitors", "Leave"]},
    "cafeteria": {"modules": {"outstanding_fees": True, "top_performing": False, "enrollment_trends": False}, "kpis": ["recent_admissions", "weekly_presence", "attendance_today"], "theme": "soft-glass", "focus_areas": ["Uptake", "Allergens", "Plans"]},
    "alumni": {"modules": {"outstanding_fees": False, "attendance_today": False, "top_performing": False, "recent_activity": True}, "kpis": ["recent_admissions", "weekly_presence", "attendance_today"], "theme": "soft-glass", "focus_areas": ["Engagement", "Giving", "Events"]},
    "compliance": {"modules": {"outstanding_fees": False, "top_performing": False, "attendance_today": False, "recent_activity": True, "ops_watch": True}, "kpis": ["weekly_presence", "recent_admissions", "attendance_today"], "theme": "crisp-professional", "focus_areas": ["Evidence", "Controls", "Audits"]},
}

# Per-pack overrides so same-family packs render distinctly (deep-merged over the family).
PACK_PROFILE_OVERRIDES: dict[str, dict] = {
    "school-admin-operations": {"modules": {"ops_watch": True, "outstanding_fees": True}, "kpis": ["recent_admissions", "attendance_today", "weekly_presence"]},
    "school-admin-executive": {"modules": {"overview": True, "top_performing": True}, "kpis": ["top_performing", "recent_admissions", "attendance_today"]},
    "teacher-gradebook-quick": {"modules": {"planner": False, "top_performing": True}, "kpis": ["top_performing", "attendance_today", "recent_admissions"]},
    "teacher-planner": {"modules": {"planner": True, "enrollment_trends": True}},
    "parent-payments": {"modules": {"outstanding_fees": True}, "kpis": ["recent_admissions", "attendance_today", "weekly_presence"]},
    "parent-student-progress": {"modules": {"top_performing": True}, "kpis": ["top_performing", "attendance_today", "recent_admissions"]},
    "student-focus-today": {"modules": {"planner": True, "attendance_today": True, "top_performing": False}, "kpis": ["attendance_today", "weekly_presence", "recent_admissions"]},
    "student-progress-tracker": {"modules": {"top_performing": True}, "kpis": ["top_performing", "weekly_presence", "attendance_today"]},
    "bursar-collection-rate": {"modules": {"outstanding_fees": True, "ops_watch": True}},
    "finance-office-ledger": {"modules": {"outstanding_fees": True}},
}


# PORTAL DEPTH: cockpit sections a pack hides on the parent/student/teacher shells.
# Keys match the `key=` on `partials/cockpit/_collapsable_section.html` includes (role-
# scoped, e.g. parent__* only render on the parent shell). Default-visible: a section is
# only hidden when listed here, so unassigned schools are unchanged. Lets a pack reshape
# portal CONTENT, not just chrome.
PACK_HIDDEN_SECTIONS: dict[str, list[str]] = {
    # Parent
    "parent-mobile-feed": [
        "parent__life_event_timeline",
        "parent__sibling_compare",
        "parent__activity_timeline",
        "parent__financial_timeline",
    ],
    "parent-payments": [
        "parent__achievements_card",
        "parent__teacher_spotlight_card",
        "parent__sibling_compare",
        "parent__life_event_timeline",
        "parent__year_progress",
    ],
    "parent-student-progress": [
        "parent__financial_timeline",
        "parent__sibling_compare",
        "parent__life_event_timeline",
        "parent__parent_teacher_thread",
    ],
    # Student
    "student-focus-today": [
        "student__achievements_card",
        "student__teacher_spotlight_card",
        "student__activity_timeline",
        "student__gradebook_trend",
        "student__attendance_heatmap",
        "student__realtime_presence",
    ],
    "student-progress-tracker": [
        "student__quick_actions_grid",
        "student__lesson_of_day",
        "student__ai_study_buddy",
        "student__realtime_presence",
    ],
    "student-self-service": [
        "student__achievements_card",
        "student__teacher_spotlight_card",
        "student__ai_study_buddy",
    ],
    # Teacher
    "teacher-gradebook-quick": [
        "teacher__lesson_of_day",
        "teacher__achievements_card",
        "teacher__teacher_spotlight_card",
        "teacher__activity_timeline",
        "teacher__year_progress",
    ],
    "teacher-planner": [
        "teacher__gradebook_trend",
        "teacher__attendance_heatmap",
        "teacher__realtime_presence",
    ],
    "teacher-command-center": [
        "teacher__year_progress",
        "teacher__realtime_presence",
    ],
    # Low-bandwidth / compact trims analytics-heavy cockpit rails everywhere.
    "low-bandwidth-compact": [
        "parent__life_event_timeline",
        "parent__sibling_compare",
        "parent__year_progress",
        "parent__teacher_spotlight_card",
        "student__ai_study_buddy",
        "student__realtime_presence",
        "teacher__gradebook_trend",
        "teacher__attendance_heatmap",
        "teacher__realtime_presence",
    ],
}


def hidden_sections_for(code: str) -> list[str]:
    """Cockpit section keys the pack hides on portal shells (empty = show all)."""
    return PACK_HIDDEN_SECTIONS.get(code, [])


def _merge_profile(family: str, code: str) -> dict:
    """Family profile deep-merged with the per-pack override (modules merge key-wise)."""
    base = FAMILY_DASHBOARD_PROFILE.get(family, {})
    override = PACK_PROFILE_OVERRIDES.get(code, {})
    merged = {
        "modules": {**(base.get("modules") or {}), **(override.get("modules") or {})},
        "kpis": override.get("kpis") or base.get("kpis") or [],
        "theme": override.get("theme") or base.get("theme") or "",
        "focus_areas": override.get("focus_areas") or base.get("focus_areas") or [],
    }
    return merged


def dashboard_template_for_pack(row: dict) -> tuple[str, dict]:
    """Return (template_name, config_schema) for a dashboard-pack row.

    config_schema drives BOTH chrome (header variant) and CONTENT — module visibility,
    KPI-strip priority, theme preset, and role-home focus/copy — so each pack renders a
    genuinely distinct dashboard, not just different header text.
    """
    family = row.get("family", "")
    code = row.get("code", "")
    variant = FAMILY_HEADER_VARIANT.get(family, "standard")
    profile = _merge_profile(family, code)
    config_schema = {
        "chrome": {"header_variant": variant},
        "role_home": {
            "eyebrow": row["name"],
            "purpose": row.get("description", ""),
            "focus_areas": profile["focus_areas"],
        },
        "modules": profile["modules"],
        "kpis": profile["kpis"],
        "theme": {"visual_preset": profile["theme"]} if profile["theme"] else {},
        # Portal cockpit sections this pack hides (key -> False); default-visible.
        "sections": {key: False for key in hidden_sections_for(code)},
        "source_pack": code,
    }
    return (f"{row['name']} — Default", config_schema)


# ---------------------------------------------------------------------------
# Display metadata for the per-user "Choose your dashboard" switcher (Phase 4b).
# Human labels for families / KPI ids / theme presets are the SOT the switcher +
# its preview cards read, so nothing is hardcoded in the template. pack_preview()
# is the honest, config-derived summary each preview card renders.
# ---------------------------------------------------------------------------
FAMILY_LABELS: dict[str, str] = {
    "admin": "Admin",
    "principal": "Leadership",
    "teacher": "Teaching",
    "parent": "Family",
    "student": "Student",
    "finance": "Finance",
    "it_admin": "IT",
    "compact": "Low-bandwidth",
    "counselor": "Counseling",
    "registrar": "Registrar",
    "nurse": "Health",
    "admissions": "Admissions",
    "hr": "HR",
    "transport": "Transport",
    "library": "Library",
    "boarding": "Boarding",
    "cafeteria": "Cafeteria",
    "alumni": "Alumni",
    "compliance": "Compliance",
}

# KPI ids used across FAMILY_DASHBOARD_PROFILE / PACK_PROFILE_OVERRIDES.
KPI_LABELS: dict[str, str] = {
    "recent_admissions": "Admissions",
    "attendance_today": "Attendance today",
    "top_performing": "Top performing",
    "weekly_presence": "Weekly presence",
}

# Visual preset slugs used in FAMILY_DASHBOARD_PROFILE[...]["theme"].
THEME_LABELS: dict[str, str] = {
    "crisp-professional": "Crisp",
    "soft-glass": "Soft glass",
    "high-contrast": "High contrast",
}


def family_label(family: str) -> str:
    """Human name for a pack family (falls back to a title-cased slug)."""
    key = (family or "").strip()
    if key in FAMILY_LABELS:
        return FAMILY_LABELS[key]
    return key.replace("_", " ").replace("-", " ").title() or "Other"


def kpi_label(kpi_id: str) -> str:
    """Human name for a KPI id (falls back to a title-cased slug)."""
    key = (kpi_id or "").strip()
    return KPI_LABELS.get(key, key.replace("_", " ").title())


def theme_label(theme_slug: str) -> str:
    """Human name for a visual-preset slug (falls back to a title-cased slug)."""
    key = (theme_slug or "").strip()
    return THEME_LABELS.get(key, key.replace("-", " ").replace("_", " ").title())


def pack_preview(code: str, family: str) -> dict:
    """Honest, config-derived summary for a pack's preview card.

    Every field is derived from the SAME profile that seeds the pack's
    ``DashboardTemplate.config_schema`` (via ``_merge_profile`` / ``FAMILY_HEADER_VARIANT``),
    so a preview card shows what selecting the pack actually changes — the KPIs it
    leads with, its focus areas, its theme, and its header layout variant — with no
    fabricated imagery. The mini-layout schematic is drawn by the template from
    ``kpi_count`` + ``header_variant`` + ``theme``.
    """
    profile = _merge_profile(family, code)
    kpi_ids = [k for k in (profile.get("kpis") or []) if k]
    theme_slug = profile.get("theme") or ""
    return {
        "kpis": [{"id": k, "label": kpi_label(k)} for k in kpi_ids],
        "kpi_count": len(kpi_ids),
        "focus_areas": list(profile.get("focus_areas") or []),
        "theme": theme_slug,
        "theme_label": theme_label(theme_slug),
        "header_variant": FAMILY_HEADER_VARIANT.get(family, "standard"),
    }


def apply_seed(dashboard_pack_model, dashboard_template_model) -> int:
    """Idempotent upsert of every pack + its one default template.

    Accepts the model classes (live models OR historical apps.get_model classes) so it
    can run from the seed command AND from a data migration. Returns the count of newly
    created templates. Re-running updates config_schema in place (no duplicates).
    """
    created_templates = 0
    for row in DASHBOARD_PACKS:
        pack, _ = dashboard_pack_model.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "family": row.get("family", ""),
                "description": row.get("description", ""),
                "version": "1.0",
                "is_active": True,
                "recommended_sectors": recommended_sectors_for(row),
            },
        )
        template_name, config_schema = dashboard_template_for_pack(row)
        _, tpl_created = dashboard_template_model.objects.update_or_create(
            dashboard_pack=pack,
            name=template_name,
            defaults={
                "description": row.get("description", ""),
                "config_schema": config_schema,
                "is_active": True,
            },
        )
        if tpl_created:
            created_templates += 1
    return created_templates
