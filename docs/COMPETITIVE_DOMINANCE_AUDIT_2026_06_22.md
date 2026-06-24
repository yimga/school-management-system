# Competitive Dominance Audit — Operator & Owner Lens (2026-06-22)

> Goal: be the Linux / AWS / Shopify / Salesforce of global school operations —
> one platform, 250+ countries, **local-first** for every tenant, AI solving
> operational friction before the tenant feels it. Rule of the game:
> **simplicity, creativity, logical flow.** This document is the grounded audit
> (not aspiration): every claim below was verified against the live tree, with
> file paths, so the gaps are real and the next moves are executable.

## 0. Verdict (read this first)

We are **architecturally ahead** of the legacy incumbents (PowerSchool, Infinite
Campus, Ellucian) on the things that are hard to retrofit: multi-tenant
isolation, local-first PPP pricing, offline resilience, and vendor-neutral
telemetry **already exist and are tested**. The incumbents' moat is contracts
and inertia, not technology.

Our remaining gaps are **feature-breadth and last-mile integration**, not
foundations. That is the winning position: we extend, they rebuild. This audit
also rejected a "rip-and-replace" blueprint (raw `psycopg2` + `SET LOCAL
app.current_tenant_id` RLS + float money + React/Node) because in our stack it
would be a **regression** — SQL-injectable tenant context, a money-as-float
violation of our zero-tolerance `scan_money_float` gate, and a second data
architecture conflicting with our existing `app.current_school_id` model.

## 1. Where we already win (verified, with receipts)

| Capability | Incumbents (PowerSchool / Infinite Campus / Ellucian) | RunMyCampus today | Evidence |
|---|---|---|---|
| **Tenant isolation** | Single shared DB; isolation by app-layer `WHERE` only | **Hybrid** schema-per-tenant **+** PostgreSQL RLS with `FORCE ROW LEVEL SECURITY` + default-deny + signed-JWT tenant binding + 2 AST CI gates at baseline 0 | `apps/tenancy/`, `apps/schools/migrations/0026_rls_policy_default_deny.py`, `0048_force_rls_on_all_enabled_tables.py`, `scan_tenant_queryset_safety.py` |
| **Local-first pricing** | Per-region multi-million-dollar consulting deploys; US config breaks abroad | **PPP engine live**: `CountryMultiplier` (A/B/C zones + tax) → `compute_localized_price()` → `compute_subscription_price_for_school()`, **249-country audit passes**, all money `Decimal` | `apps/billing/regional_pricing.py`, `apps/siteconfig/models_platform_catalog.py`, `docs/generated/pricing_ppp_matrix_audit.json` |
| **Offboarding / data portability** | Legal letters, manual SQL extracts, weeks | 10-stage lifecycle spine + soft-delete + grace, operator queue, dual-approval, legal hold, dry-run, **portable ZIP export** (JSON + canonical CSV) | `apps/schools/tenant_offboarding.py`, `apps/lifecycle/`, `apps/schools/super_views_offboarding_queue.py` |
| **Offline resilience (3G)** | None — online-only portals | Service-worker outbox (Lamport-clocked), encrypted IndexedDB drafts, wizard server-state (`SetupProgress`), weak-connection drip mode | `static/js/service-worker.js`, `form-draft-save.js`, `rmc-wizard-offline-intake.js`, `apps/setup_studio/wizard_state_resolver.py` |
| **Telemetry cost** | Datadog / New Relic passed through as price | **Zero paid-vendor lock-in**: pluggable metrics bridge (Prometheus / StatsD / structured-log / noop), `/metrics/`, 13 coded SLOs | `apps/observability/metrics.py`, `apps/observability/slo.py` |

## 2. Real gaps (the honest backlog, ranked by leverage)

Each row is a **confirmed** gap from the grounded audit — `ABSENT` means it does
not exist; `PARTIAL` means it exists but stops short.

