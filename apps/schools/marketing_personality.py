"""
Marketing page personality registry — one visual identity per route family.

Each personality drives CSS tokens on ``[data-mkt-personality]`` (accent, hero wash,
card chrome, eyebrow motif) and seeds interactive viz panels via
``apps.schools.marketing_personality_seeds``.

OS matrices (RUN / TEACH / PAY / COMMUNICATE) group operational domains with shared
viz engines but distinct per-page accents.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

OsMatrix = Literal["run", "teach", "pay", "communicate", "neutral"]


class MarketingPersonality(TypedDict):
    id: str
    label: str
    accent: str
    accent_ink: str
    accent_soft: str
    hero_tone: str
    eyebrow_motif: str
    card_variant: str
    os_matrix: OsMatrix
    viz_engine: str


def _hex_luminance(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    rgb = [int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    channels = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb
    ]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = _hex_luminance(fg), _hex_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _accent_ink_for_contrast(accent: str, bg: str = "#faf7f2", target: float = 7.0) -> str:
    """Derive eyebrow-safe ink from accent (WCAG 2.2 AAA 7:1 on marketing cream)."""
    if _contrast_ratio(accent, bg) >= target:
        return accent
    raw = accent.lstrip("#")
    rgb = [int(raw[i : i + 2], 16) for i in (0, 2, 4)]
    for step in range(24):
        rgb = [max(0, int(c * 0.88)) for c in rgb]
        candidate = "#{:02x}{:02x}{:02x}".format(*rgb)
        if _contrast_ratio(candidate, bg) >= target:
            return candidate
    return "#1c1917"


def _p(
    pid: str,
    *,
    label: str,
    accent: str,
    accent_soft: str,
    hero_tone: str,
    eyebrow_motif: str,
    card_variant: str,
    os_matrix: OsMatrix = "neutral",
    viz_engine: str = "sparkline-generic",
) -> MarketingPersonality:
    return MarketingPersonality(
        id=pid,
        label=label,
        accent=accent,
        accent_ink=_accent_ink_for_contrast(accent),
        accent_soft=accent_soft,
        hero_tone=hero_tone,
        eyebrow_motif=eyebrow_motif,
        card_variant=card_variant,
        os_matrix=os_matrix,
        viz_engine=viz_engine,
    )


# ── 4 Core Product OS matrices (parent lane personalities) ──
_OS_RUN = "run"
_OS_TEACH = "teach"
_OS_PAY = "pay"
_OS_COMM = "communicate"

_PERSONALITIES: dict[str, MarketingPersonality] = {
    "home": _p(
        "home",
        label="Home",
        accent="#c2410c",
        accent_soft="rgba(194, 65, 12, 0.08)",
        hero_tone="editorial-warm",
        eyebrow_motif="bell",
        card_variant="editorial",
        viz_engine="campus-pulse",
    ),
    "platform-hub": _p(
        "platform-hub",
        label="Platform",
        accent="#4f46e5",
        accent_soft="rgba(79, 70, 229, 0.1)",
        hero_tone="module-grid",
        eyebrow_motif="grid",
        card_variant="module",
        os_matrix=_OS_RUN,
        viz_engine="run-gauge",
    ),
    "solutions-hub": _p(
        "solutions-hub",
        label="Solutions",
        accent="#059669",
        accent_soft="rgba(5, 150, 105, 0.1)",
        hero_tone="role-tabs",
        eyebrow_motif="people",
        card_variant="persona",
        viz_engine="persona-radar",
    ),
    "solutions-persona": _p(
        "solutions-persona",
        label="Role story",
        accent="#7c3aed",
        accent_soft="rgba(124, 58, 237, 0.1)",
        hero_tone="role-story",
        eyebrow_motif="tuesday",
        card_variant="story",
        viz_engine="day-role-story",
    ),
    "solutions-higher-ed": _p(
        "solutions-higher-ed",
        label="Higher education",
        accent="#1e3a8a",
        accent_soft="rgba(30, 58, 138, 0.1)",
        hero_tone="provost",
        eyebrow_motif="research",
        card_variant="research",
        viz_engine="provost-research",
    ),
    "solutions-k12-districts": _p(
        "solutions-k12-districts",
        label="K-12 districts",
        accent="#166534",
        accent_soft="rgba(22, 101, 52, 0.1)",
        hero_tone="board",
        eyebrow_motif="governance",
        card_variant="compliance",
        viz_engine="board-compliance",
    ),
    "pricing": _p(
        "pricing",
        label="Pricing",
        accent="#d97706",
        accent_soft="rgba(217, 119, 6, 0.1)",
        hero_tone="ledger",
        eyebrow_motif="plans",
        card_variant="tier",
        os_matrix=_OS_PAY,
        viz_engine="pricing-matrix",
    ),
    "trust": _p(
        "trust",
        label="Trust",
        accent="#0369a1",
        accent_soft="rgba(3, 105, 161, 0.1)",
        hero_tone="shield",
        eyebrow_motif="compliance",
        card_variant="pillar",
        viz_engine="trust-ledger",
    ),
    "security-matrix": _p(
        "security-matrix",
        label="Security matrix",
        accent="#be123c",
        accent_soft="rgba(190, 18, 60, 0.1)",
        hero_tone="rbac-grid",
        eyebrow_motif="permissions",
        card_variant="matrix",
        os_matrix=_OS_RUN,
        viz_engine="rbac-matrix",
    ),
    "migrate": _p(
        "migrate",
        label="Migration",
        accent="#0d9488",
        accent_soft="rgba(13, 148, 136, 0.1)",
        hero_tone="pathway",
        eyebrow_motif="timeline",
        card_variant="step",
        viz_engine="migration-switch",
    ),
    "compare": _p(
        "compare",
        label="Compare",
        accent="#64748b",
        accent_soft="rgba(100, 116, 139, 0.12)",
        hero_tone="split",
        eyebrow_motif="versus",
        card_variant="contrast",
        viz_engine="compare-split",
    ),
    "company": _p(
        "company",
        label="Company",
        accent="#92400e",
        accent_soft="rgba(146, 64, 14, 0.08)",
        hero_tone="human",
        eyebrow_motif="story",
        card_variant="narrative",
        viz_engine="timeline-corporate",
    ),
    "about": _p(
        "about",
        label="About",
        accent="#78350f",
        accent_soft="rgba(120, 53, 15, 0.08)",
        hero_tone="history",
        eyebrow_motif="growth",
        card_variant="narrative",
        viz_engine="timeline-corporate",
    ),
    "careers": _p(
        "careers",
        label="Careers",
        accent="#0e7490",
        accent_soft="rgba(14, 116, 144, 0.1)",
        hero_tone="engineering",
        eyebrow_motif="stack",
        card_variant="code",
        viz_engine="stack-selector",
    ),
    "brand-assets": _p(
        "brand-assets",
        label="Brand assets",
        accent="#db2777",
        accent_soft="rgba(219, 39, 119, 0.1)",
        hero_tone="swatch",
        eyebrow_motif="palette",
        card_variant="asset",
        viz_engine="brand-swatches",
    ),
    "resources": _p(
        "resources",
        label="Resources",
        accent="#4338ca",
        accent_soft="rgba(67, 56, 202, 0.1)",
        hero_tone="library",
        eyebrow_motif="guides",
        card_variant="catalog",
        viz_engine="kb-search",
    ),
    "resources-help-center": _p(
        "resources-help-center",
        label="Knowledge base",
        accent="#4c1d95",
        accent_soft="rgba(76, 29, 149, 0.1)",
        hero_tone="search",
        eyebrow_motif="ai-room",
        card_variant="catalog",
        viz_engine="kb-search",
    ),
    "developers": _p(
        "developers",
        label="Developers",
        accent="#0e7490",
        accent_soft="rgba(14, 116, 144, 0.12)",
        hero_tone="terminal",
        eyebrow_motif="api",
        card_variant="code",
        viz_engine="api-playground",
    ),
    "demo": _p(
        "demo",
        label="Demo",
        accent="#ea580c",
        accent_soft="rgba(234, 88, 12, 0.1)",
        hero_tone="action",
        eyebrow_motif="calendar",
        card_variant="form",
        viz_engine="wizard-steps",
    ),
    "contact": _p(
        "contact",
        label="Contact",
        accent="#1f2937",
        accent_soft="rgba(31, 41, 55, 0.06)",
        hero_tone="minimal",
        eyebrow_motif="inbox",
        card_variant="plain",
        viz_engine="inbox-queue",
    ),
    "portal-login": _p(
        "portal-login",
        label="Portal login",
        accent="#334155",
        accent_soft="rgba(51, 65, 85, 0.08)",
        hero_tone="secure-gateway",
        eyebrow_motif="mfa",
        card_variant="plain",
        viz_engine="secure-gateway",
    ),
    "find-campus": _p(
        "find-campus",
        label="Find your campus",
        accent="#0284c7",
        accent_soft="rgba(2, 132, 199, 0.1)",
        hero_tone="geo",
        eyebrow_motif="map-pin",
        card_variant="finder",
        viz_engine="geo-finder",
    ),
    "implementation-timelines": _p(
        "implementation-timelines",
        label="Implementation",
        accent="#0f766e",
        accent_soft="rgba(15, 118, 110, 0.1)",
        hero_tone="gantt",
        eyebrow_motif="milestones",
        card_variant="step",
        viz_engine="gantt-rollout",
    ),
    "procurement-docs": _p(
        "procurement-docs",
        label="Procurement",
        accent="#57534e",
        accent_soft="rgba(87, 83, 78, 0.1)",
        hero_tone="repository",
        eyebrow_motif="contract",
        card_variant="document",
        viz_engine="procurement-repo",
    ),
    "system-status": _p(
        "system-status",
        label="System status",
        accent="#dc2626",
        accent_soft="rgba(220, 38, 38, 0.1)",
        hero_tone="incident",
        eyebrow_motif="uptime",
        card_variant="status",
        os_matrix=_OS_RUN,
        viz_engine="incident-monitor",
    ),
    "infrastructure-map": _p(
        "infrastructure-map",
        label="Infrastructure",
        accent="#0891b2",
        accent_soft="rgba(8, 145, 178, 0.12)",
        hero_tone="topology",
        eyebrow_motif="nodes",
        card_variant="map",
        os_matrix=_OS_RUN,
        viz_engine="infra-map",
    ),
    "hardware-store": _p(
        "hardware-store",
        label="Hardware store",
        accent="#52525b",
        accent_soft="rgba(82, 82, 91, 0.1)",
        hero_tone="commerce",
        eyebrow_motif="spec",
        card_variant="product",
        viz_engine="product-grid",
    ),
    "training-academies": _p(
        "training-academies",
        label="Training academies",
        accent="#7c2d12",
        accent_soft="rgba(124, 45, 18, 0.1)",
        hero_tone="lms",
        eyebrow_motif="progress",
        card_variant="course",
        os_matrix=_OS_TEACH,
        viz_engine="lms-progress",
    ),
    "teacher-communities": _p(
        "teacher-communities",
        label="Teacher communities",
        accent="#6d28d9",
        accent_soft="rgba(109, 40, 217, 0.1)",
        hero_tone="forum",
        eyebrow_motif="thread",
        card_variant="discussion",
        os_matrix=_OS_TEACH,
        viz_engine="thread-board",
    ),
    "lesson-planning": _p(
        "lesson-planning",
        label="Lesson planning",
        accent="#15803d",
        accent_soft="rgba(21, 128, 61, 0.1)",
        hero_tone="canvas",
        eyebrow_motif="blocks",
        card_variant="template",
        os_matrix=_OS_TEACH,
        viz_engine="template-canvas",
    ),
    "legal-ferpa": _p(
        "legal-ferpa",
        label="FERPA",
        accent="#1d4ed8",
        accent_soft="rgba(29, 78, 216, 0.1)",
        hero_tone="legal",
        eyebrow_motif="records",
        card_variant="ledger",
        viz_engine="legal-records",
    ),
    "legal-coppa": _p(
        "legal-coppa",
        label="COPPA",
        accent="#c026d3",
        accent_soft="rgba(192, 38, 211, 0.1)",
        hero_tone="child-safety",
        eyebrow_motif="consent",
        card_variant="ledger",
        viz_engine="legal-consent",
    ),
    "legal-gdpr": _p(
        "legal-gdpr",
        label="GDPR",
        accent="#2563eb",
        accent_soft="rgba(37, 99, 235, 0.1)",
        hero_tone="privacy",
        eyebrow_motif="dsar",
        card_variant="ledger",
        viz_engine="privacy-dashboard",
    ),
    "legal-wcag": _p(
        "legal-wcag",
        label="WCAG",
        accent="#059669",
        accent_soft="rgba(5, 150, 105, 0.1)",
        hero_tone="a11y",
        eyebrow_motif="conformance",
        card_variant="matrix",
        viz_engine="a11y-matrix",
    ),
    "legal-terms": _p(
        "legal-terms",
        label="Terms",
        accent="#374151",
        accent_soft="rgba(55, 65, 81, 0.08)",
        hero_tone="document",
        eyebrow_motif="clause",
        card_variant="document",
        viz_engine="legal-document",
    ),
    "legal-cookie": _p(
        "legal-cookie",
        label="Cookie policy",
        accent="#a16207",
        accent_soft="rgba(161, 98, 7, 0.1)",
        hero_tone="tracker",
        eyebrow_motif="tags",
        card_variant="matrix",
        viz_engine="cookie-matrix",
    ),
    "lane-academics": _p(
        "lane-academics",
        label="Academics",
        accent="#059669",
        accent_soft="rgba(5, 150, 105, 0.1)",
        hero_tone="timetable",
        eyebrow_motif="bell-schedule",
        card_variant="matrix",
        os_matrix=_OS_TEACH,
        viz_engine="teach-engagement",
    ),
    "lane-admissions": _p(
        "lane-admissions",
        label="Admissions",
        accent="#4f46e5",
        accent_soft="rgba(79, 70, 229, 0.1)",
        hero_tone="pipeline",
        eyebrow_motif="funnel",
        card_variant="pipeline",
        os_matrix=_OS_COMM,
        viz_engine="communicate-feed",
    ),
    "lane-finance": _p(
        "lane-finance",
        label="Finance",
        accent="#d97706",
        accent_soft="rgba(217, 119, 6, 0.1)",
        hero_tone="ledger-bars",
        eyebrow_motif="receipt",
        card_variant="ledger",
        os_matrix=_OS_PAY,
        viz_engine="pay-ledger",
    ),
}

_PLATFORM_PERSONALITIES: dict[str, MarketingPersonality] = {
    "platform-admissions": _p(
        "platform-admissions",
        label="Admissions",
        accent="#22c55e",
        accent_soft="rgba(34, 197, 94, 0.1)",
        hero_tone="pipeline",
        eyebrow_motif="funnel",
        card_variant="pipeline",
        os_matrix=_OS_COMM,
        viz_engine="communicate-feed",
    ),
    "platform-fees-payments": _p(
        "platform-fees-payments",
        label="Fees & payments",
        accent="#ca8a04",
        accent_soft="rgba(202, 138, 4, 0.12)",
        hero_tone="ledger-bars",
        eyebrow_motif="receipt",
        card_variant="ledger",
        os_matrix=_OS_PAY,
        viz_engine="pay-ledger",
    ),
    "platform-student-information-system": _p(
        "platform-student-information-system",
        label="Student information",
        accent="#2563eb",
        accent_soft="rgba(37, 99, 235, 0.12)",
        hero_tone="timetable",
        eyebrow_motif="bell-schedule",
        card_variant="matrix",
        os_matrix=_OS_TEACH,
        viz_engine="teach-engagement",
    ),
    "platform-attendance": _p(
        "platform-attendance",
        label="Attendance",
        accent="#047857",
        accent_soft="rgba(4, 120, 87, 0.12)",
        hero_tone="roll-call",
        eyebrow_motif="present",
        card_variant="matrix",
        os_matrix=_OS_TEACH,
        viz_engine="attendance-spark",
    ),
    "platform-analytics": _p(
        "platform-analytics",
        label="Analytics",
        accent="#c47f1c",
        accent_soft="rgba(196, 127, 28, 0.12)",
        hero_tone="chart",
        eyebrow_motif="signal",
        card_variant="metric",
        os_matrix=_OS_RUN,
        viz_engine="run-gauge",
    ),
    "platform-security": _p(
        "platform-security",
        label="Security",
        accent="#f472b6",
        accent_soft="rgba(244, 114, 182, 0.12)",
        hero_tone="shield",
        eyebrow_motif="compliance",
        card_variant="pillar",
        os_matrix=_OS_RUN,
        viz_engine="trust-ledger",
    ),
    "platform-parent-portal": _p(
        "platform-parent-portal",
        label="Parent portal",
        accent="#6d28d9",
        accent_soft="rgba(109, 40, 217, 0.12)",
        hero_tone="inbox",
        eyebrow_motif="family",
        card_variant="message",
        os_matrix=_OS_COMM,
        viz_engine="family-guide",
    ),
    "platform-teacher-portal": _p(
        "platform-teacher-portal",
        label="Teacher portal",
        accent="#0369a1",
        accent_soft="rgba(3, 105, 161, 0.12)",
        hero_tone="classroom",
        eyebrow_motif="bell-schedule",
        card_variant="matrix",
        os_matrix=_OS_TEACH,
        viz_engine="classroom-roster",
    ),
    "platform-student-portal": _p(
        "platform-student-portal",
        label="Student portal",
        accent="#0f766e",
        accent_soft="rgba(45, 212, 191, 0.12)",
        hero_tone="learner",
        eyebrow_motif="path",
        card_variant="story",
        os_matrix=_OS_TEACH,
        viz_engine="gamified-learner",
    ),
    "platform-communications": _p(
        "platform-communications",
        label="Communications",
        accent="#6366f1",
        accent_soft="rgba(99, 102, 241, 0.12)",
        hero_tone="inbox",
        eyebrow_motif="thread",
        card_variant="message",
        os_matrix=_OS_COMM,
        viz_engine="communicate-feed",
    ),
    "platform-workflows": _p(
        "platform-workflows",
        label="Workflows",
        accent="#c084fc",
        accent_soft="rgba(192, 132, 252, 0.12)",
        hero_tone="flow",
        eyebrow_motif="step",
        card_variant="step",
        os_matrix=_OS_RUN,
        viz_engine="workflow-flow",
    ),
    "platform-offline-first": _p(
        "platform-offline-first",
        label="Offline-first",
        accent="#14b8a6",
        accent_soft="rgba(20, 184, 166, 0.12)",
        hero_tone="sync",
        eyebrow_motif="signal",
        card_variant="plain",
        viz_engine="sync-pulse",
    ),
    "platform-grading-report-cards": _p(
        "platform-grading-report-cards",
        label="Grading",
        accent="#fbbf24",
        accent_soft="rgba(251, 191, 36, 0.12)",
        hero_tone="report",
        eyebrow_motif="marks",
        card_variant="tier",
        os_matrix=_OS_TEACH,
        viz_engine="grade-distribution",
    ),
    "platform-migration-cloud": _p(
        "platform-migration-cloud",
        label="Migration Cloud",
        accent="#0d9488",
        accent_soft="rgba(13, 148, 136, 0.1)",
        hero_tone="pathway",
        eyebrow_motif="timeline",
        card_variant="step",
        viz_engine="migration-path",
    ),
    "platform-marketplace": _p(
        "platform-marketplace",
        label="Marketplace",
        accent="#8b5cf6",
        accent_soft="rgba(139, 92, 246, 0.12)",
        hero_tone="ecosystem",
        eyebrow_motif="apps",
        card_variant="module",
        viz_engine="app-catalog",
    ),
    "platform-control-plane": _p(
        "platform-control-plane",
        label="Control plane",
        accent="#1e293b",
        accent_soft="rgba(30, 41, 59, 0.08)",
        hero_tone="operator",
        eyebrow_motif="governance",
        card_variant="pillar",
        os_matrix=_OS_RUN,
        viz_engine="run-gauge",
    ),
    "platform-education-os": _p(
        "platform-education-os",
        label="Education OS",
        accent="#4338ca",
        accent_soft="rgba(67, 56, 202, 0.1)",
        hero_tone="module-grid",
        eyebrow_motif="grid",
        card_variant="module",
        os_matrix=_OS_RUN,
        viz_engine="education-os-modules",
    ),
    "platform-integrations": _p(
        "platform-integrations",
        label="Integrations",
        accent="#0ea5e9",
        accent_soft="rgba(14, 165, 233, 0.12)",
        hero_tone="connector",
        eyebrow_motif="webhook",
        card_variant="code",
        viz_engine="integration-hub",
    ),
    "platform-runtime": _p(
        "platform-runtime",
        label="Runtime",
        accent="#64748b",
        accent_soft="rgba(100, 116, 139, 0.12)",
        hero_tone="config",
        eyebrow_motif="cascade",
        card_variant="module",
        os_matrix=_OS_RUN,
        viz_engine="config-cascade",
    ),
}

# View-layer map: user-facing route keys → personality id (Django, not Next.js page.tsx)
_VIEW_LAYER_SLUG_MAP: dict[str, str] = {
    "home": "home",
    "platform": "platform-hub",
    "platform-hub": "platform-hub",
    "about": "about",
    "company": "company",
    "careers": "careers",
    "brand-assets": "brand-assets",
    "app-marketplace": "platform-marketplace",
    "hardware-store": "hardware-store",
    "developer-apis": "developers",
    "developers": "developers",
    "solutions": "solutions-hub",
    "solutions-higher-ed": "solutions-higher-ed",
    "solutions-k12-districts": "solutions-k12-districts",
    "portal-login": "portal-login",
    "request-demo": "demo",
    "demo": "demo",
    "book-demo": "demo",
    "pricing-matrix": "pricing",
    "pricing": "pricing",
    "implementation-timelines": "implementation-timelines",
    "find-campus-portal": "find-campus",
    "find-campus": "find-campus",
    "teacher-workspace": "platform-teacher-portal",
    "training-academies": "training-academies",
    "teacher-communities": "teacher-communities",
    "lesson-planning-templates": "lesson-planning",
    "lesson-planning": "lesson-planning",
    "parent-access-guide": "platform-parent-portal",
    "student-portal-overview": "platform-student-portal",
    "system-status": "system-status",
    "infrastructure-map": "infrastructure-map",
    "trust-security-center": "trust",
    "trust-center": "trust",
    "trust": "trust",
    "security-matrix": "security-matrix",
    "support-knowledge-base": "resources-help-center",
    "resources-help-center": "resources-help-center",
    "procurement-docs": "procurement-docs",
    "legal-compliance-ferpa": "legal-ferpa",
    "legal-compliance-coppa": "legal-coppa",
    "legal-compliance-gdpr": "legal-gdpr",
    "legal-compliance-wcag": "legal-wcag",
    "legal-compliance-terms": "legal-terms",
    "legal-compliance-cookie-policy": "legal-cookie",
    "ferpa": "legal-ferpa",
    "coppa": "legal-coppa",
    "gdpr": "legal-gdpr",
    "wcag": "legal-wcag",
    "terms": "legal-terms",
    "cookie-policy": "legal-cookie",
    "academics": "lane-academics",
    "finance": "lane-finance",
    "admissions": "lane-admissions",
    "why-switch": "migrate",
    "why": "migrate",
    "migrate": "migrate",
    "compare": "compare",
    "resources": "resources",
    "contact": "contact",
    "uptime": "system-status",
    "security": "security-matrix",
    "compliance": "trust",
    "security-compliance": "trust",
}

_SLUG_TO_PERSONALITY: dict[str, str] = dict(_VIEW_LAYER_SLUG_MAP)

# Public export for validation tests (view-layer spec keys)
VIEW_LAYER_SLUGS: tuple[str, ...] = tuple(_VIEW_LAYER_SLUG_MAP.keys())


def all_marketing_personality_ids() -> list[str]:
    """Every registered personality id (for distinction tests)."""
    ids: set[str] = set(_PERSONALITIES) | set(_PLATFORM_PERSONALITIES)
    return sorted(ids)


def personality_accent_signature(personality: MarketingPersonality) -> str:
    """Unique token for distinction checks: accent + viz_engine."""
    return f"{personality['accent']}|{personality['viz_engine']}"


def resolve_marketing_personality(slug: str | None) -> MarketingPersonality:
    """Map a marketing page slug (or short lane slug) to a personality record."""
    raw = (slug or "home").strip().lower()
    if raw in _PERSONALITIES:
        return _PERSONALITIES[raw]
    if raw in _PLATFORM_PERSONALITIES:
        return _PLATFORM_PERSONALITIES[raw]
    if raw.startswith("solutions-"):
        mapped = _SLUG_TO_PERSONALITY.get(raw)
        if mapped and mapped in _PERSONALITIES:
            return _PERSONALITIES[mapped]
        return _PERSONALITIES["solutions-persona"]
    pid = _SLUG_TO_PERSONALITY.get(raw)
    if pid and pid in _PERSONALITIES:
        return _PERSONALITIES[pid]
    if pid and pid in _PLATFORM_PERSONALITIES:
        return _PLATFORM_PERSONALITIES[pid]
    if raw.startswith("platform-"):
        return _p(
            raw,
            label=raw.replace("platform-", "").replace("-", " ").title(),
            accent="#38bdf8",
            accent_soft="rgba(56, 189, 248, 0.1)",
            hero_tone="module-grid",
            eyebrow_motif="grid",
            card_variant="module",
            os_matrix=_OS_RUN,
            viz_engine=f"platform-{raw.split('-', 1)[-1]}",
        )
    if raw.startswith("legal-"):
        return _PERSONALITIES.get(raw, _PERSONALITIES["legal-terms"])
    return _PERSONALITIES["platform-hub"]


def marketing_personality_context(slug: str | None) -> dict[str, Any]:
    """Template context keys for personality wiring + seeded viz payload."""
    from apps.schools.marketing_personality_seeds import seed_for_personality

    personality = resolve_marketing_personality(slug)
    seed = seed_for_personality(personality["id"])
    return {
        "marketing_personality": personality,
        "marketing_personality_id": personality["id"],
        "marketing_personality_os": personality["os_matrix"],
        "marketing_personality_accent_ink": personality["accent_ink"],
        "marketing_viz_engine": personality["viz_engine"],
        "marketing_personality_seed": seed,
        "marketing_personality_seed_json": seed.get("json", "{}"),
    }
