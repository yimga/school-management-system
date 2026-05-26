# Concierge Migration — Specialist Guide

**Wave M · v3.95.0 · 2026-05-26**

White-glove migration from the legacy SIS is the single biggest barrier to switching identified in the 2026 competitive audit. Every percentage point of switching friction removed is a percentage point of TAM unlocked.

This module is the **per-source-system adapter registry** — what each migration costs, what it covers, what the risk profile is.

## Seeded sources (7)

| Source | Vendor | Segments | Transport | Concierge days | Risk |
|---|---|---|---|---|---|
| `powerschool-sis` | PowerSchool | NA-K12, AU-K12, LATAM-Premium | csv, api, jdbc | 21 | medium |
| `sims-capita-ess` | ESS | UK-K12, UK-MAT, IE-K12 | csv, xml_export, jdbc | 18 | medium |
| `arbor-mis` | Arbor / Permira | UK-K12, UK-MAT | csv, api | 14 | low |
| `bromcom-mis` | Bromcom | UK-K12, UK-MAT | csv, api | 14 | low |
| `managebac-faria` | Faria | IB-Global, International-Premium | csv, api | 12 | low |
| `skyward-sis` | Skyward | NA-K12 | csv, jdbc | 21 | **high** (read-only — write paths counsel-pending) |
| `generic-csv` | Custom | SMB, Emerging-Markets | csv | 5 | low (self-serve via Setup Studio) |

## Capability matrix

Each source declares its supported capabilities from this set:

`students` · `guardians` · `staff` · `classes` · `attendance` · `grades` · `fees_ledger` · `documents` · `report_cards` · `timetable` · `historical_5y` · `incremental_sync`

Only **arbor-mis** currently supports `incremental_sync` — useful for staged cutovers where the source stays live during validation.

## Registry API

```python
from apps.migration_cloud.source_adapters import (
    list_sources, get_source, sources_for_segment, sources_with_capability,
    total_concierge_days_for_sources, summary,
)

# Find UK options
uk_sources = sources_for_segment("UK-K12")  # arbor, sims, bromcom

# Capability filter
incremental = sources_with_capability("incremental_sync")  # only arbor

# Cost estimate for a customer
days = total_concierge_days_for_sources(["powerschool-sis", "managebac-faria"])  # 33

# Aggregate stats
s = summary()
# → {"source_count": 7, "by_risk": {"low": 4, "medium": 2, "high": 1}, ...}
```

## Special handling notes

### PowerSchool (medium risk)
API key gated through PowerSchool plugin marketplace. Some tenants prefer JDBC. **Trauma-aware comms required** after the Dec 2024 breach (62.4M records exposed) — incoming customers will want extra reassurance on data handling.

### SIMS (medium risk)
Long-tail of bespoke schemas — every tenant's SIMS deployment diverges. **Pre-migration audit step is mandatory.**

### Skyward (high risk)
Write paths remain literal `// honest-stub:` markers — counsel-pending for write certification. **Read-only migration only** until legal signoff.

### ManageBac (low risk)
IB-specific. Curriculum metadata (DP/MYP/PYP) must round-trip; rubric mappings need IB-coordinator review.

## Companion sibling integration

The Concierge Migration registry pairs with the Companion Cloud uploads system in [apps/migration_cloud/companion_receiver.py](beta/school-management-system/apps/migration_cloud/companion_receiver.py). A specialist's typical flow:

1. **Pre-migration audit** (90 min) — run [scripts/run_premigration_audit.py](beta/school-management-system/scripts/) (Wave M+1 — script TBD).
2. **Companion upload** of source export — registers via `companion_receiver.register_upload`.
3. **Adapter dispatch** — match source_id to a per-source ETL pipeline.
4. **Cutover** — rehearsed + rollback-ready.
5. **Post-migration validation** — integrity scan across all migrated entities.

## Tests

[apps/migration_cloud/tests/test_source_adapters.py](beta/school-management-system/apps/migration_cloud/tests/test_source_adapters.py) — 18 unit tests covering registry shape, segment filters, capability lookups, concierge-days math.