### Offboarding — "deactivation must actually switch the tenant OFF"
| # | Gap | State | Why it matters (owner/operator) |
|---|---|---|---|
| O1 | Custom domain not unbound on deactivate | ~~ABSENT~~ **CLOSED 2026-06-22** | A switched-off tenant kept a live white-label hostname → confusion + routing liability. **Fixed** below. |
| O2 | Billing not suspended on deactivate (only explicit `freeze`) | ~~PARTIAL~~ **CLOSED 2026-06-22** | A deactivated tenant stayed billable. **Fixed** below. |
| O3 | Data export not automatic on closure request | ~~PARTIAL~~ **CLOSED 2026-06-22** | `request_self_service_closure` triggers `run_wind_down_export` automatically; tests in `test_offboarding_auto_export.py`. |
| O4 | Remote provider (Stripe) cancel stubbed | ~~PARTIAL~~ **CLOSED 2026-06-24** | `stripe_remote_cancel.cancel_stripe_subscription` + default `BILLING_REMOTE_CANCEL_ADAPTER`; pluggable via env override. |

### Local-first billing
| # | Gap | State | Move |
|---|---|---|---|
| B1 | No scheduled invoicing beat (operator runs a command) | ~~PARTIAL~~ **CLOSED 2026-06-24** | `scheduled_invoicing.py` + hourly Celery beat; tenant-local day-of-month + hour window via `is_invoice_generation_due_for_school`; wired into `auto_generate_fee_invoices` task. |
| B2 | No per-country plan SKU variants (one base × multiplier) | ~~ABSENT~~ **CLOSED 2026-06-24** | `Plan.regional_sku_overrides` + `regional_sku_override_for()` + billing resolver; migration `0202_b2_sku_overrides_b4_holding_rollup`; tests `test_regional_sku_override.py`. |
| B3 | Tax at country level only | ~~PARTIAL~~ **CLOSED 2026-06-24** | `SubdivisionTaxRate` platform catalog + `tax_engine._subdivision_tax_rate()` overrides country rate when `subdivision_code` supplied; wired through `compute_localized_price`. |
| B4 | Single currency per tenant | ~~PARTIAL~~ **CLOSED 2026-06-24** | `HoldingCurrencyRollup` model + `holding_rollup.materialize_holding_currency_rollups()` aggregates sub-school billing by currency (no FX fiction); tests `test_holding_currency_rollup.py`; verifier `verify_holding_currency_rollup_b4.py`. |

### Proactive AI resilience
| # | Gap | State | Move |
|---|---|---|---|
| R1 | No keystroke-level server persistence of in-progress wizards | ~~ABSENT~~ **CLOSED 2026-06-24** | `persist_step_draft` + `WizardStepDraftSyncView` + `rmc-wizard-delta-sync.js` debounced POST to `SetupProgress.draft_answers`; merged into form on reload. |
| R2 | No auto UI rehydration on reconnect | ~~ABSENT~~ **CLOSED 2026-06-24** | `rmc-reconnect-rehydrate.js` — after SW `sync-complete` / `sms-sync-end`, hydrates offline mirror then triggers HTMX `rmc-reconnect` + `rmc:reconnect-rehydrate` for health widgets. |
| R3 | No background-sync periodic retry | ~~PARTIAL~~ **CLOSED 2026-06-24** | `service-worker.js` — `periodicsync` on `rmc-offline-queue-drain` + `registerOfflineSyncRetries()` on activate/enqueue; drains outbox when tabs are closed (Chromium Background Sync / Periodic Sync). |

### Observability (tenant-facing)
| # | Gap | State | Move |
|---|---|---|---|
| T1 | No tenant-visible latency/SLO dashboard (only health score) | ~~ABSENT~~ **CLOSED 2026-06-23** | `TenantPerformanceSnapshot` + `/authentication/backend/performance/` — 7-day timeline, friction proxy, platform commitments (honest targets), lifecycle events; linked from operational health strip. |
| T2 | SLOs defined but not operationalized as alert rules | ~~ABSENT~~ **CLOSED** | `apps/observability/prometheus_alert_rules.py` + `manage.py emit_prometheus_alert_rules` → `deploy/observability/slo_alerts.yml`; tests in `test_prometheus_alert_rules.py`. |
| T3 | No free collector in the self-host stack | ~~ABSENT~~ **CLOSED** | `deploy/observability/docker-compose.yml` — Prometheus + Grafana OSS; pairs with `/metrics/` when `OBSERVABILITY_METRICS_BACKEND=prometheus-client`. |

