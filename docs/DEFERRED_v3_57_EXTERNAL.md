# v3.57.0 Platform-Parity Sweep — Deferred / External Catalog

**Date:** 2026-05-21
**SW shipping:** `sms-v3.57.0-platform-parity-sweep-2026-05-21`
**Companion docket:** [`CSS_RETIREMENT_DOCKET.md` § v3.57.0](CSS_RETIREMENT_DOCKET.md)

The originally-scoped 27-agent fan-out hit the Anthropic account session-quota
wall mid-execution. The v3.57.0 wave that **did ship** is the in-repo
continuation produced directly by the orchestrator (no further agents) after
the wall. This document is the SOT for what is intentionally NOT in v3.57.0
and what wave should pick it up.

## Classification rules

- **agent-only** — needs parallel multi-agent execution to be coherent within
  one orchestrator window (new Django apps with cross-cutting concerns,
  multi-template adoption sweeps, etc.). Schedule for the next agent-budget
  window.
- **counsel-pending** — legal / privacy review blocks shipping; not fixable
  by engineering work alone.
- **adoption-wave** — primitive shipped in v3.57.0; consumer wiring is a
  separate, narrower wave (lower risk to ship after the primitive bakes).
- **time-blocked** — calendar-bound (90-day field test windows, scheduled
  ramps, vendor release dates).
- **operator-burndown** — drift detector tripped at non-zero baseline;
  operator wave to triage and resolve site-by-site.

## Catalog

### New Django apps (agent-only)

| App | Purpose | Scope |
|---|---|---|
| `apps/incidents/` | First-class incident timeline + post-mortem registry | Models (`Incident`, `IncidentEvent`, `Postmortem`) + migration + admin + cockpit panel + tests. Currently incident state lives ad-hoc in `apps/observability/incident_services.py`. |
| `apps/multitenant_ops/` | Cross-tenant operator runbook + bulk action authority audit | Models (`OperatorRunbook`, `BulkActionAttempt`, `BulkActionApproval`) + migration + dual-control approval flow + tests. |
| `apps/field_operations/` | Field-staff workflow (school visits, on-site IT, deploy crews) | Models (`FieldVisit`, `FieldVisitTask`, `FieldExpense`) + migration + offline-PWA wrap + tests. |

**Why deferred:** each needs migrations + models + admin + view classes + per-tenant scoping markers + at least 20 tests + cockpit-panel template + new context-processor injection points. Trying to ship three new apps simultaneously without dedicated agents to keep file boundaries clean would cause migration conflicts and import cycles.

### Remaining scanners (agent-only)

| Scanner | What it catches |
|---|---|
| `scan_email_plaintext_twin.py` | Every `*.html` email template must have a `*.txt` plaintext twin with parity content (per FERPA accessibility; some districts mail-clients-only render text). |
| `scan_sms_template_length.py` | SMS templates exceeding 160 chars without an explicit `# sms-multipart-allow:` marker. |
| `scan_pdf_brand_cascade.py` | PDF render templates (transcripts, invoices, report cards) using literal hex instead of the per-tenant `--brand-*` cascade via `rmc-print-v2.css`. |
| `scan_pwa_install_prompt_coverage.py` | Pages eligible for the PWA install prompt that don't carry the manifest hint. |
| `scan_a11y_aria_coverage.py` extensions | The base scanner shipped pre-quota; extending it to cover interactive widgets + landmark roles + skip-link patterns is a follow-up. |

### Counsel-pending items

| Item | Blocked on |
|---|---|
| MAA v2.0 promotion flip | External counsel signoff PDF (`docs/legal/maa_v2_signoff.pdf` not yet delivered) |
| FACTS / Skyward write-path unblock | Open counsel docket at `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` (CFAA / DMCA § 1201 / state computer-trespass questions) |
| `scan_pii_logging_smell.py` strict-mode 100% audit | Privacy counsel walk-through of remaining warn-only logger calls |

### Time-blocked items

| Item | Unblocks |
|---|---|
| Webhook verifier SDK 1.0.0 graduation | 90-day field test ends ~2026-08-19 (started 2026-05-19) |
| HSM bridge implementation for one of the 4 reserved audit-signing backends | Awaits operator selection of cloud HSM provider |
| Reproducible Tauri builds + in-toto attestations | Awaits Tauri 2.1 upstream release |

