"""
Deterministic marketing viz seed data — one unique dataset per personality id.

Public pages consume these via ``data-mkt-personality-seed`` (JSON) and
``mkt-personality-viz.js``. No authenticated API required.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


def _series(labels: list[str], values: list[float]) -> list[dict[str, Any]]:
    return [{"label": a, "value": b} for a, b in zip(labels, values, strict=True)]


def _money(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"


def _seed(
    *,
    personality_id: str,
    viz_engine: str,
    metrics: list[dict[str, Any]],
    series: list[dict[str, Any]] | None = None,
    timeline: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "personality_id": personality_id,
        "viz_engine": viz_engine,
        "metrics": metrics,
        "series": series or [],
        "timeline": timeline or [],
    }
    if extra:
        payload.update(extra)
    payload["json"] = json.dumps(
        {k: v for k, v in payload.items() if k != "json"},
        separators=(",", ":"),
    )
    return payload


# ── RUN platform seeds ──
_RUN_GAUGE = _seed(
    personality_id="platform-hub",
    viz_engine="run-gauge",
    metrics=[
        {"label": "Active tenants", "value": "1,284", "delta": "+3.2%"},
        {"label": "p95 API latency", "value": "142ms", "delta": "-8ms"},
        {"label": "Jobs queued", "value": "38", "delta": "stable"},
    ],
    series=_series(
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        [92, 94, 91, 96, 97, 95, 98],
    ),
)

_CONTROL_PLANE = _seed(
    personality_id="platform-control-plane",
    viz_engine="run-gauge",
    metrics=[
        {"label": "Campuses governed", "value": "412", "delta": "+12"},
        {"label": "Policy bundles", "value": "89", "delta": "+2"},
        {"label": "Health score avg", "value": "94.1", "delta": "+0.4"},
    ],
    series=_series(["NA", "EU", "AF", "APAC"], [88, 91, 86, 93]),
)

# ── TEACH platform seeds ──
_TEACH_ENGAGEMENT = _seed(
    personality_id="lane-academics",
    viz_engine="teach-engagement",
    metrics=[
        {"label": "Classes live", "value": "186", "delta": "now"},
        {"label": "Engagement index", "value": "78%", "delta": "+4%"},
        {"label": "Interventions due", "value": "14", "delta": "today"},
    ],
    series=_series(["Period 1", "P2", "P3", "P4", "P5"], [72, 81, 79, 85, 88]),
    extra={"dependency_nodes": 24, "dependency_edges": 41},
)

_CLASSROOM_ROSTER = _seed(
    personality_id="platform-teacher-portal",
    viz_engine="classroom-roster",
    metrics=[
        {"label": "Roster size", "value": "32", "delta": "3A"},
        {"label": "Attendance today", "value": "97%", "delta": "+1"},
        {"label": "Grades pending", "value": "5", "delta": "due Fri"},
    ],
    series=_series(["Mon", "Tue", "Wed", "Thu", "Fri"], [96, 94, 97, 98, 97]),
)

# ── PAY platform seeds ──
_PAY_LEDGER = _seed(
    personality_id="lane-finance",
    viz_engine="pay-ledger",
    metrics=[
        {"label": "Collected (MTD)", "value": _money(28473950), "delta": "+6.1%"},
        {"label": "Outstanding", "value": _money(1203400), "delta": "-2.3%"},
        {"label": "Audit entries", "value": "12,804", "delta": "balanced"},
    ],
    series=_series(["W1", "W2", "W3", "W4"], [210000, 245000, 198000, 267000]),
    extra={"double_entry": True, "currency": "USD"},
)

_PRICING_MATRIX = _seed(
    personality_id="pricing",
    viz_engine="pricing-matrix",
    metrics=[
        {"label": "Starter", "value": "$299", "delta": "/mo"},
        {"label": "Growth", "value": "$799", "delta": "popular"},
        {"label": "Enterprise", "value": "Custom", "delta": "SLA"},
    ],
    series=_series(["USD", "EUR", "GBP", "XAF"], [299, 279, 249, 185000]),
    extra={"localized": True},
)

# ── COMMUNICATE platform seeds ──
_COMM_FEED = _seed(
    personality_id="platform-communications",
    viz_engine="communicate-feed",
    metrics=[
        {"label": "Messages queued", "value": "1,204", "delta": "live"},
        {"label": "Delivery rate", "value": "99.2%", "delta": "+0.1%"},
        {"label": "Sentiment", "value": "82", "delta": "positive"},
    ],
    series=_series(["SMS", "Email", "Push", "In-app"], [420, 680, 210, 890]),
)

# Per-personality unique seeds (abbreviated keys → full payloads)
_PERSONALITY_SEEDS: dict[str, dict[str, Any]] = {
    "home": _seed(
        personality_id="home",
        viz_engine="campus-pulse",
        metrics=[
            {"label": "Schools live", "value": "1,284", "delta": "+18"},
            {"label": "Students served", "value": "412K", "delta": "+2.1%"},
            {"label": "Messages / day", "value": "2.1M", "delta": "peak"},
        ],
        series=_series(["Admissions", "Academics", "Finance", "Comms"], [88, 92, 85, 94]),
    ),
    "platform-hub": _RUN_GAUGE,
    "platform-control-plane": _CONTROL_PLANE,
    "platform-analytics": _seed(
        personality_id="platform-analytics",
        viz_engine="run-gauge",
        metrics=[
            {"label": "Dashboards", "value": "48", "delta": "live"},
            {"label": "Queries/min", "value": "12.4K", "delta": "+8%"},
            {"label": "Export jobs", "value": "6", "delta": "running"},
        ],
        series=_series(["Mon", "Tue", "Wed", "Thu", "Fri"], [78, 82, 85, 88, 91]),
    ),
    "platform-education-os": _seed(
        personality_id="platform-education-os",
        viz_engine="education-os-modules",
        metrics=[
            {"label": "Modules", "value": "24", "delta": "core"},
            {"label": "Workflows", "value": "156", "delta": "active"},
            {"label": "Uptime", "value": "99.97%", "delta": "30d"},
        ],
        series=_series(["Ops", "SIS", "Finance", "Comms"], [95, 92, 88, 90]),
    ),
    "migrate": _seed(
        personality_id="migrate",
        viz_engine="migration-switch",
        metrics=[
            {"label": "Legacy exports", "value": "4", "delta": "connected"},
            {"label": "Mapped fields", "value": "96%", "delta": "validated"},
            {"label": "Go-live", "value": "Day 90", "delta": "target"},
        ],
        timeline=[
            {"day": 1, "label": "Inventory", "pct": 20},
            {"day": 21, "label": "Dry-run", "pct": 55},
            {"day": 60, "label": "Training", "pct": 80},
            {"day": 90, "label": "Cutover", "pct": 100},
        ],
    ),
    "lane-academics": _TEACH_ENGAGEMENT,
    "platform-student-information-system": _seed(
        personality_id="platform-student-information-system",
        viz_engine="teach-engagement",
        metrics=[
            {"label": "Students", "value": "2,840", "delta": "enrolled"},
            {"label": "Programs", "value": "12", "delta": "active"},
            {"label": "Records sync", "value": "100%", "delta": "SIS"},
        ],
        series=_series(["G6", "G7", "G8", "G9", "G10", "G11", "G12"], [420, 410, 398, 402, 390, 385, 435]),
    ),
    "platform-teacher-portal": _CLASSROOM_ROSTER,
    "platform-attendance": _seed(
        personality_id="platform-attendance",
        viz_engine="attendance-spark",
        metrics=[
            {"label": "Present", "value": "94.2%", "delta": "today"},
            {"label": "Late", "value": "3.1%", "delta": "-0.2%"},
            {"label": "Absent", "value": "2.7%", "delta": "flagged"},
        ],
        series=_series(["G7", "G8", "G9", "G10", "G11", "G12"], [96, 95, 93, 94, 92, 91]),
    ),
    "lane-finance": _PAY_LEDGER,
    "platform-fees-payments": _seed(
        personality_id="platform-fees-payments",
        viz_engine="pay-ledger",
        metrics=[
            {"label": "Invoices (MTD)", "value": "3,204", "delta": "+4%"},
            {"label": "Collected", "value": _money(9845020), "delta": "98.2%"},
            {"label": "Gateways", "value": "6", "delta": "live"},
        ],
        series=_series(["Tuition", "Fees", "Meals", "Transport"], [62, 18, 12, 8]),
        extra={"double_entry": True},
    ),
    "pricing": _PRICING_MATRIX,
    "lane-admissions": _seed(
        personality_id="lane-admissions",
        viz_engine="communicate-feed",
        metrics=[
            {"label": "Enquiries", "value": "284", "delta": "pipeline"},
            {"label": "Conversion", "value": "34%", "delta": "+2%"},
            {"label": "Offers sent", "value": "42", "delta": "week"},
        ],
        series=_series(["Lead", "Apply", "Review", "Offer"], [100, 72, 48, 34]),
    ),
    "platform-admissions": _seed(
        personality_id="platform-admissions",
        viz_engine="communicate-feed",
        metrics=[
            {"label": "Applications", "value": "1,204", "delta": "open"},
            {"label": "Decisions", "value": "86%", "delta": "SLA met"},
            {"label": "Waitlist", "value": "48", "delta": "active"},
        ],
        series=_series(["Inquiry", "Apply", "Interview", "Enroll"], [320, 210, 98, 76]),
    ),
    "platform-communications": _COMM_FEED,
    "platform-parent-portal": _seed(
        personality_id="platform-parent-portal",
        viz_engine="family-guide",
        metrics=[
            {"label": "Unread", "value": "3", "delta": "messages"},
            {"label": "Balance due", "value": _money(12500), "delta": "due 12 Jun"},
            {"label": "Events", "value": "2", "delta": "this week"},
        ],
        series=_series(["Fees", "Reports", "Messages", "Calendar"], [1, 2, 3, 2]),
        extra={"accessibility": "large-type-ready"},
    ),
    "platform-student-portal": _seed(
        personality_id="platform-student-portal",
        viz_engine="gamified-learner",
        metrics=[
            {"label": "XP this week", "value": "420", "delta": "+80"},
            {"label": "Assignments", "value": "4", "delta": "due"},
            {"label": "Streak", "value": "12d", "delta": "🔥"},
        ],
        series=_series(["Math", "Science", "English", "Hist"], [88, 92, 85, 90]),
    ),
    "developers": _seed(
        personality_id="developers",
        viz_engine="api-playground",
        metrics=[
            {"label": "API calls (24h)", "value": "2.4M", "delta": "+12%"},
            {"label": "Error rate", "value": "0.04%", "delta": "-0.01%"},
            {"label": "Webhooks", "value": "18.2K", "delta": "delivered"},
        ],
        series=_series(["GET", "POST", "PATCH", "DELETE"], [62, 28, 8, 2]),
        extra={"sample_endpoint": "/api/v1/students/"},
    ),
    "demo": _seed(
        personality_id="demo",
        viz_engine="wizard-steps",
        metrics=[
            {"label": "Step", "value": "2", "delta": "of 4"},
            {"label": "Campus size", "value": "800–2K", "delta": "students"},
            {"label": "Pain", "value": "Migration", "delta": "selected"},
        ],
        timeline=[
            {"day": 1, "label": "Discovery", "pct": 25},
            {"day": 14, "label": "Sandbox", "pct": 50},
            {"day": 30, "label": "Pilot", "pct": 75},
            {"day": 90, "label": "Go-live", "pct": 100},
        ],
    ),
    "trust": _seed(
        personality_id="trust",
        viz_engine="trust-ledger",
        metrics=[
            {"label": "Controls mapped", "value": "47", "delta": "live"},
            {"label": "Last audit", "value": "14d", "delta": "ago"},
            {"label": "Incidents (90d)", "value": "0", "delta": "P1"},
        ],
        series=_series(["Encrypt", "RBAC", "Audit", "DR"], [100, 98, 96, 94]),
    ),
    "security-matrix": _seed(
        personality_id="security-matrix",
        viz_engine="rbac-matrix",
        metrics=[
            {"label": "Roles", "value": "12", "delta": "defined"},
            {"label": "Permissions", "value": "284", "delta": "mapped"},
            {"label": "Overrides", "value": "3", "delta": "review"},
        ],
        series=_series(["Admin", "Teacher", "Parent", "Student"], [48, 96, 64, 76]),
        extra={"matrix_rows": 12, "matrix_cols": 18},
    ),
    "about": _seed(
        personality_id="about",
        viz_engine="timeline-corporate",
        metrics=[
            {"label": "Founded", "value": "2019", "delta": ""},
            {"label": "Countries", "value": "34", "delta": "+6 YoY"},
            {"label": "Team", "value": "140+", "delta": "remote-first"},
        ],
        timeline=[
            {"year": 2019, "label": "Founded in Yaoundé"},
            {"year": 2021, "label": "Multi-tenant launch"},
            {"year": 2024, "label": "Migration Cloud"},
            {"year": 2026, "label": "Education OS"},
        ],
    ),
    "careers": _seed(
        personality_id="careers",
        viz_engine="stack-selector",
        metrics=[
            {"label": "Open roles", "value": "18", "delta": "hiring"},
            {"label": "Stack", "value": "Django", "delta": "+ React"},
            {"label": "Remote", "value": "100%", "delta": "async"},
        ],
        series=_series(["Eng", "Product", "GTM", "Ops"], [8, 4, 3, 3]),
        extra={"stacks": ["Python", "TypeScript", "Rust", "PostgreSQL"]},
    ),
    "brand-assets": _seed(
        personality_id="brand-assets",
        viz_engine="brand-swatches",
        metrics=[
            {"label": "Primary", "value": "#c2410c", "delta": "copy"},
            {"label": "Ink", "value": "#1c1917", "delta": "copy"},
            {"label": "Canvas", "value": "#faf7f2", "delta": "copy"},
        ],
        series=_series(["Primary", "Indigo", "Emerald", "Gold"], [40, 28, 22, 18]),
        extra={"swatches": ["#c2410c", "#4f46e5", "#059669", "#d97706"]},
    ),
    "platform-marketplace": _seed(
        personality_id="platform-marketplace",
        viz_engine="app-catalog",
        metrics=[
            {"label": "Apps", "value": "124", "delta": "listed"},
            {"label": "Installs", "value": "8.2K", "delta": "MTD"},
            {"label": "Avg rating", "value": "4.7", "delta": "★"},
        ],
        series=_series(["Admissions", "Finance", "LMS", "Ops"], [32, 28, 24, 40]),
    ),
    "solutions-higher-ed": _seed(
        personality_id="solutions-higher-ed",
        viz_engine="provost-research",
        metrics=[
            {"label": "Programs", "value": "48", "delta": "tracked"},
            {"label": "Research grants", "value": "$2.1M", "delta": "FY26"},
            {"label": "Retention", "value": "91%", "delta": "+2%"},
        ],
        series=_series(["UG", "Grad", "Online", "Cont Ed"], [62, 18, 14, 6]),
    ),
    "solutions-k12-districts": _seed(
        personality_id="solutions-k12-districts",
        viz_engine="board-compliance",
        metrics=[
            {"label": "Schools", "value": "67", "delta": "district"},
            {"label": "Board packets", "value": "12", "delta": "ready"},
            {"label": "Compliance", "value": "100%", "delta": "FERPA"},
        ],
        series=_series(["Policy", "Finance", "HR", "Academics"], [24, 18, 12, 46]),
    ),
    "portal-login": _seed(
        personality_id="portal-login",
        viz_engine="secure-gateway",
        metrics=[
            {"label": "MFA ready", "value": "Yes", "delta": "TOTP"},
            {"label": "Session TTL", "value": "8h", "delta": "configurable"},
            {"label": "Failed (24h)", "value": "0.02%", "delta": "low"},
        ],
        series=_series(["Passkey", "TOTP", "SMS", "Email"], [12, 48, 8, 32]),
    ),
    "find-campus": _seed(
        personality_id="find-campus",
        viz_engine="geo-finder",
        metrics=[
            {"label": "Indexed", "value": "1,284", "delta": "campuses"},
            {"label": "Regions", "value": "6", "delta": "continents"},
            {"label": "Match", "value": "<200ms", "delta": "search"},
        ],
        series=_series(["NA", "EU", "AF", "LATAM", "APAC", "ME"], [210, 180, 420, 95, 310, 69]),
    ),
    "implementation-timelines": _seed(
        personality_id="implementation-timelines",
        viz_engine="gantt-rollout",
        metrics=[
            {"label": "Day 1", "value": "Kickoff", "delta": ""},
            {"label": "Day 30", "value": "Pilot", "delta": ""},
            {"label": "Day 90", "value": "Go-live", "delta": ""},
        ],
        timeline=[
            {"day": 1, "label": "Discovery", "pct": 10},
            {"day": 7, "label": "Data map", "pct": 25},
            {"day": 21, "label": "Dry-run", "pct": 55},
            {"day": 45, "label": "Training", "pct": 75},
            {"day": 90, "label": "Production", "pct": 100},
        ],
    ),
    "system-status": _seed(
        personality_id="system-status",
        viz_engine="incident-monitor",
        metrics=[
            {"label": "API", "value": "Operational", "delta": "99.98%"},
            {"label": "Portal", "value": "Operational", "delta": "99.95%"},
            {"label": "Latency p95", "value": "142ms", "delta": "NA"},
        ],
        series=_series(["NA-East", "NA-West", "EU", "AF-South"], [98, 97, 99, 96]),
    ),
    "infrastructure-map": _seed(
        personality_id="infrastructure-map",
        viz_engine="infra-map",
        metrics=[
            {"label": "Regions", "value": "6", "delta": "active"},
            {"label": "Edge nodes", "value": "24", "delta": "CDN"},
            {"label": "Gateways", "value": "12", "delta": "API"},
        ],
        series=_series(["US", "EU", "AF", "APAC"], [8, 6, 5, 5]),
    ),
    "resources-help-center": _seed(
        personality_id="resources-help-center",
        viz_engine="kb-search",
        metrics=[
            {"label": "Articles", "value": "842", "delta": "indexed"},
            {"label": "Avg resolve", "value": "4.2m", "delta": "read"},
            {"label": "AI assist", "value": "On", "delta": "Engine Room"},
        ],
        series=_series(["Setup", "Billing", "SIS", "API"], [210, 180, 240, 120]),
    ),
    "procurement-docs": _seed(
        personality_id="procurement-docs",
        viz_engine="procurement-repo",
        metrics=[
            {"label": "Templates", "value": "24", "delta": "RFP"},
            {"label": "Signed", "value": "18", "delta": "contracts"},
            {"label": "SOC2 pack", "value": "Ready", "delta": "download"},
        ],
        series=_series(["RFP", "MSA", "DPA", "SOC2"], [24, 18, 18, 12]),
    ),
    "legal-ferpa": _seed(
        personality_id="legal-ferpa",
        viz_engine="legal-records",
        metrics=[
            {"label": "Records encrypted", "value": "100%", "delta": "at rest"},
            {"label": "Access logs", "value": "Full", "delta": "audit"},
            {"label": "Disclosures", "value": "Tracked", "delta": "FERPA"},
        ],
        series=_series(["Encrypt", "Access", "Audit", "Export"], [100, 98, 96, 94]),
    ),
    "legal-coppa": _seed(
        personality_id="legal-coppa",
        viz_engine="legal-consent",
        metrics=[
            {"label": "Parent consent", "value": "Required", "delta": "<13"},
            {"label": "Data min", "value": "Strict", "delta": "COPPA"},
            {"label": "Third-party", "value": "Disclosed", "delta": "list"},
        ],
        series=_series(["Consent", "Minimize", "Parent", "Delete"], [100, 95, 98, 92]),
    ),
    "legal-gdpr": _seed(
        personality_id="legal-gdpr",
        viz_engine="privacy-dashboard",
        metrics=[
            {"label": "DSAR SLA", "value": "30d", "delta": "GDPR"},
            {"label": "Erasure", "value": "Supported", "delta": "Art 17"},
            {"label": "DPA", "value": "Available", "delta": "Art 28"},
        ],
        series=_series(["Access", "Rectify", "Erase", "Port"], [88, 82, 90, 86]),
    ),
    "legal-wcag": _seed(
        personality_id="legal-wcag",
        viz_engine="a11y-matrix",
        metrics=[
            {"label": "WCAG target", "value": "2.2 AA", "delta": "roadmap AAA"},
            {"label": "Contrast", "value": "7:1+", "delta": "marketing"},
            {"label": "Keyboard", "value": "Full", "delta": "shells"},
        ],
        series=_series(["Perceivable", "Operable", "Understandable", "Robust"], [94, 96, 92, 95]),
    ),
    "legal-terms": _seed(
        personality_id="legal-terms",
        viz_engine="legal-document",
        metrics=[{"label": "Version", "value": "2026.05", "delta": "effective"}],
        series=_series(["Terms", "Privacy", "DPA", "SLA"], [1, 1, 1, 1]),
    ),
    "legal-cookie": _seed(
        personality_id="legal-cookie",
        viz_engine="cookie-matrix",
        metrics=[
            {"label": "Essential", "value": "12", "delta": "required"},
            {"label": "Analytics", "value": "4", "delta": "opt-in"},
            {"label": "Marketing", "value": "2", "delta": "opt-in"},
        ],
        series=_series(["Essential", "Analytics", "Marketing", "Pref"], [12, 4, 2, 3]),
    ),
    "training-academies": _seed(
        personality_id="training-academies",
        viz_engine="lms-progress",
        metrics=[
            {"label": "Courses", "value": "36", "delta": "live"},
            {"label": "Completion", "value": "68%", "delta": "avg"},
            {"label": "Certs", "value": "1.2K", "delta": "issued"},
        ],
        series=_series(["Module 1", "M2", "M3", "M4"], [100, 82, 64, 48]),
    ),
    "teacher-communities": _seed(
        personality_id="teacher-communities",
        viz_engine="thread-board",
        metrics=[
            {"label": "Threads", "value": "2.4K", "delta": "active"},
            {"label": "Tags", "value": "48", "delta": "topics"},
            {"label": "Replies/day", "value": "186", "delta": "+12%"},
        ],
        series=_series(["Math", "Science", "ELA", "Arts"], [620, 480, 540, 310]),
    ),
    "lesson-planning": _seed(
        personality_id="lesson-planning",
        viz_engine="template-canvas",
        metrics=[
            {"label": "Templates", "value": "124", "delta": "shared"},
            {"label": "Blocks", "value": "8", "delta": "types"},
            {"label": "Exports", "value": "PDF", "delta": "+ DOCX"},
        ],
        series=_series(["Warm-up", "Instruction", "Practice", "Exit"], [8, 24, 16, 8]),
    ),
    "hardware-store": _seed(
        personality_id="hardware-store",
        viz_engine="product-grid",
        metrics=[
            {"label": "SKUs", "value": "24", "delta": "verified"},
            {"label": "Ship", "value": "5–7d", "delta": "regional"},
            {"label": "Warranty", "value": "3yr", "delta": "edu"},
        ],
        series=_series(["Kiosks", "Printers", "Tablets", "AP"], [6, 8, 6, 4]),
    ),
}


def seed_for_personality(personality_id: str) -> dict[str, Any]:
    """Return seeded viz payload; synthesize unique fallback if missing."""
    if personality_id in _PERSONALITY_SEEDS:
        return _PERSONALITY_SEEDS[personality_id]
    # Deterministic fallback from id hash — still unique per slug
    h = sum(ord(c) for c in personality_id) % 97
    return _seed(
        personality_id=personality_id,
        viz_engine=f"spark-{personality_id[:12]}",
        metrics=[
            {"label": "Signal", "value": str(70 + h % 25), "delta": "+1"},
            {"label": "Load", "value": f"{(h % 40) + 60}%", "delta": "live"},
            {"label": "Index", "value": str(h), "delta": "seed"},
        ],
        series=_series(["A", "B", "C", "D"], [(h + i * 7) % 100 for i in range(4)]),
    )
