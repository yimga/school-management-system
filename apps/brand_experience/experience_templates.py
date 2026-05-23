"""ExperienceTemplate overlay registry.

Templates themselves live as PackContract entries in
``apps.platform_runtime.pack_contract.EXPERIENCE_TEMPLATE_PACKS`` so they
inherit the full pack lifecycle (preview / simulate / impact / apply / rollback /
audit) for free. This module holds the *template-specific* overlay metadata that
does not belong on the generic PackContract surface: layout family identity,
local-first country/language/profile coverage, palette + typography hints,
accessibility floor, mobile posture, and discovery tags.

Categories: operator / tenant-admin / teacher / parent / student / staff /
specialized / local-first.

Layout families are 1..10 — defined in
``docs/plans/LOCAL_FIRST_TEMPLATE_MARKETPLACE_PLAN.md`` § 6.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


LAYOUT_FAMILY_NAMES = {
    1: "executive-command",
    2: "academic-operations",
    3: "finance-control",
    4: "family-engagement",
    5: "teacher-productivity",
    6: "student-progress",
    7: "migration-readiness",
    8: "security-compliance",
    9: "low-connectivity-compact",
    10: "premium-international",
}

PALETTE_FAMILIES = (
    "editorial-cream",
    "warm-terracotta",
    "cool-indigo",
    "green-emerald",
    "desert-amber",
    "monsoon-teal",
    "sakura-blush",
    "andes-clay",
    "savanna-ochre",
    "nordic-slate",
)

TYPOGRAPHY_STACKS = (
    "stack-editorial-serif",
    "stack-system-sans",
    "stack-bilingual-mixed",
)

ACCESSIBILITY_FLOOR = "AA"
ACCESSIBILITY_LEVELS = {"AA", "AAA", "partial"}
MOBILE_LEVELS = {"mobile-first", "responsive", "desktop-only"}


@dataclass(frozen=True)
class ExperienceTemplateOverlay:
    """Template-specific metadata layered over PackContract."""

    key: str
    category: str
    layout_family: int
    palette_family: str
    typography_stack: str
    accessibility_level: str
    mobile_level: str
    supported_countries: tuple[str, ...]
    supported_languages: tuple[str, ...]
    local_profile_ref: str
    preview_template: str
    thumbnail: str
    tags: tuple[str, ...] = field(default_factory=tuple)

    def is_local_first(self) -> bool:
        return self.category == "local-first" and bool(self.local_profile_ref)

    def is_operator_only(self) -> bool:
        return self.category == "operator"

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "category": self.category,
            "layout_family": self.layout_family,
            "layout_family_name": LAYOUT_FAMILY_NAMES.get(self.layout_family, "unknown"),
            "palette_family": self.palette_family,
            "typography_stack": self.typography_stack,
            "accessibility_level": self.accessibility_level,
            "mobile_level": self.mobile_level,
            "supported_countries": list(self.supported_countries),
            "supported_languages": list(self.supported_languages),
            "local_profile_ref": self.local_profile_ref,
            "preview_template": self.preview_template,
            "thumbnail": self.thumbnail,
            "tags": list(self.tags),
            "is_local_first": self.is_local_first(),
            "is_operator_only": self.is_operator_only(),
        }


def _o(
    key: str,
    category: str,
    family: int,
    palette: str,
    *,
    countries: tuple[str, ...] = ("*",),
    languages: tuple[str, ...] = ("*",),
    typography: str = "stack-system-sans",
    accessibility: str = "AA",
    mobile: str = "responsive",
    local_profile: str = "",
    tags: tuple[str, ...] = (),
) -> ExperienceTemplateOverlay:
    return ExperienceTemplateOverlay(
        key=key,
        category=category,
        layout_family=family,
        palette_family=palette,
        typography_stack=typography,
        accessibility_level=accessibility,
        mobile_level=mobile,
        supported_countries=countries,
        supported_languages=languages,
        local_profile_ref=local_profile,
        preview_template=f"marketplace/previews/{key}.html",
        thumbnail=f"img/template-thumbs/{key}.svg",
        tags=tags,
    )


OVERLAYS: tuple[ExperienceTemplateOverlay, ...] = (
    # A. Operator / Manager (10) — cool-indigo
    _o("operator-executive-command-center", "operator", 1, "cool-indigo", tags=("executive", "premium", "data-rich")),
    _o("operator-implementation-war-room", "operator", 7, "cool-indigo", tags=("operations", "data-rich")),
    _o("operator-support-cockpit", "operator", 1, "cool-indigo", tags=("operations",)),
    _o("operator-revenue-billing-ops", "operator", 3, "cool-indigo", tags=("finance", "data-rich")),
    _o("operator-security-compliance-command", "operator", 8, "cool-indigo", tags=("compliance", "data-rich")),
    _o("operator-migration-ops-center", "operator", 7, "cool-indigo", tags=("operations",)),
    _o("operator-marketplace-console", "operator", 1, "cool-indigo", tags=("operations",)),
    _o("operator-observability-health", "operator", 8, "cool-indigo", tags=("operations", "data-rich")),
    _o("operator-tenant-lifecycle-command", "operator", 1, "cool-indigo", tags=("operations",)),
    _o("operator-ai-intelligence-console", "operator", 8, "cool-indigo", tags=("operations", "premium")),
    # B. Tenant Admin (8) — green-emerald (warm + operations)
    _o("admin-school-command-center", "tenant-admin", 1, "green-emerald", tags=("premium", "executive")),
    _o("admin-launch-readiness-cockpit", "tenant-admin", 7, "green-emerald", tags=("operations",)),
    _o("admin-academic-ops-hub", "tenant-admin", 2, "green-emerald", tags=("academic",)),
    _o("admin-finance-fees-hub", "tenant-admin", 3, "cool-indigo", tags=("finance",)),
    _o("admin-staff-ops-hub", "tenant-admin", 1, "green-emerald", tags=("operations",)),
    _o("admin-family-engagement-hub", "tenant-admin", 4, "green-emerald", tags=("parent-friendly",)),
    _o("admin-data-quality-control-room", "tenant-admin", 8, "nordic-slate", tags=("data-rich",)),
    _o("admin-low-connectivity-hub", "tenant-admin", 9, "nordic-slate", mobile="mobile-first", tags=("low-connectivity", "compact", "mobile-first")),
    # C. Teacher (8) — green-emerald
    _o("teacher-daily-workspace", "teacher", 5, "green-emerald", tags=("teacher-focused",)),
    _o("teacher-class-performance-studio", "teacher", 2, "green-emerald", tags=("teacher-focused", "data-rich")),
    _o("teacher-attendance-marks-fast-desk", "teacher", 5, "green-emerald", tags=("teacher-focused", "compact")),
    _o("teacher-parent-comms-desk", "teacher", 5, "green-emerald", tags=("teacher-focused",)),
    _o("teacher-lesson-syllabus-control", "teacher", 2, "green-emerald", tags=("teacher-focused", "academic")),
    _o("teacher-student-risk-monitor", "teacher", 5, "green-emerald", tags=("teacher-focused",)),
    _o("teacher-assessment-publishing", "teacher", 2, "green-emerald", tags=("teacher-focused", "academic")),
    _o("teacher-mobile-compact", "teacher", 9, "nordic-slate", mobile="mobile-first", tags=("teacher-focused", "mobile-first", "low-connectivity")),
    # D. Parent (6) — warm-terracotta
    _o("parent-family-home", "parent", 4, "warm-terracotta", tags=("parent-friendly",)),
    _o("parent-student-progress", "parent", 6, "warm-terracotta", tags=("parent-friendly",)),
    _o("parent-fees-payments-family", "parent", 3, "warm-terracotta", tags=("parent-friendly", "finance")),
    _o("parent-attendance-behavior", "parent", 4, "warm-terracotta", tags=("parent-friendly",)),
    _o("parent-comms-hub", "parent", 4, "warm-terracotta", tags=("parent-friendly",)),
    _o("parent-multi-child", "parent", 4, "warm-terracotta", tags=("parent-friendly",)),
    # E. Student (6) — green-emerald
    _o("student-home", "student", 6, "green-emerald", tags=("student-friendly",)),
    _o("student-assignments-results", "student", 6, "green-emerald", tags=("student-friendly", "academic")),
    _o("student-attendance-schedule", "student", 6, "green-emerald", tags=("student-friendly",)),
    _o("student-learning-progress", "student", 6, "green-emerald", tags=("student-friendly",)),
    _o("student-help-support", "student", 6, "green-emerald", tags=("student-friendly",)),
    _o("student-mobile-minimal", "student", 9, "nordic-slate", mobile="mobile-first", tags=("student-friendly", "mobile-first", "minimal")),
    # F. Staff (4) — nordic-slate
    _o("staff-home", "staff", 1, "nordic-slate", tags=("operations",)),
    _o("staff-hr-payroll", "staff", 1, "nordic-slate", tags=("operations",)),
    _o("staff-operations", "staff", 1, "nordic-slate", tags=("operations",)),
    _o("staff-transport-canteen-hostel", "staff", 1, "nordic-slate", tags=("operations",)),
    # G. Specialized (8)
    _o("specialized-boarding-school-ops", "specialized", 10, "editorial-cream", tags=("premium", "luxury")),
    _o("specialized-bilingual-school", "specialized", 10, "editorial-cream", typography="stack-bilingual-mixed", tags=("bilingual", "premium")),
    _o("specialized-international-school", "specialized", 10, "editorial-cream", typography="stack-editorial-serif", tags=("premium", "luxury")),
    _o("specialized-low-connectivity-regional", "specialized", 9, "savanna-ochre", mobile="mobile-first", tags=("low-connectivity", "compact")),
    _o("specialized-private-primary", "specialized", 4, "warm-terracotta", tags=("parent-friendly", "premium")),
    _o("specialized-private-secondary", "specialized", 2, "green-emerald", tags=("academic", "premium")),
    _o("specialized-faith-inspired-neutral", "specialized", 4, "editorial-cream", tags=("premium",)),
    _o("specialized-community-day-school", "specialized", 4, "warm-terracotta", tags=("parent-friendly",)),
    # H. Local-First Regional (25)
    _o("local-cm-anglophone-private-secondary", "local-first", 2, "warm-terracotta", countries=("CM",), languages=("en", "fr"), typography="stack-bilingual-mixed", local_profile="cm-anglophone-gce", tags=("heritage", "bilingual")),
    _o("local-ng-private-secondary", "local-first", 2, "warm-terracotta", countries=("NG",), languages=("en",), local_profile="ng-private-secondary", tags=("heritage",)),
    _o("local-gh-private-school", "local-first", 4, "warm-terracotta", countries=("GH",), languages=("en",), local_profile="gh-private-school", tags=("heritage",)),
    _o("local-ke-primary-secondary", "local-first", 4, "savanna-ochre", countries=("KE",), languages=("en", "sw"), typography="stack-bilingual-mixed", local_profile="ke-cbc-primary-secondary", tags=("heritage", "bilingual")),
    _o("local-za-provincial", "local-first", 2, "savanna-ochre", countries=("ZA",), languages=("en", "af", "zu"), local_profile="za-provincial-grades", tags=("heritage",)),
    _o("local-cm-francophone-bac", "local-first", 2, "warm-terracotta", countries=("CM",), languages=("fr", "en"), typography="stack-bilingual-mixed", local_profile="cm-francophone-bac", tags=("heritage", "bilingual")),
    _o("local-ci-private-college", "local-first", 2, "warm-terracotta", countries=("CI",), languages=("fr",), local_profile="ci-bac-francophone", tags=("heritage",)),
    _o("local-sn-private-lycee", "local-first", 2, "warm-terracotta", countries=("SN",), languages=("fr", "wo"), typography="stack-bilingual-mixed", local_profile="sn-bac-francophone", tags=("heritage", "bilingual")),
    _o("local-ma-private-school", "local-first", 2, "desert-amber", countries=("MA",), languages=("ar", "fr"), typography="stack-bilingual-mixed", local_profile="ma-bac-bilingual", tags=("heritage", "bilingual")),
    _o("local-in-cbse-private", "local-first", 2, "monsoon-teal", countries=("IN",), languages=("hi", "en"), typography="stack-bilingual-mixed", local_profile="in-cbse-hindi-medium", tags=("heritage", "bilingual")),
    _o("local-in-ka-state-board", "local-first", 2, "monsoon-teal", countries=("IN",), languages=("kn", "en"), typography="stack-bilingual-mixed", local_profile="in-ka-state-board", tags=("heritage", "bilingual")),
    _o("local-pk-private-school", "local-first", 2, "desert-amber", countries=("PK",), languages=("ur", "en"), typography="stack-bilingual-mixed", local_profile="pk-fbise-urdu-medium", tags=("heritage", "bilingual")),
    _o("local-bd-private-school", "local-first", 2, "monsoon-teal", countries=("BD",), languages=("bn", "en"), typography="stack-bilingual-mixed", local_profile="bd-sec-edu-bengali", tags=("heritage", "bilingual")),
    _o("local-jp-international-private", "local-first", 10, "sakura-blush", countries=("JP",), languages=("ja", "en"), typography="stack-bilingual-mixed", local_profile="jp-mext-bilingual", tags=("heritage", "premium", "bilingual")),
    _o("local-kr-international-private", "local-first", 10, "sakura-blush", countries=("KR",), languages=("ko", "en"), typography="stack-bilingual-mixed", local_profile="kr-international-bilingual", tags=("heritage", "premium", "bilingual")),
    _o("local-cn-bilingual-private", "local-first", 10, "sakura-blush", countries=("CN",), languages=("zh-Hans", "en"), typography="stack-bilingual-mixed", local_profile="cn-bilingual-private", tags=("heritage", "premium", "bilingual")),
    _o("local-ph-private-school", "local-first", 4, "warm-terracotta", countries=("PH",), languages=("en", "tl"), typography="stack-bilingual-mixed", local_profile="ph-deped-k12", tags=("heritage", "bilingual")),
    _o("local-my-private-school", "local-first", 2, "monsoon-teal", countries=("MY",), languages=("en", "ms"), typography="stack-bilingual-mixed", local_profile="my-igcse-bilingual", tags=("heritage", "bilingual")),
    _o("local-id-private-school", "local-first", 4, "monsoon-teal", countries=("ID",), languages=("id", "en"), typography="stack-bilingual-mixed", local_profile="id-private-bilingual", tags=("heritage", "bilingual")),
    _o("local-us-charter", "local-first", 2, "cool-indigo", countries=("US",), languages=("en", "es"), local_profile="us-charter-state", tags=("heritage",)),
    _o("local-uk-cambridge-international", "local-first", 10, "editorial-cream", countries=("GB",), languages=("en",), typography="stack-editorial-serif", local_profile="gb-igcse-a-level", tags=("heritage", "premium", "luxury")),
    _o("local-au-private-day", "local-first", 2, "cool-indigo", countries=("AU",), languages=("en",), local_profile="au-state-curriculum", tags=("heritage",)),
    _o("local-ae-gulf-international", "local-first", 10, "desert-amber", countries=("AE",), languages=("ar", "en"), typography="stack-bilingual-mixed", local_profile="ae-cbse-or-british", tags=("heritage", "premium", "bilingual")),
    _o("local-mx-private-bilingual", "local-first", 10, "andes-clay", countries=("MX",), languages=("es", "en"), typography="stack-bilingual-mixed", local_profile="mx-sep-bilingual", tags=("heritage", "premium", "bilingual")),
    _o("local-br-private-bilingual", "local-first", 10, "andes-clay", countries=("BR",), languages=("pt", "en"), typography="stack-bilingual-mixed", local_profile="br-mec-bilingual", tags=("heritage", "premium", "bilingual")),
)


_OVERLAY_INDEX: dict[str, ExperienceTemplateOverlay] = {o.key: o for o in OVERLAYS}


def get_overlay(template_key: str) -> ExperienceTemplateOverlay | None:
    return _OVERLAY_INDEX.get(template_key)


def list_overlays(
    *,
    category: str | None = None,
    country: str | None = None,
    language: str | None = None,
    tenant_safe_only: bool = False,
) -> list[dict]:
    rows = [o for o in OVERLAYS]
    if category:
        rows = [r for r in rows if r.category == category]
    if country:
        cc = country.strip().upper()
        rows = [r for r in rows if "*" in r.supported_countries or cc in r.supported_countries]
    if language:
        lc = language.strip().lower()
        rows = [r for r in rows if "*" in r.supported_languages or lc in [s.lower() for s in r.supported_languages]]
    if tenant_safe_only:
        rows = [r for r in rows if not r.is_operator_only()]
    return [r.as_dict() for r in rows]


def overlay_keys() -> Iterable[str]:
    return _OVERLAY_INDEX.keys()


def assert_registry_invariants() -> None:
    """Raise AssertionError if registry shape regresses. Run from verifier."""
    if len(OVERLAYS) != 75:
        raise AssertionError(f"Expected exactly 75 ExperienceTemplate overlays, got {len(OVERLAYS)}")
    keys = [o.key for o in OVERLAYS]
    if len(set(keys)) != len(keys):
        raise AssertionError("Duplicate ExperienceTemplate overlay keys detected.")
    for o in OVERLAYS:
        if o.layout_family not in LAYOUT_FAMILY_NAMES:
            raise AssertionError(f"Template {o.key}: layout_family {o.layout_family} not in 1..10")
        if o.palette_family not in PALETTE_FAMILIES:
            raise AssertionError(f"Template {o.key}: palette_family {o.palette_family} not registered")
        if o.typography_stack not in TYPOGRAPHY_STACKS:
            raise AssertionError(f"Template {o.key}: typography_stack {o.typography_stack} not registered")
        if o.accessibility_level not in ACCESSIBILITY_LEVELS:
            raise AssertionError(f"Template {o.key}: accessibility_level {o.accessibility_level} invalid")
        if o.mobile_level not in MOBILE_LEVELS:
            raise AssertionError(f"Template {o.key}: mobile_level {o.mobile_level} invalid")
        if o.category == "local-first" and not o.local_profile_ref:
            raise AssertionError(f"Template {o.key}: local-first templates must reference a LocalExperienceProfile")
