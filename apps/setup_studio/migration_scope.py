"""Migration wizard scope domains + presets — platform-wide for all tenants.

No per-school SiteSettings gate: every tenant (past, present, future) gets the
same canonical domain list and one-click presets from code + Migration Cloud SOT.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

# Curated order — core roster domains first, extended ops last.
MIGRATION_SCOPE_DOMAIN_ORDER: tuple[str, ...] = (
    "students",
    "staff",
    "sections",
    "guardians",
    "enrollment",
    "grades",
    "attendance",
    "behavior",
    "finance",
    "transcripts",
    "health",
    "communications",
    "events",
    "library",
    "transport",
    "transport_assignments",
    "hostel",
    "hostel_assignments",
    "cafeteria",
    "cafeteria_assignments",
    "payroll",
    "alumni",
    "compliance",
)

MIGRATION_SCOPE_DOMAIN_META: dict[str, dict[str, Any]] = {
    "students": {"label": _("Students"), "unlocks": _("Roster + student profiles")},
    "staff": {"label": _("Staff"), "unlocks": _("Teacher + admin accounts")},
    "sections": {"label": _("Sections / classes"), "unlocks": _("Timetable + gradebook shell")},
    "guardians": {"label": _("Guardians"), "unlocks": _("Parent portal links")},
    "enrollment": {"label": _("Enrollment"), "unlocks": _("Active roster status")},
    "grades": {"label": _("Grades"), "unlocks": _("Gradebook + report cards")},
    "attendance": {"label": _("Attendance"), "unlocks": _("Daily attendance module")},
    "behavior": {"label": _("Behavior / incidents"), "unlocks": _("Conduct tracking")},
    "finance": {"label": _("Finance / fees"), "unlocks": _("Billing + invoices")},
    "transcripts": {"label": _("Transcripts"), "unlocks": _("Historical academic records")},
    "health": {"label": _("Health records"), "unlocks": _("Nurse / clinic module")},
    "communications": {"label": _("Communications"), "unlocks": _("Message history")},
    "events": {"label": _("Events"), "unlocks": _("School calendar data")},
    "library": {"label": _("Library"), "unlocks": _("Catalog + checkouts")},
    "transport": {"label": _("Transport routes"), "unlocks": _("Bus routes + stops")},
    "transport_assignments": {"label": _("Transport assignments"), "unlocks": _("Student route assignments")},
    "hostel": {"label": _("Hostel / boarding"), "unlocks": _("Room inventory")},
    "hostel_assignments": {"label": _("Hostel assignments"), "unlocks": _("Bed assignments")},
    "cafeteria": {"label": _("Cafeteria / meal plans"), "unlocks": _("Meal plan balances")},
    "cafeteria_assignments": {"label": _("Cafeteria assignments"), "unlocks": _("Per-student meal links")},
    "payroll": {"label": _("Payroll"), "unlocks": _("Staff payroll history")},
    "alumni": {"label": _("Alumni"), "unlocks": _("Graduate network")},
    "compliance": {"label": _("Compliance"), "unlocks": _("Policy + audit records")},
}

MIGRATION_SCOPE_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "key": "roster_starter",
        "label": _("Roster starter pack"),
        "description": _("Students, staff, and sections — fastest path to a working school"),
        "recommended": True,
        "domains": ("students", "staff", "sections"),
        "clicks": 1,
    },
    {
        "key": "full_academic",
        "label": _("Full academic import"),
        "description": _("Adds guardians and grades for gradebook-ready data"),
        "recommended": False,
        "domains": ("students", "staff", "sections", "guardians", "grades"),
        "clicks": 1,
    },
)

# Modules unlocked when domains are selected (for live preview column).
MIGRATION_SCOPE_MODULE_UNLOCKS: dict[str, tuple[str, ...]] = {
    "roster": ("students", "staff", "sections", "enrollment"),
    "gradebook": ("grades", "sections", "students"),
    "parent_portal": ("guardians", "students"),
    "attendance": ("attendance",),
    "billing": ("finance",),
    "timetable": ("sections", "staff"),
}


def build_migration_scope_choices() -> list[dict[str, Any]]:
    """Canonical migration domains for the account_migration select_scope step."""
    choices: list[dict[str, Any]] = []
    for domain in MIGRATION_SCOPE_DOMAIN_ORDER:
        meta = MIGRATION_SCOPE_DOMAIN_META.get(domain, {})
        label = meta.get("label") or domain.replace("_", " ").title()
        unlocks = meta.get("unlocks") or ""
        choices.append(
            {
                "value": domain,
                "label_token": str(label),
                "metadata": {
                    "unlocks": str(unlocks),
                    "tier": "core" if domain in {"students", "staff", "sections"} else "extended",
                },
            }
        )
    return choices


def presets_for_template() -> list[dict[str, Any]]:
    """Serialize presets for Django templates (domains as JSON-safe lists)."""
    return [
        {
            "key": p["key"],
            "label": p["label"],
            "description": p["description"],
            "recommended": bool(p.get("recommended")),
            "domains": list(p["domains"]),
            "clicks": p.get("clicks", 1),
        }
        for p in MIGRATION_SCOPE_PRESETS
    ]
