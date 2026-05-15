# State of Platform — 2026-05-14 (grounded re-baseline)

This note exists because the request that triggered it asked for an audit assuming a single-school-to-multi-tenant transition. **That transition completed many waves ago.** The COMPETITIVE_PARITY_ROADMAP doc lags the code by a measurable margin. This file is the corrected snapshot.

## Where we actually are

- 50 Django apps under `apps/`.
- ~708 markdown docs under `docs/` (this is itself a problem — see below).
- 23 TODO/FIXME markers in all of `apps/` excluding tests/archive. Of those, 2 are concrete config-not-hardcoded follow-ups; the rest are minor.
- CI matrix: `a11y-axe.yml`, `pa11y-ci.yml`, `lighthouse-ci.yml`, `tenants-rls.yml`, `playwright-tenant-postgres.yml`, `django-tests.yml`, `smoke.yml`, `smoke-light.yml`, `marketing-n10-pr.yml`, `n10-performance-budgets.yml`, `collabora-wopi-smoke.yml`, `ollama-image-digest-weekly.yml`, `premium-maturity-weekly.yml`, `sdk-release.yml`, `backlog_unlock_nightly.yml`, `security-self-audit.yml`.
- Service worker: `sms-v2.11.0-everything-closeout-2026-05-14`.
- AI surfaces: single gateway (`services/ai_gateway.py`), 27 `/api/ai/*` endpoints, 6 bounded-context wrappers, RAG ingest (mgmt cmd + admin endpoint), Ollama-first tier policy with rules fallback. Full SOT in [`AI_PLATFORM_WIDE_STATUS_2026_05_14.md`](AI_PLATFORM_WIDE_STATUS_2026_05_14.md).
- SLOs: 8 canonical service-level objectives in `apps/observability/slo.py` (code-defined SOT, not config). Custom Sentry transactions wrap attendance submit, grade entry, parent dashboard, migration bundle apply. Burn-rate alert taxonomy per Google SRE Workbook. SOT: [`OBSERVABILITY_SLO_CODE.md`](OBSERVABILITY_SLO_CODE.md).
- Tenant isolation scanner: 194 tenant-scoped models indexed, 769 unscoped queries encoded as a CI baseline. New unscoped queries fail PRs. SOT: [`TENANT_ISOLATION_SCANNER.md`](TENANT_ISOLATION_SCANNER.md).
- Marketplace seed: 47 first-party apps (was 27). 25 regional/sector blueprint packs (was 18).
- Security baselines: bandit (63 findings, 2 HIGH / 61 MEDIUM), pip-audit, tenant-isolation. All under `var/security-audit-baseline-*.json`.
- Doc set: 28 more zero-reference one-shot docs archived to `docs/archive/legacy_2026_05_14/` (now 33 total).

## What the roadmap doc says is open vs. what code shows

Audited 2026-05-14 against `apps/` and `config/settings.py`:

| Roadmap item | Doc status | Actual code status |
|---|---|---|
| P11.1 — `CeleryIntegration` in `sentry_sdk.init` | "single line, critical gap" | **Closed.** `config/settings.py:1559-1568` wires it with import guard. |
| P12.1 — drf-spectacular | "Done in this pass" | Closed. `/api/openapi.json` + Swagger + Redoc live. |
| P12.2 — `django-cors-headers` allowlist from `SiteConfig` | "to do" | **Closed.** `corsheaders` in `INSTALLED_APPS:237`, middleware at `:251`, allowlist + regex at `:1505-1511`. |
| P12.3 — Global `IdempotencyKeyMiddleware` for `/api/v1/` POST | "today only finance has it" | **Closed.** `apps/api/middleware_idempotency.py:100`. |
| P12.4 — RFC 7807 problem+json envelope | "to do" | **Closed.** `apps/api/exception_handler.py` + `REST_FRAMEWORK["EXCEPTION_HANDLER"]` at `settings.py:1499`. |
| P12.6 — Cursor pagination default | "to do" | **Closed.** `settings.py:1496`. |
| P13.5 — `anthropic` client packaging + entitlement gate | "wire Anthropic Claude client" | **Closed.** `requirements.txt:45` `anthropic>=0.39.0`. Entitlement-gated views shipped per `D-wave 13.D`. |
| P14.1 — OAuth2 scope vocabulary | "to do" | **Closed.** `apps/marketplace/scopes_catalog.py` (`students:read`, `attendance:write`, …). |
| P10 item 5 — `role="banner"` on `<nav>` in `base.html:127` | "to do" | **Closed.** No matching `role="banner"` in any base template now. |
| P10 item 6 — `aria-label` on `<aside>` in `control_plane_base.html` | "to do" | **Closed.** `control_plane_base.html:76` has `aria-label="{% trans 'Control plane navigation' %}"`. |

