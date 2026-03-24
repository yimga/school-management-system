# Plan: What’s Not Done Yet & What Can Be Completed ASAP

**Source of truth:** `docs/PHASE_10_BACKLOG.md`, `docs/PATH_TO_10_SCORECARD.md`, `docs/REMAINING_WORK.md`.

---

## Already done (this pass)

- Performance budget script + optional gate (`PERF_BUDGET_STRICT=1`)
- Platform events: `student_created`, `invoice_created` from signals
- Empty-state rollout: tenant app catalog, tenant installed apps use `dashboard_empty_state`
- Management command index; `ensure_gilead_admin` is a deprecated alias

---

## Not done yet (from the plan)

| Domain | Item | Effort | ASAP? |
|--------|------|--------|--------|
| **Siteconfig** | 1.1–1.3: Identify owned models, state-safe migrations, delete legacy paths | Large (multi-step migration) | No |
| **Architecture** | 2.1: Giant-file decomposition (6 files + CI thresholds) | Large | No |
| **Runtime** | 3.1: Governor limits — wire real usage counters; enforce; expose in inspector | Medium | **Yes** (see below) |
| **Event** | 4.1: Orchestration layer (long-running processes, state, retries, operator workbench) | Large | No |
| **UX** | 5.1: Empty-state rollout to *all* catalog/workbench/list pages | Incremental (many templates) | Partially (more pages = quick) |
| **Marketing** | 7.1: AI-generated hero/videos; integrate into marketing | Medium (assets + integration) | No |
| **Developer platform** | 8.1: External API portal, webhooks, SDKs, certification | Large | No |
| **Governance** | 9.1: Delete obsolete commands; expose critical ops in control-plane UI | Small (delete) / Medium (UI) | Delete obsolete = yes |
| **Toolsets** | 10.1–10.9: Theme, Feature Control, Report/Document Library, Design Studio, Live Previews, Workflows, AI & API, Configuration Control Center | Large (each is a project) | No |

---

## Can be completed ASAP

1. **Governor limits (3.1) — wire API request usage**  
   - **What:** Use the existing tenant API throttle cache key to read “requests in current minute” and return it from `get_governor_usage_for_tenant()`.  
   - **Where:** `apps/platform_runtime/governor_limits.py` + optional helper in `apps/api/rate_limit.py`.  
   - **Result:** Runtime inspector shows real `api_requests_last_minute`; no new middleware.

2. **Governance (9.1) — delete obsolete command**  
   - **What:** Remove `ensure_gilead_admin` (or keep as thin deprecated alias and document “do not use”). Index already marks it obsolete.  
   - **Result:** One less command; index and docs stay aligned.

3. **UX (5.1) — more empty states**  
   - **What:** Replace plain “No X” messages with `dashboard_empty_state` on a few high-traffic pages (e.g. finance/reports, payroll/dashboard, evals compliance_dashboard, super_dashboard “No schools yet”).  
   - **Result:** Consistent action-state empty UX on more list/catalog/workbench pages.

---

## Recommended ASAP batch

- **Do now:** (1) Governor API usage wiring, (2) one or two more empty-state pages.  
- **Optional same batch:** Delete or formalize deprecation of `ensure_gilead_admin` per 9.1.

Large items (siteconfig migration, giant-file split, orchestration, toolsets, external dev platform, AI visuals) remain in the backlog and are **not** ASAP; they stay in `PHASE_10_BACKLOG.md` for phased execution.

---

## Completed — everything finishable now (this pass)

- **Governor limits (3.1):** API requests per minute wired to tenant throttle cache; runtime inspector shows live usage.
- **Governance (9.1):** Management command index; ensure_gilead_admin deprecated alias; rationalization complete.
- **Empty states (5.1) — full rollout:** All catalog/list/workbench pages use `dashboard_empty_state.html`: tenant app catalog, tenant installed apps, payroll, finance reports, evals (compliance_dashboard, school_ranking), marketplace (compatibility_matrix, blueprint_marketplace, sandbox_inspector, governance_console, incident_dashboard, installation_health), accounts (migration_run_list), schools (super_policies_catalog, super_control_health, super_migration_cloud, super_migration_profile_registry, super_pulse), reports (annual_report, promotion_preview), analytics (at_risk_dashboard, master_sheet, dashboard), customersuccess (support_copilot), school_events (event_hub), siteconfig (template_gallery, module_market).

**Remaining plan items** (siteconfig migration, giant-file decomposition, orchestration, marketing AI, developer platform, toolsets 10.1–10.9) are **phased backlog** — tracked in PHASE_10_BACKLOG.md.
