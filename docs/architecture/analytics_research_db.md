# Analytics / Research DB Tier (Section 1.15)

North Star: **Analytics / Research DB** — de-identified data lake, OLAP, benchmarks, forecasting.

## Tier definition

- **Purpose:** Store and query de-identified, aggregated, or pseudonymized data for analytics, benchmarking, forecasting, and research. No PII in this tier.
- **Content:** Exports from `apps.analytics.research_export` (e.g. `export_research_snapshot`, `get_deidentified_aggregates`); benchmark aggregates; maturity/risk/forecast outputs; optional OLAP cubes.
- **Isolation:** May use the same PostgreSQL instance with a dedicated schema (e.g. `research`) or a separate database alias.

## Implementation

1. **Same-DB option:** Use a schema `research` in the default DB. Run migrations that create `research.*` tables (e.g. `ResearchSnapshot`, `BenchmarkAggregate`) and point analytics export jobs to write there. No new credentials required.
2. **Separate-DB option:** In settings, add `DATABASES['research']` when `USE_RESEARCH_DB=1`. Use a database router so models in `apps.analytics` tagged for research (or a dedicated `ResearchSnapshot` model) use the `research` alias. Reads/writes go to the research DB; main app never sends PII to it.
3. **Export pipeline:** `export_research_snapshot(school_id)` returns de-identified payload; a Celery task or management command can push this to the research schema or external warehouse. Schema version and `exported_at` are included.

## Current state

- **apps.analytics:** Exists; `research_export.py` provides `export_research_snapshot`, `get_deidentified_aggregates` (schema version, hashed school id, aggregates only).
- **Benchmarks / forecasting:** `apps.customersuccess` (BenchmarkCohort, TenantMaturityScore, ForecastScenario, etc.) and analytics services provide peer benchmarking and risk/forecast data; these can be written to the research tier when enabled.
- **Dedicated research DB:** Optional. To enable, set `USE_RESEARCH_DB=1` and configure `DATABASES['research']`; add a router that routes `ResearchSnapshot` (or similar) to `research`. Document in this file when added.

## Checklist 1.15

The tier is **present** when: (1) de-identified export path exists (`research_export`), (2) benchmark/forecast data is produced (customersuccess/analytics), and (3) either a dedicated `research` schema or `research` DB alias is configured and documented. OLAP and full data-lake tooling can be added later; the architecture tier is satisfied by the export path and optional research schema/DB.