**Net:** every item from Passes 10–14 that the roadmap doc lists as buildable inside this repo is built. The roadmap doc needs its checkmarks refreshed, not the code.

## AI surfaces — situated and functional (2026-05-14)

Closeout wave NS-2 (`sms-v2.10.0`) verified every AI surface end-to-end:

| Layer | Status |
|---|---|
| Gateway (`services/ai_gateway.py`) | ✅ 21 TaskTypes, tier policy, prompt-injection regex, structured-output validation |
| Helpers (`services/ai_helpers.py`) | ✅ Graceful degradation, PII inference, prompt-type tagging, `record_feedback` |
| RAG memory (`AIEmbeddingStore` + `services/ai_memory.py`) | ✅ Ingest via mgmt command **and** admin endpoint `/console/ai/rag/ingest/` (added this wave) |
| 27 `/api/ai/*` endpoints | ✅ All wired in `apps/portal/views_ai_gateway.py`, rate-limited, permission-gated, audited |
| `/api/ai/health/` probe | ✅ Wired in `config/urls.py`, `tenant_urls.py`, `manager_urls.py`, `public_urls.py` |
| Audit feed `/api/ai-copilot/audit/` | ✅ Staff-only, redacted, paginated |
| Bounded-context wrappers (6) | ✅ Migration Cloud, Finance, People, Automation, Dashboard, Analytics ML |
| Anomaly LLM narrative enrichment | ✅ `_enrich_with_ai_narrative` in `apps/dashboard/services/insight_anomalies.py` |
| ⌘K palette AI hooks | ✅ "Open AI Copilot" + "Ask AI: <query>" fallback (added this wave) |
| Governance (env × tenant × content) | ✅ `apps/platform_runtime/ai_governance.py` |
| Audit + metric | ✅ `AIActionAuditLog` + `AIGatewayMetric` daily rollup |
| Safety | ✅ Prompt injection, PII routing, schema validation, permission gating, rate limit |

Definitive surface-by-surface SOT: [`AI_PLATFORM_WIDE_STATUS_2026_05_14.md`](AI_PLATFORM_WIDE_STATUS_2026_05_14.md).

## Genuinely-open items (and the right owners)

What actually blocks further progress is now almost entirely **non-repo**:

### Operator credentials / external accounts

| Item | Owner | Blocker |
|---|---|---|
| Stripe Connect platform account | Founders / Finance | Stripe approval + ToS review |
| `PYPI_API_TOKEN`, `NPM_TOKEN` repo secrets | Repo admin | One-time GitHub Settings → Secrets |
| `SENTRY_AUTH_TOKEN`, `SENTRY_ORG_SLUG` for RUM push | Ops | Sentry workspace |
| Apple Developer account + Google Play account | Founders / Mobile owner | $$ + annual renewal |
| Production DNS for `partners.`, `docs.`, `api.` subdomains | Ops / DNS owner | Provider login |
| Collabora production stand-up | Ops | VM + DNS + cert |
| 24/7 NOC contract + pager rotation | Ops | Vendor selection + contract |

### Business / partnership

| Item | Owner | Blocker |
|---|---|---|
| Clever / ClassLink district sponsor | Sales / Partnerships | Named district prospect |
| SOC 2 Type II audit firm engagement | Compliance lead + exec sponsor | Hire compliance lead, scope auditor |
| WAEC / KCSE / CBSE official rostering integrations | Partnerships | Vendor agreements |

