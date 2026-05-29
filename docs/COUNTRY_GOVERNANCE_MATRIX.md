# Country Governance Matrix — Continental Index

Machine-readable truth: `docs/generated/country_governance_matrix.json` (249 ISO 3166-1 alpha-2 codes). Per-country shards: `docs/generated/country_governance_matrix/{iso}.json`.

**Status (batch 1562):** **249/249 verified** via `scripts/enrich_country_governance_matrix.py --continent all --write`. Locale + governance fields synced from seed packs, continent defaults, and Africa-specific overrides.

## Wave progress

| Wave | Continent / scope | Target count | Verified |
|------|-------------------|-------------:|---------:|
| W0 | Skeleton bootstrap | 249 | 249 |
| W-Africa | Africa | ~58 | 59 |
| W-Asia | Asia | ~51 | 51 |
| W-Europe | Europe | ~51 | 51 |
| W-Americas | Americas | ~56 | 56 |
| W-Oceania | Oceania + Pacific | ~26 | 26 |
| W-Territories | Dependent territories (T3) | remainder | remainder |

Regenerate: `python scripts/enrich_country_governance_matrix.py --continent all --write`

## Enrichment pipeline

1. `sync_languages_for_row` — `_seed_country_languages.py` + geonamescache fallback
2. `sync_terminology_for_row` — `COUNTRY_LOCALIZATION` + per-language education overlays
3. `sync_formats_for_row` — `country_formats_service.py`
4. Africa overrides — `scripts/lib/global_governance_africa_overrides.py`
5. Continent defaults — `scripts/lib/global_governance_continent_defaults.py`

## Research tiers

| Tier | Meaning |
|------|---------|
| T1 | Deep anchor markets — hand-researched |
| T2 | Structured sovereign states — template + mandatory overrides |
| T3 | Territories / deps — explicit `territory: true` |

## Exit gates

**Phase 0D:** `verify_country_governance_matrix.py --require-verified` + `verify_country_dissection_ledger.py --require-verified`

**Phase 3+:** Deepen MC profiles, subdivisions, runtime wiring per completion register.

**Phase 5 closure (batch 1565):** Program complete — register **41/41 DONE**. Ongoing drift: `python scripts/verify_country_governance_matrix.py --drift-check --write`

## Competitor benchmark appendix (Phase 5)

Regional incumbent comparison — matrix `competitor_edge` field aligns to this table. Re-benchmark quarterly when country packs change.

| Region | Incumbent pain | RunMyCampus defensible edge | Must close to win |
|--------|----------------|----------------------------|-------------------|
| North America | PowerSchool / Infinite Campus fragmentation | Unified schema + single copilot | Org/district overlay + LEA employer (Phase 4 shipped) |
| UK / Europe | iSAMS / Classter rigidity | Abstract calendars + local packs | MAT central product — Group Console + MAT hub (Phase 4A) |
| Africa | Western billing blindspot + connectivity | Offline-first PWA + mobile-money scaffolds | Live M-Pesa/MoMo webhooks (external PSP); WASSCE depth in matrix |
| LATAM | Inflation + voucher workflows | Multi-currency tenants + tax engine | Boleto/OXXO print + fee repricing (partial) |
| MENA | RTL cosmetic-only dashboards | Arabic locale + `rmc_text_direction` | Bi-directional mixed-script report blocks |
| Faith networks | FACTS diocese consolidation story | `FAITH_BASED` sector + tenant isolation | Diocese org + consolidated rollup (Phase 4C) |

**Verifier:** `verify_country_governance_matrix.py --drift-check` on every PR touching `docs/generated/country_governance_matrix*` or seed packs.