### Adoption-wave items (primitives shipped in v3.57.0)

| Primitive | Adoption work |
|---|---|
| `rmc-pagination-grammar.css` | Wire into 5 forks: admin Django changelist override / ~~DRF Redoc page template~~ / ~~`portal-ui-components.css` `.portal-page-pager` retirement~~ / ~~`backend-dashboard-v2.css` `.bk-dash-pager` retirement~~ / `phase2-portal-bundle.css` `.rbac-page-pager` retirement. Delete forks AFTER one full adoption wave.

#### Status (2026-05-22, v3.57.11)

Django admin `.paginator` + ~8 bespoke Bootstrap pagination markup sites layered with `rmc-pagination*` classes via additive CSS in `rmc-pagination-grammar.css`. 3 originally-listed forks (`.portal-page-pager`, `.bk-dash-pager`, DRF Redoc) confirmed absent from tree — likely mass-purged in an earlier wave. Closed item. |
| `rmc-print-v2.css` | Adoption into transcript / report-card / invoice templates. Each template needs `.rmc-print-v2` wrapper + brand-block + watermark prop wiring. |
| `rmc-email-civic.css` | Adoption into 5+ transactional email templates: welcome / activation / low-balance / migration receipt / webhook confirmation. Each needs civic 4-tier markup restructure. |
| `cockpit_front_office_200x` (10 sections) | Need 10 partial templates under `templates/partials/cockpit/_front_office_*.html` + sparkline service wiring per panel. |
| `cockpit_tenant_v3_extended` (10 sections) | Need 10 partial templates under `templates/partials/cockpit/_tenant_v3_*.html` + per-role dashboard wiring + privacy-gate enforcement for sibling-compare opt-in. |
| Operator admin UI fieldset extension | `apps/siteconfig/forms_cockpit.py::CockpitPayloadForm` needs new fieldsets covering the 20 new sections (schema is ready; form needs additions). |

### Operator burndown items

| Drift detector | Baseline | Burndown shape |
|---|---|---|
| `scan_horizontal_overflow_risk.py` | 55 sites in 11 files | Each site needs either a `text-overflow: ellipsis` + `overflow: hidden` companion declaration OR a categorical `/* horizontal-overflow-risk-allow: <reason> */` marker. Top offenders: `phase2-portal-bundle.css` 2, `portal-ui-components.css` 4, `portal-layout-professional.css` 2. |

### Originally scoped agent waves NOT executed (quota wall)

These were in the v3.57.0 27-agent plan but never started:

* **Wave 4 (A16-A20):** internal eng dashboard / cost transparency / data quality / universal search / admissions
* **Wave 5 (A21-A25):** IEP / crisis comms / document management / unified messaging / curriculum
* **Wave 6 (A26-A27 + C5-C7):** DR portability / workflow engine / AI bias / locale depth / stakeholder voice
* **Wave 7 (C8 + C1-C4):** white-label / component SOT / telemetry / migration screenshots / progressive rollout

Pickup recommendation: queue Waves 4-7 for the next agent-budget window with the same one-agent-per-domain isolation pattern. None of these items are urgent (no shipping deadlines, no security gates trip without them).

## Suggested ordering for the next wave (v3.58+)

1. **Adoption sweep first** — the primitives shipped in v3.57.0 are only useful once consumers adopt them. One agent per CSS bundle (pagination / print / email) + their template fork retirements.
2. **Operator admin UI fieldset extension** — single-agent wave; the schema is ready, the form just needs the new fieldsets.
3. **20 cockpit partial templates** — two agents (front-office + tenant-v3 extended), one partial per section.
4. **Burndown of `scan_horizontal_overflow_risk.py`** — single-agent wave, mechanical with text-overflow:ellipsis + overflow:hidden additions.
5. **Remaining 5 scanners** — single agent.
6. **Three new Django apps (incidents / multitenant_ops / field_operations)** — three agents, one app each.
7. **Wave 4-7 luxury sweeps** — four parallel agents, one wave each.

Pace expectation: each item above is roughly one focused wave (~1-3 hours of agent work). Don't try to pack more than ~5 agents into a single Anthropic billing window after observing the v3.57.0 quota wall.