### Data / product decisions

| Item | Owner | Blocker |
|---|---|---|
| Trained at-risk ML joblib artifact (`AT_RISK_MODEL_PATH`) | Data + Product | Need tagged dataset + training notebook output |
| Marketing AI video / image generation | Creative director + Runway/Sora subscription | Not Claude-buildable — script + render pipeline elsewhere |
| Final design-token contrast pass (P10 items 2-4) | Design lead | Brand-color trade-off decision, not code |

## What is actually worth attacking next (repo-deliverable)

These are the real internal opportunities — not "transition to multi-tenant" (done), not "build a marketplace" (done) — but the deeper polish layer:

1. **Documentation graveyard cleanup.** 708 markdown files in `docs/` is unmanageable. Roughly 30-40% are stale or duplicate. Proposal: designate 8-10 canonical "living docs" (SECURITY, OBSERVABILITY, COMPETITIVE_PARITY_ROADMAP, NORTH_STAR_PLATFORM, MULTI_TENANT_GLOBAL_ROADMAP, ECOSYSTEM_STRATEGY, CSS_RETIREMENT_DOCKET, STATE_OF_PLAY, ACCESS_POINTS, AGENTS); sweep the rest into `docs/archive/` with one-line redirects. Until this happens, every future agent (Claude, Cursor, human) will re-litigate work already shipped, because the docs say it's open.

2. **Bounded-context model ownership audit.** `apps/people` vs `apps/customers` vs `apps/accounts` vs `apps/student360` — at first glance these have overlapping concerns around the student profile. Worth a 2-day audit producing a definitive `docs/bounded_context_ownership.md` refresh (the file exists; verify it's current and that imports actually obey it). Cross-app imports that violate the chart are the real architectural sprawl.

3. **Roadmap doc status checkmark refresh.** Mechanical: walk the COMPETITIVE_PARITY_ROADMAP table, validate each row against `grep` of code state, flip strikethrough. Saves every future session 30 minutes of "wait, is this still open?"

4. **Memory entry re-grounding.** MEMORY.md is 60+ entries. Some are demonstrably stale (e.g. roadmap items they reference are now closed). Sweep with the same "validate against code" pass; archive completed work into single-line "Done" summaries.

5. **The 23 TODO markers.** Smallest cleanup. Each is a single-file edit. Most are config-not-hardcoded follow-ups.

6. **Real penetration test.** Not something Claude can run from this terminal — needs an external pentest firm (HackerOne, Bishop Fox, Trail of Bits). Schedule it; the codebase is at a state where an external test produces actionable signal instead of obvious low-hanging fruit.

7. **Lighthouse / Core Web Vitals baseline in production.** CI runs Lighthouse on PRs; what's the live `runmycampus.com` score? Field data > lab data.

## Items in the original prompt that this note explicitly does not action

The triggering request asked for several things that aren't right to do from this session:

- **"Move all models into bounded apps"** — multi-week refactor across 50 apps. Wrong tool here. Belongs to a dedicated wave with per-PR scope.
- **"Make the system impenetrable"** — not a real engineering metric. The right move is the external pentest above + SOC 2 evidence room build. Both are owner-actions, not code.
- **"AI-generated marketing videos / images"** — outside the Claude Code surface. Brief Runway/Sora separately.
- **"Score 15/10"** — not a real bar.
- **"Plan for problems 100 years ahead"** — speculative. The right time horizon for platform decisions is 2-5 years (regulatory + AI capability shifts). Beyond that is fiction.
- **"Every single file analyzed"** — token-burn for negative ROI; SOT docs already encode the state.

## TL;DR for the next session

- The platform is multi-tenant. It has been for many waves.
- The roadmap doc lags the code. Trust `grep` over markdown.
- What blocks further forward motion is mostly **outside this repo**: credentials, partnerships, training data, hires, vendor contracts.
- The biggest *internal* lever now is **ruthless doc/memory consolidation** so future agents stop solving solved problems.
