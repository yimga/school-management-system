"""Wave M (v3.95.0 — 2026-05-26) — Concierge Migration source adapter registry.

The competitive move: **white-glove migration** from the legacy SIS — the
single biggest barrier to switching identified in the audit
(PowerSchool 23% NA share, SIMS 60%+ UK historical, Arbor 44% English post-
Permira, ManageBac 2000+ IB schools). Every percentage point of switching
friction we remove is a percentage point of TAM unlocked.

This module declares the per-source-system **migration adapter contract**
plus seeded specs for the top 6 sources. The adapters themselves are full
implementations in Wave M+ (one per quarter); this registry is the
scheduling + scope contract that the concierge team works against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Capability flags
# ---------------------------------------------------------------------------

_CAP_STUDENTS = "students"
_CAP_GUARDIANS = "guardians"
_CAP_STAFF = "staff"
_CAP_CLASSES = "classes"
_CAP_ATTENDANCE = "attendance"
_CAP_GRADES = "grades"
_CAP_FEES_LEDGER = "fees_ledger"
_CAP_DOCUMENTS = "documents"
_CAP_REPORT_CARDS = "report_cards"
_CAP_TIMETABLE = "timetable"
_CAP_HISTORICAL_5Y = "historical_5y"
_CAP_INCREMENTAL = "incremental_sync"

_ALL_CAPS: tuple[str, ...] = (
    _CAP_STUDENTS, _CAP_GUARDIANS, _CAP_STAFF, _CAP_CLASSES,
    _CAP_ATTENDANCE, _CAP_GRADES, _CAP_FEES_LEDGER, _CAP_DOCUMENTS,
    _CAP_REPORT_CARDS, _CAP_TIMETABLE, _CAP_HISTORICAL_5Y, _CAP_INCREMENTAL,
)


@dataclass(frozen=True)
class MigrationSourceAdapterSpec:
    """A migration source contract."""

    source_id: str
    display_name: str
    vendor: str
    market_segments: tuple[str, ...]  # e.g. "NA-K12", "UK-MAT", "IB-Global"
    transport: tuple[str, ...]  # "csv" / "api" / "jdbc" / "xml_export"
    capabilities: tuple[str, ...]
    estimated_concierge_days: int
    average_data_volume: str  # "small / medium / large / enterprise"
    risk_level: str  # "low / medium / high"
    notes: str = ""
    docs_url: str = ""


_REGISTRY: dict[str, MigrationSourceAdapterSpec] = {}


def register_source(spec: MigrationSourceAdapterSpec) -> None:
    _REGISTRY[spec.source_id] = spec


def get_source(source_id: str) -> MigrationSourceAdapterSpec | None:
    return _REGISTRY.get(source_id)


def list_sources() -> tuple[MigrationSourceAdapterSpec, ...]:
    return tuple(_REGISTRY.values())


def sources_for_segment(segment: str) -> tuple[MigrationSourceAdapterSpec, ...]:
    s = (segment or "").strip()
    return tuple(adp for adp in _REGISTRY.values() if s in adp.market_segments)


def sources_with_capability(cap: str) -> tuple[MigrationSourceAdapterSpec, ...]:
    return tuple(adp for adp in _REGISTRY.values() if cap in adp.capabilities)


def all_capabilities() -> tuple[str, ...]:
    return _ALL_CAPS


def clear_registry_for_tests() -> None:
    _REGISTRY.clear()


# ---------------------------------------------------------------------------
# Seeded sources — top 6 competitor SIS platforms
# ---------------------------------------------------------------------------

def _seed_sources() -> None:
    register_source(MigrationSourceAdapterSpec(
        source_id="powerschool-sis",
        display_name="PowerSchool SIS",
        vendor="PowerSchool",
        market_segments=("NA-K12", "AU-K12", "LATAM-Premium"),
        transport=("csv", "api", "jdbc"),
        capabilities=(
            _CAP_STUDENTS, _CAP_GUARDIANS, _CAP_STAFF, _CAP_CLASSES,
            _CAP_ATTENDANCE, _CAP_GRADES, _CAP_FEES_LEDGER, _CAP_DOCUMENTS,
            _CAP_HISTORICAL_5Y,
        ),
        estimated_concierge_days=21,
        average_data_volume="large",
        risk_level="medium",
        notes=(
            "API key gated through PowerSchool plugin marketplace; some "
            "tenants prefer JDBC. Trauma-aware comms required after the "
            "Dec 2024 breach (62.4M records)."
        ),
    ))

    register_source(MigrationSourceAdapterSpec(
        source_id="sims-capita-ess",
        display_name="SIMS (Capita / ESS)",
        vendor="ESS / Education Software Solutions",
        market_segments=("UK-K12", "UK-MAT", "IE-K12"),
        transport=("csv", "xml_export", "jdbc"),
        capabilities=(
            _CAP_STUDENTS, _CAP_GUARDIANS, _CAP_STAFF, _CAP_CLASSES,
            _CAP_ATTENDANCE, _CAP_GRADES, _CAP_DOCUMENTS, _CAP_HISTORICAL_5Y,
            _CAP_TIMETABLE,
        ),
        estimated_concierge_days=18,
        average_data_volume="large",
        risk_level="medium",
        notes=(
            "Long-tail of bespoke schemas — every tenant's SIMS deployment "
            "diverges. Pre-migration audit step is mandatory."
        ),
    ))

    register_source(MigrationSourceAdapterSpec(
        source_id="arbor-mis",
        display_name="Arbor MIS",
        vendor="Arbor / Permira",
        market_segments=("UK-K12", "UK-MAT"),
        transport=("csv", "api"),
        capabilities=(
            _CAP_STUDENTS, _CAP_GUARDIANS, _CAP_STAFF, _CAP_CLASSES,
            _CAP_ATTENDANCE, _CAP_GRADES, _CAP_DOCUMENTS, _CAP_TIMETABLE,
            _CAP_INCREMENTAL,
        ),
        estimated_concierge_days=14,
        average_data_volume="medium",
        risk_level="low",
        notes=(
            "Cleaner API + better-normalized schema than SIMS. Incremental "
            "sync supported — useful for staged cutovers."
        ),
    ))

    register_source(MigrationSourceAdapterSpec(
        source_id="bromcom-mis",
        display_name="Bromcom MIS",
        vendor="Bromcom",
        market_segments=("UK-K12", "UK-MAT"),
        transport=("csv", "api"),
        capabilities=(
            _CAP_STUDENTS, _CAP_GUARDIANS, _CAP_STAFF, _CAP_CLASSES,
            _CAP_ATTENDANCE, _CAP_GRADES, _CAP_TIMETABLE,
        ),
        estimated_concierge_days=14,
        average_data_volume="medium",
        risk_level="low",
        notes=(
            "Growing UK alternative — well-documented export tooling. AI "
            "feature parity (switchable LLM) means migrators should "
            "preserve AI policy continuity."
        ),
    ))

    register_source(MigrationSourceAdapterSpec(
        source_id="managebac-faria",
        display_name="ManageBac (Faria)",
        vendor="Faria Education Group",
        market_segments=("IB-Global", "International-Premium"),
        transport=("csv", "api"),
        capabilities=(
            _CAP_STUDENTS, _CAP_GUARDIANS, _CAP_STAFF, _CAP_CLASSES,
            _CAP_GRADES, _CAP_REPORT_CARDS, _CAP_DOCUMENTS,
        ),
        estimated_concierge_days=12,
        average_data_volume="medium",
        risk_level="low",
        notes=(
            "IB-specific. Curriculum metadata (DP/MYP/PYP) must round-trip; "
            "rubric mappings need IB-coordinator review."
        ),
    ))

    register_source(MigrationSourceAdapterSpec(
        source_id="skyward-sis",
        display_name="Skyward SIS",
        vendor="Skyward",
        market_segments=("NA-K12",),
        transport=("csv", "jdbc"),
        capabilities=(
            _CAP_STUDENTS, _CAP_GUARDIANS, _CAP_STAFF, _CAP_CLASSES,
            _CAP_ATTENDANCE, _CAP_GRADES, _CAP_FEES_LEDGER, _CAP_HISTORICAL_5Y,
        ),
        estimated_concierge_days=21,
        average_data_volume="enterprise",
        risk_level="high",
        notes=(
            "Write-paths remain `// honest-stub:` markers — counsel-pending "
            "for write certification. Read-only migration only."
        ),
    ))

    register_source(MigrationSourceAdapterSpec(
        source_id="generic-csv",
        display_name="Generic CSV Bundle",
        vendor="Custom / Spreadsheet",
        market_segments=("SMB", "Emerging-Markets"),
        transport=("csv",),
        capabilities=(
            _CAP_STUDENTS, _CAP_GUARDIANS, _CAP_STAFF, _CAP_CLASSES,
        ),
        estimated_concierge_days=5,
        average_data_volume="small",
        risk_level="low",
        notes=(
            "Fallback adapter — every other source can degrade to this "
            "via CSV exports. Doesn't require concierge engagement; "
            "tenant-admin self-serve via Setup Studio."
        ),
    ))


_seed_sources()


# ---------------------------------------------------------------------------
# Concierge engagement summary
# ---------------------------------------------------------------------------

def total_concierge_days_for_sources(source_ids: list[str]) -> int:
    """Sum of estimated concierge days for a customer's source list."""
    total = 0
    for sid in source_ids:
        spec = _REGISTRY.get(sid)
        if spec:
            total += spec.estimated_concierge_days
    return total


def summary() -> dict[str, Any]:
    sources = list_sources()
    return {
        "source_count": len(sources),
        "all_capabilities": list(_ALL_CAPS),
        "by_risk": {
            risk: sum(1 for s in sources if s.risk_level == risk)
            for risk in ("low", "medium", "high")
        },
        "by_segment": _segment_counts(sources),
        "total_capability_coverage": sum(len(s.capabilities) for s in sources),
    }


def _segment_counts(sources: tuple[MigrationSourceAdapterSpec, ...]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in sources:
        for seg in s.market_segments:
            out[seg] = out.get(seg, 0) + 1
    return out
