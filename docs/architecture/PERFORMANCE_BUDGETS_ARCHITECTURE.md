# Performance budgets and cleanup/deletion plan

Page load budgets, runtime compilation budgets, widget/dashboard budgets, reporting/query and search performance, and explicit cleanup/deletion (Execution Master §3.10, §8).

## Performance budgets

- **Page load budgets:** Target first contentful paint and time-to-interactive per page family (e.g. list &lt; 2s, dashboard &lt; 3s on 3G-equivalent). Measure in CI or monitoring; fail deploy or alert when over.
- **Runtime compilation budgets:** `build_tenant_runtime` should complete within a few tens of ms; cache aggressively; no N+1 or heavy queries in resolver steps.
- **Widget/dashboard budgets:** Per-widget data fetch and render time; limit concurrent widgets; lazy-load below fold.
- **Reporting/query performance:** Heavy reports: timeout and row limits; materialize where needed; see REPORTING_BI_ARCHITECTURE.
- **Search performance:** Index size and query latency targets; rate limits; see SEARCH_ARCHITECTURE.

## Cleanup list (what to delete or shrink)

- **Dead templates:** Remove after confirming no references (search codebase and URL confs).
- **Duplicate layout code:** Replace with shared partials (page_families, shell bases).
- **Redundant dashboard JS:** Consolidate to one dashboard runtime/widget system; remove duplicate history.
- **Unused formatting helpers:** Single path for date/currency/number (runtime.locale + formatters).
- **Legacy settings bypasses:** Migrate to request.tenant_runtime and helpers; remove direct SiteSettings.get_solo() in tenant-facing code.
- **Obsolete placeholder TODOs:** Resolve or remove; no "TBD" in production UI (use "—" or N/A).
- **Old admin leftovers:** Remove if superseded by Unfold or custom admin.
- **Duplicated currency/date/number logic:** One formatter layer keyed by runtime.
- **Code paths that bypass runtime:** Reject in review; enforce via check_no_hardcoding and lint_tenant_settings.

## God-app decomposition (siteconfig)

Over time split into: branding, dashboard engine, workflow engine, platform settings, runtime config helpers, pack governance. Do not add new responsibilities to siteconfig; move new work to platform_runtime, policies, or dedicated apps.

## References

- [CLEANUP_AND_DELETION_PLAN.md](CLEANUP_AND_DELETION_PLAN.md)
- [../VISUAL_DEBT_BACKLOG.md](../VISUAL_DEBT_BACKLOG.md)
- scripts/check_no_hardcoding.py, scripts/lint_tenant_settings.py
- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md)
