"""Canonical onboarding-migration vendor catalog.

SOT for the "where is your data today?" picker in the public onboarding flow
(`onboarding_wizard` step 3) and the post-verify handoff page. Each entry maps
1:1 to a `MigrationProfile.SourceSystem` enum value when one exists, and falls
through to `OTHER` for vendors we haven't seeded a profile for yet.

Why a separate module:
- Keeps the catalog ordered + curated (twelve tiles look intentional; the raw
  enum is unordered).
- Lets us extend with marketing copy (counts, blurbs, "Quick to migrate" hints)
  without polluting the SourceSystem TextChoices.
- Single import in views + tests + templates via `{% with vendors=ONBOARDING_VENDORS %}`.

Visual treatment:
- Each vendor renders as a monogram tile + name. We do NOT use third-party logos
  (trademark concerns + visual chaos). The deterministic gradient per vendor gives
  the grid a curated-but-restrained look — Stripe / Linear school of design.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OnboardingVendor:
    """A vendor tile on the onboarding migration step."""

    slug: str                  # stable identifier; goes into session + bundle source_hint
    name: str                  # display name
    monogram: str              # two-letter glyph for the tile (e.g. "PS")
    source_system: str         # MigrationProfile.SourceSystem value (or "other")
    profile_slug: str | None   # default MigrationProfile.slug to preselect, if any
    tagline: str               # one-line marketing hint
    palette: str               # one of "ink", "indigo", "teal", "amber" — quiet four-tone rotation


# Four-tone palette rotation. Quiet, premium, no garish brand mimicry.
# Each is a CSS class hook (.ovendor-tile--ink etc.) consumed by the SCSS.
_PALETTES = ("ink", "indigo", "teal", "amber")


def _palette(index: int) -> str:
    return _PALETTES[index % len(_PALETTES)]


# Curated 12-tile grid. Order chosen for K-12 SIS market share + visual balance —
# largest incumbents first, niche vendors mid-grid, "Other" tile last so the
# fallback affordance reads as deliberate rather than default.
ONBOARDING_VENDORS: tuple[OnboardingVendor, ...] = (
    OnboardingVendor("powerschool",     "PowerSchool",          "PS", "powerschool",     "students_from_powerschool",     "K-12 SIS · widely deployed",                  _palette(0)),
    OnboardingVendor("blackbaud",       "Blackbaud",            "BB", "blackbaud",       "students_from_blackbaud",       "Education Management Solutions",              _palette(1)),
    OnboardingVendor("veracross",       "Veracross",            "VC", "veracross",       "students_from_veracross",       "Independent school SIS",                      _palette(2)),
    OnboardingVendor("infinite_campus", "Infinite Campus",      "IC", "infinite_campus", "students_from_infinite_campus", "District-scale SIS",                          _palette(3)),
    OnboardingVendor("alma",            "Alma SIS",             "AL", "alma",            "students_from_alma",            "Modern independent SIS",                      _palette(0)),
    OnboardingVendor("facts",           "FACTS / RenWeb",       "FA", "facts",           "students_from_facts",           "Faith-based + private schools",               _palette(1)),
    OnboardingVendor("skyward",         "Skyward",              "SK", "skyward",         "students_from_skyward",         "District SIS",                                _palette(2)),
    OnboardingVendor("managebac",       "ManageBac",            "MB", "other",           None,                            "IB / international curriculum",               _palette(3)),
    OnboardingVendor("toddle",          "Toddle",               "TD", "other",           None,                            "International + IB-friendly",                 _palette(0)),
    OnboardingVendor("finalsite",       "Finalsite",            "FS", "other",           None,                            "Web + portal platform",                       _palette(1)),
    OnboardingVendor("sycamore",        "Sycamore",             "SY", "other",           None,                            "K-12 SIS",                                    _palette(2)),
    OnboardingVendor("spreadsheet",     "Spreadsheets / Other", "··", "other",           None,                            "CSV, Excel, or a custom export",              _palette(3)),
)


VENDORS_BY_SLUG: dict[str, OnboardingVendor] = {v.slug: v for v in ONBOARDING_VENDORS}


def resolve_vendor(slug: str | None) -> OnboardingVendor | None:
    """Look up a vendor by its slug; returns None if missing / blank."""
    if not slug:
        return None
    return VENDORS_BY_SLUG.get(slug.strip().lower())


# Domain checklist for the post-verify handoff page. Each row maps to a
# MigrationProfile.Domain (or a synthesized one) and surfaces a complexity badge
# the operator can scan in a glance. Time estimates are conservative averages.
@dataclass(frozen=True)
class OnboardingDataDomain:
    slug: str               # stable identifier; goes into session + bundle settings
    label: str              # display name
    description: str        # short tooltip / micro-copy
    complexity: str         # one of "quick" / "standard" / "detailed"
    minutes: int            # rough setup minutes for the time tally
    default_on: bool        # pre-check in the UI
    icon: str               # Bootstrap Icons class


ONBOARDING_DATA_DOMAINS: tuple[OnboardingDataDomain, ...] = (
    OnboardingDataDomain("students",   "Students & enrollment",      "Active and prior students, demographics, year groups.",     "quick",    2, True,  "bi-mortarboard"),
    OnboardingDataDomain("staff",      "Staff & roles",              "Teachers, principals, support staff, role assignments.",    "quick",    2, True,  "bi-people"),
    OnboardingDataDomain("grades",     "Grades & evaluations",       "Marks, gradebook entries, term and final grades.",          "standard", 5, True,  "bi-graph-up"),
    OnboardingDataDomain("attendance", "Attendance records",         "Daily and period attendance, late codes, absences.",        "standard", 4, True,  "bi-calendar-check"),
    OnboardingDataDomain("fees",       "Fees & invoices",            "Tuition lines, payment plans, balances, receipts.",         "standard", 5, False, "bi-receipt"),
    OnboardingDataDomain("contacts",   "Parent / guardian contacts", "Phone, email, address, relationships to students.",         "quick",    2, True,  "bi-house-heart"),
    OnboardingDataDomain("documents",  "Documents & files",          "Report cards, transcripts, signed permission slips.",       "detailed", 7, False, "bi-folder2-open"),
    OnboardingDataDomain("schedules",  "Class schedules & timetables", "Periods, rotations, room assignments, teacher loads.",  "detailed", 7, False, "bi-table"),
)


DOMAINS_BY_SLUG: dict[str, OnboardingDataDomain] = {d.slug: d for d in ONBOARDING_DATA_DOMAINS}


def estimate_minutes(domain_slugs: list[str]) -> int:
    """Sum the estimated setup minutes for a list of domain slugs."""
    return sum(DOMAINS_BY_SLUG[s].minutes for s in domain_slugs if s in DOMAINS_BY_SLUG)