## 3. First increment shipped this pass (O1 + O2)

**"Deactivation now actually deactivates."** One coherent, tested change in
`apps/schools/control_plane_lifecycle.py::apply_school_lifecycle_action`:

- **Custom-domain teardown** (new `apps/schools/domain_unbind.py::unbind_custom_domains`):
  on `deactivate`, every verified `CUSTOM` `SchoolDomain` is marked unverified
  (`is_verified=False`, `verified_at=None`) and `School.custom_domain_verified`
  is cleared, so the hostname stops resolving to live content. **Reversible** —
  the rows and the `custom_domain` string are retained so reactivation re-runs
  DNS verification; permanent purge already drops the rows via the `School`
  CASCADE. A `DOMAIN_UNVERIFIED` provisioning event records it. Subdomains are
  untouched.
- **Billing freeze on deactivate**: `_target_subscription_status_for_school`
  now returns `SUSPENDED` whenever the school is not active, and
  `activate`/`deactivate` were folded into the subscription-resync branch, so a
  switched-off tenant is no longer billable and a reactivated one resumes.

No migration (existing fields + existing `DOMAIN_UNVERIFIED` event type).
Validated: 9 teardown/lifecycle tests + 16 lifecycle-action regression tests +
migration-drift 0 + 6 architectural gates green.

## 4. The reusable Dominance Prompt

Paste this to run the next loop on any capability area. It encodes the rules
that keep us ahead **and** honest (the previous external blueprint failed both).

```
ROLE: Principal architect of RunMyCampus — the global school OS (Django,
schema-per-tenant + RLS, Decimal money, Django templates + vanilla rmc-*.js).
Active code in beta/school-management-system/.

OBJECTIVE: Extend the platform toward global dominance on <CAPABILITY AREA>,
local-first for every tenant across 250+ countries, AI-proactive, with the
operator/owner experience as the lens. Rule of the game: simplicity, creativity,
logical flow.

NON-NEGOTIABLES (these are why we win, do not break them):
- VERIFY FIRST. Map what already exists (grep/read real files) before claiming a
  gap. Most "missing" features already exist more maturely — do not duplicate or
  fork a second architecture. Cite file paths.
- MATCH THE STACK. Django + schema/RLS isolation (app.current_school_id, never a
  new GUC), Decimal money (scan_money_float is zero-tolerance), no hardcoding
  (7-layer cascade), no raw f-string SQL, no React/Node bolt-ons.
- TENANT-SAFE. Every tenant-scoped query carries school=; respect RLS + the
  scan_tenant_queryset_safety gate.
- PREFER NO MIGRATION. Reuse existing fields/enums/events; if a migration is
  truly needed, keep it a single clean leaf.
- SURFACE SCOPE. Name the breadth and the strategic subset before sweeping.

LOOP (do not stop until clean):
  AUDIT (grounded, with file paths)
  -> identify the highest-leverage REAL gap (ABSENT/PARTIAL, not already built)
  -> FIX + ADD VALUE (production code, no TODOs/placeholders)
  -> TEST (unit + integration; run them, paste results)
  -> VALIDATE (architectural gates + migration drift, all green)
  -> RE-AUDIT for gaps (concurrency, unvalidated input, double-booking, leaks)
  -> FIX + CLOSE
  -> repeat until 100% done, secure, and structurally complete.

OUTPUT: structural code + schema + tests, path-scoped commit, honest report of
what is done vs deferred. No filler, no "VERIFIED DONE" without runnable proof.
```

## 5. Why this is the dominance play

The incumbents sell lock-in; we sell **clean exits, local pricing, offline
trust, and zero-cost transparency** — features that make switching *to* us safe
and switching *away* painless, which is exactly what wins a global market where
every district fears being trapped. We carve the blue ocean by being the only
vendor whose **simplicity is a moat**: each loop above closes one real gap, fully
tested, no rebuilds. **B1, R1, O4 closed 2026-06-24** (see §2). Next loop targets **B2** (per-country plan SKU overrides), **R3** (SW Background Sync drain), or **B3** (subdivision tax table).
