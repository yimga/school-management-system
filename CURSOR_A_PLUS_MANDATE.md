# RUNMYCAMPUS — A+ END-TO-END IMPLEMENTATION MANDATE (for Cursor)

> **Hand this entire file to the executing agent (Cursor / Claude Code).** It contains three prompts:
> 0. **PROMPT S — THE STRATEGY LAYER** (read FIRST: ambition, diagnosis, where-to-play / not-play, the choice-cascade gate, and the strategic scorecard rows. Strategy AIMS the build; it never relaxes it).
> 1. **PROMPT A — THE BUILD MANDATE** (implement everything end-to-end to A+ — ≥98/100, i.e. **9.8/10 minimum under the lowest-dimension scoring regime** — on every metric).
> 2. **PROMPT B — THE FINAL AUDIT** (re-audit, produce an A+ scorecard, and decide GO / NO-GO; if NO-GO, loop back to Prompt A).
>
> Run **Prompt A** until it self-reports all gates green, then run **Prompt B**. If Prompt B returns NO-GO, feed its findings back into Prompt A and repeat. **Do not stop until Prompt B returns GO. Standards are never softened — softening the bar is itself a NO-GO.**

---

## CONTEXT YOU ARE OPERATING IN (read first, do not skip)

- **Repo:** Django 5 multi-tenant School Management OS ("RunMyCampus"). Active codebase is `beta/school-management-system/`. ~1M LOC, 54 apps, ~700 models, 1,011 migrations, ~10,000 tests, **237 CI-wired architectural gates**, a self-protecting meta-gate (`scripts/verify_ci_gate_wiring.py`, `REQUIRED_GATES`).
- **Production DB is PostgreSQL.** Local/test default is SQLite. **SQLite hides Postgres-only bugs (RLS, exclusion constraints, JSON ops, constraint timing). You MUST validate correctness-critical work on real Postgres** (workflows already exist: `tenants-rls.yml`, `playwright-tenant-postgres.yml`).
- **This is a SHARED, HIGH-CHURN working tree.** Other agents/sessions commit constantly. Obey the **Integrity Rules** (Part 0). Never `git add -A`. Never delete or revert work you did not author. Never use `|| true`, `2>/dev/null`, `--no-verify`, `.skip`, `xfail`, or baseline edits to make a gate *appear* green.
- A prior independent audit (summarized in Part 2) found the platform is **real and strong on infrastructure** but that **marketing/docstrings run ahead of wiring** in several headline areas. **Your job is to make reality match — and exceed — the claims, with proof.**

---

# PROMPT S — THE STRATEGY LAYER (read FIRST; strategy governs the build)

> Added 2026-07-05 after reviewing the "From Reactive Planning to Strategic Thinking" framework (five elements of strategy · strategic-thinking mindsets · four failure modes · choice cascade). Honest self-diagnosis of this mandate: it has a world-class **execution and learning system** (the A→B loop) but was exposed to three of the four classic strategy failure modes — *too broad* ("everything ≥98" with no sequencing), *too activity-based* (metrics without the choices behind them written down), and *trade-off-avoidant* (250 countries treated as one undifferentiated launch). This layer fixes the aim. **It relaxes nothing** — every gate, ceiling, and the 9.8 minimum stand exactly as written. Strategy decides the ORDER and the WHY; Prompts A and B still decide DONE.

## S1 — AMBITION (which mountain)

Become the **operating system for schools worldwide** — the way Shopify is for commerce, AWS for infrastructure, Salesforce for CRM, Linux for sovereign computing, Amazon for breadth. Concretely: any school on Earth — from a 3-teacher school on a cash economy and a 2G connection to a 40-campus network — can self-serve from signup to a fully operating, locally-native, offline-capable school OS **in under one hour, with no consultant**, and can leave at any time with all of its data (which is exactly why it won't want to).

## S2 — DIAGNOSIS (what is really true)

- Incumbents (PowerSchool, Blackbaud, Veracross, Skyward, FACTS) are US/EU-centric, connectivity-assuming, USD-priced, consultant-installed, and lock data in. **Their moat is switching cost, not product love.**
- The underserved majority of the world's schools run on bad networks, cheap devices, cash + mobile money, local grading scales, local languages, and — increasingly — data-sovereignty law. Nobody serves them with premium self-serve software; they get spreadsheets or thin local clones.
- Therefore the real contest is NOT feature parity with incumbents. It is **(a) instant genesis, (b) local-native from day one, (c) offline survival, (d) sovereignty, (e) painless migration IN.** That is why metrics 25–28 are the moat, and why **Migration Cloud is the wedge that attacks the incumbents' only moat.**

## S3 — STRATEGIC CHOICES (where we play, how we win, what we will NOT do)

**Where we play first (beachheads, not 250-at-once):** self-serve private K-12 schools in connectivity-constrained, currency-diverse markets — Tier-1 beachhead cohorts per the country-readiness matrix (W7): West Africa (NG/GH/CM/CI), East Africa (KE/UG/TZ/RW), South Asia (IN/PK/BD/NP), SE Asia (PH/ID/VN), LatAm (BR/MX/CO/PE). The 250-country ambition is a **readiness LADDER, not a launch plan**: a country is "open" when its readiness row (language, grading scale, currency + payment rail, calendar, residency posture, identity fields) is green. The country-readiness matrix is a strategy artifact, not a metadata table.

**How we win:** the four moats (metrics 25–28) + time-to-value (S-TTV below) + PPP-honest pricing + the Migration Cloud switching-cost attack + the marketplace/SDK ecosystem flywheel + local-first AI grounded in tenant truth.

**What we will NOT do (binding not-do list — violating it is strategic drift):**
1. No consultant-led implementations. Anything that requires a consultant is a product bug.
2. No per-school forks or custom code. Runtime configurability (EAV, cascade, manifest) is the only personalization path.
3. No US-district-procurement play until the self-serve engine is proven in beachheads. Districts are a Tier-2 entry earned by reputation, not RFPs.
4. No scale-out infra (K8s/Ceph/NATS/Kafka/ClickHouse) before the >50-school / district-isolation trigger. Portability preserved; money saved.
5. No counsel-blocked write-paths (FACTS/Skyward), no fake green, no bar-softening — ever.
6. No new feature work that cannot name its strategic choice (see the S7 gate).

## S4 — CAPABILITIES & UNIQUE ASSETS (what we uniquely leverage)

~1M-LOC multi-tenant OS with FORCE-RLS isolation · a self-protecting CI-gate culture (a **quality moat no competitor can copy quickly**) · two-rail offline (SODP+WAL) + CRDT governance · Migration Cloud (6-vendor extractors + MAA legal rail + sealed-box crypto) · 250-country pricing + PPP engine · world-scale grading registry · marketplace + workflow engine + PDP · per-tenant DR + self-host posture · 20 locales · RBAC-gated local-first AI copilots.

## S5 — EXECUTION & LEARNING SYSTEM (two loops, not one)

- **Loop 1 — repo truth (running, unchanged):** PROMPT A builds → PROMPT B adversarially re-scores → B's next-work packet binds the next wave. 9.8 minimum, lowest-dimension scoring, no averaging, no exceptions.
- **Loop 2 — market truth (currently MISSING; now mandatory to stand up):** beachhead pilots → activation/retention telemetry → country-ladder promotion. No amount of repo work substitutes for this loop. B classifies its legs EXTERNAL_PROOF_REQUIRED, but the canvas (S9) surfaces them every cycle so they cannot be forgotten. **The single most strategic decision currently mis-filed as "operational": choosing and signing the first pilot cohort.**

## S6 — BENCHMARK DNA (what "the X of education" means, concretely)

| Benchmark | Their edge | Our counterpart (repo-real today) | Gap to close |
|---|---|---|---|
| **Shopify** | Signup → first sale in minutes | Onboarding wizard genesis→launch | Measure + gate **TTV: signup → operating school < 1 hour** (S1 row) |
| **Linux** | Sovereignty, no lock-in, trust | Self-host runtime + encrypted export + residency enforcement (metrics 27/28) | Restore/self-host proven in CI; publish the sovereignty pledge |
| **Salesforce** | Ecosystem + configurability | Marketplace, EAV, workflow engine, published SDKs | Developer-adoption metrics; first external app; partner program |
| **AWS** | Reliability + primitives + trust | RLS, 26+ gates, DR, observability, SLO registry | Postgres-CI ground truth always green; public status/SLO page |
| **Amazon** | Start narrow, win, expand (books → everything) | Country-readiness matrix (W7) | Beachhead-ladder discipline; resist 250-at-once |

## S7 — THE CHOICE-CASCADE GATE (for every NEW workstream)

Before any agent opens a NEW workstream (anything beyond the 28 metrics + S-rows), it must answer, in ≤10 lines on the scoreboard: **problem? · who is affected? · success measure? · options considered? · trade-off accepted? · capability leveraged? · what must be true? · what we measure in 90 days.** A workstream that cannot answer is REJECTED as activity-without-direction (failure modes 1–2). This gate sequences work; it NEVER excuses skipping a red gate or shrinking an existing metric's bar.

## S8 — STRATEGIC SCORECARD ROWS (PROMPT B scores these alongside the 28)

The repo-side enabler of each row is held to the same ≥98 / 9.8 bar; the market leg is classified honestly (EXTERNAL_PROOF_REQUIRED until pilots run — never counted as done, never dropped from the register):

| S# | Strategic metric | Bar |
|---|---|---|
| S1 | **Time-to-value**: signup → operating school (real data, no consultant) | < 1 hour, E2E-proven |
| S2 | **Migration wedge**: incumbent SIS → RunMyCampus, end-to-end | < 1 day per school, proven per vendor |
| S3 | **Country readiness ladder** | Tier-1 beachhead rows 100% green in the W7 matrix |
| S4 | **Local-money completeness** | ≥3 live rails + PPP tuition + cash micro-ledger (metric 26) |
| S5 | **Offline survival** | 7-day contract PROVEN (metric 25) |
| S6 | **Sovereignty pledge** | Export + self-host + residency proven (27/28) AND published |
| S7 | **Ecosystem flywheel** | SDKs published, marketplace live, first external app shipped |
| S8 | **Market-truth loop** | Pilot cohort signed; activation/retention telemetry flowing |

## S9 — 90-DAY STRATEGIC CANVAS (refresh every audit cycle; append, never delete)

- **Core problem:** incumbent-locked + underserved schools cannot self-serve a world-class school OS.
- **Changing environment:** AI disruption, data-sovereignty law, mobile-money ubiquity, post-COVID digitization budgets.
- **Priority stakeholders:** school owners/proprietors (buyers) · teachers (daily users) · parents (payers) · students · regulators.
- **Three choices on the table:** beachhead cohort selection · PDP enforcement promotion · config-SOT adoption ratchet.
- **Trade-off accepted:** depth in beachheads over breadth in 250 countries.
- **Advantage leveraged:** the offline + migration + sovereignty moat, compounded by the CI-gate quality culture.
- **90-day measures:** every one of the 28 + S rows ≥9.8 repo-side or honestly EXTERNAL-classified · pilot cohort signed · TTV measured end-to-end.

---

# PROMPT A — THE BUILD MANDATE

You are a **fleet of senior staff engineers** shipping RunMyCampus to **best-in-class, A+ (≥98%) on every metric**. Anything below 98 on any metric is a **NO-GO**. You will deploy multiple parallel agents, verify everything against objective gates, and **keep closing gaps until every gate is green and every metric is ≥98**.

## PART 0 — THE OPERATING CONTRACT (non-negotiable; these rules cannot be waived)

1. **AUDIT-FIRST, NEVER ASSUME.** Before implementing any item, open the actual files and confirm the current state with `file:line` evidence. The audit in Part 2 is a *starting map*, not gospel — verify it. If a claimed gap is already fixed, say so and move on. If you find a NEW gap not listed here, fix it too (the mandate is **expansive**: cover everything, listed or not).
2. **END-TO-END OR IT DOES NOT COUNT.** A feature is "done" only when it is wired **producer → store → server → UI → test → CI gate**. Models without views, services called only by tests, formulas evaluated only in tests, tables that ship empty, and "no-op bridges" all count as **NOT DONE**. (The prior audit caught exactly these.)
3. **EVIDENCE IS MANDATORY.** Every "done" claim must carry: the `file:line` of the implementation, the test that proves it, and the exact command + output proving the relevant gate is at baseline 0 / green.
4. **NO FAKE GREEN.** Forbidden, automatic NO-GO if detected: deleting/weakening tests to pass; `|| true` / `continue-on-error` to mask failures; editing a gate's baseline/allowlist to hide a real finding; `# type: ignore`/bare `except`/`--no-verify`; stubbing a return value to satisfy an assertion; marking a flag enabled without the producer+applier behind it.
5. **TENANT-SAFE BY CONSTRUCTION.** Every new model that holds tenant data MUST have a `school` FK, an RLS enable migration + default-deny policy, and pass `scan_tenant_queryset_safety.py` (baseline 0). Every new query MUST be school-scoped. No raw SQL with f-string-interpolated values (identifiers-only, parameterized values).
6. **POSTGRES TRUTH.** Any work touching RLS, constraints (exclusion/gist), JSON fields, or transactions MUST have a test that runs on Postgres (tag it for `tenants-rls.yml` / `playwright-tenant-postgres.yml`). Do not rely on SQLite passing.
7. **SHARED-TREE HYGIENE.** Stage only the specific files you changed (explicit paths, never `-A`). Run the relevant gates locally before commit. Rebase/fast-forward over peers; never force-push shared branches; never absorb another agent's uncommitted work. Before any push, confirm the tree is intact (`git ls-tree -r HEAD | wc -l` is sane, not collapsed).
8. **DECIMAL MONEY, LOCALE DISPLAY, NO PII IN LOGS.** Honor existing zero-tolerance gates `scan_money_float.py`, `scan_locale_display.py`, `scan_pii_logging_smell.py`.
9. **MIGRATIONS ARE FORWARD-ONLY & REVERSIBLE.** Idempotent data migrations; no destructive hot migrations on populated tables; seed via migration + management command (both), never runtime-only.
10. **DOCS MUST NOT OVERSTATE.** When you finish an item, update its docstring/CLAUDE.md note to describe **only what is wired**, with the proving test named. Remove or correct any docstring that overstates delivered surface.

## PART 1 — MODEL & AGENT FLEET

- **Use the highest-capability frontier model available in Cursor for ALL implementation and audit work** (e.g., the top Claude Opus / max-reasoning tier). **Do NOT use fast/mini/lite tiers** for implementation, security, tenancy, billing, or audit. Lightweight tiers are permitted only for mechanical formatting.
- **Deploy multiple parallel agents** (Cursor background agents / multi-composer). Suggested fleet — run workstreams concurrently where files don't collide; serialize where they do:

  | Agent | Owns | Primary dirs (avoid cross-collision) |
  |---|---|---|
  | **A1 — Tenant Experience Lead** | Tenant shell, onboarding, dashboards, a11y, i18n/RTL, best-in-class UX | `templates/`, `static/css`, `static/js`, `apps/portal`, `apps/setup_studio` |
  | **A2 — Grading & Reporting** | Polymorphic grading wiring, report-card render/PDF/distribute | `apps/evals`, `apps/reports`, `apps/academics` |
  | **A3 — Metadata/EAV Delivery** | Dynamic forms+reports+search, country catalog auto-seed | `apps/metadata`, `apps/people`, `apps/locale` |
  | **A4 — Billing/PPP/Payments** | Seed PPP, tuition scaling, live PSP gateways, entitlements | `apps/billing`, `apps/finance`, `apps/plans_entitlements`, `apps/payroll` |
  | **A5 — Core Ops Features** | Room/asset booking + double-booking constraint, discipline engine, substitute auto-match, inventory, athletics | `apps/schoolops`, `apps/academics`, `apps/school_events`, `apps/people` |
  | **A6 — Security & Compliance** | Rate-limit/lockout, ReBAC enforcement, bandit/SAST, FERPA/GDPR/COPPA, DSAR/residency | `apps/accounts`, `apps/security`, `apps/compliance`, `apps/lifecycle`, `config` |
  | **A7 — Platform/Infra/Perf/Obs** | Celery worker+beat, Postgres test path, performance/N+1, observability, healthz, DR/backups | `config`, `render.yaml`, `apps/observability`, `apps/platform_runtime` |
  | **A8 — Offline/PWA/Realtime** | Homework offline applier+UI, background-sync, WAL completeness, manifest/SW | `apps/wal_stream`, `apps/sync_engine`, `static/js`, `apps/brand_experience` |
  | **A0 — Coordinator/Integrator** | Merges, runs the full gate suite, owns the scorecard, blocks NO-GO | repo-wide (read), gate runs, scorecard |

- **Coordination protocol:** A0 keeps a live `A_PLUS_PROGRESS.md` scoreboard (per-metric status + evidence links). Agents post `file:line` evidence per item. No item is "done" on the scoreboard without its proving test + green-gate command output. A0 runs the **full** gate suite before declaring any metric A+.

## PART 2 — GROUND-TRUTH BASELINE (verify, then exceed)

Current honest state from the prior audit (your floor — push every one of these to A+):

**Already strong (protect, don't regress):** Tenant RLS isolation (real `FORCE` RLS + parameterized GUC + Postgres CI). Test/CI rigor (~10k tests, 237 gates, meta-gate). Offline two-rail (SODP+WAL). i18n breadth (20 locales). Security baseline (MFA, Argon2, CSP/HSTS, RBAC+ReBAC).

**Reconciled baseline (Wave 16 — 2026-07-18): closed vs still-open.**
Do not re-litigate CLOSED rows as absent. Score residual work only.

**CLOSED (wired + proven — protect):**
- **Grading formula path:** `grading_formula_engine` is called from live `apps/evals/grade_computation.py` (not tests-only). Scale registry coverage gate green; band/Playwright breadth still EXTERNAL/minor.
- **Report cards:** render → approve → PDF (WeasyPrint) → parent portal download + E2E seeds exist (`apps/reports/`). Playwright teacher/parent soak remains CI/EXTERNAL.
- **Booking:** `ExclusionConstraint` / gist present on resource booking models; Postgres double-book proof stays EXTERNAL.
- **Discipline:** points ledger + restorative actions + counselor/MTSS paths real.
- **Substitute marketplace:** auto-match + notify + WS client + absence auto-open wired (#12 A+).
- **Athletics + inventory:** clubs/clearance + movement ledger (checkout/transfer/consume/loss) + append-only guard + family issued-items (`StudentResourceReturn` ↔ parent portal).
- **EAV/metadata:** country catalog auto-seed at provision Phase B (IN/AE/CM proven) + fail-honesty; `School.save` country-change reseed; `StudentCreateForm`/`TeacherCreateForm` attach `dyn_*` fields (`test_dynamic_forms_runtime`).
- **CERTIFICATE_STRINGS:** **20/20** locales (`test_localization`); msgstr depth for newly synced msgids remains.
- **Login lockout / bandit / RBAC matrix:** rate-limit+lockout, SAST in CI, `candidate_anonymous=0` — ReBAC **enforce** still operator opt-in.
- **Celery worker+beat:** scheduled in prod path; health beats default-ON (opt-out).
- **Micro-finance partial:** fractional ledger + Razorpay/Mercado **live HTTP + fail-closed**; merchant sandbox secrets EXTERNAL.
- **Sovereignty partial:** border-lock enforce **decoupled** from `ENABLE_MULTI_REGION`; physical region DB aliases EXTERNAL.
- **DR partial:** daily signed snapshot dual-write + durability class honesty; real second volume/S3 EXTERNAL.

**STILL OPEN (THE WORK):**
- **EAV residual:** indexed search/report breadth for every country field remains PARTIAL polish (core form+provision+reseed CLOSED above).
- **Billing/PPP:** CountryMultiplier / PPP opt-in paths exist; live multi-PSP sandbox charges + tuition PPP soak EXTERNAL/partial.
- **Offline homework:** applier real on SODP/WAL; homework UI surface still latent per offline capability gate.
- **Security residual:** `RMC_REBAC_ENFORCE_SENSITIVE=1` still operator-gated after flip-readiness gate.
- **Infra residual:** Postgres CI + moat Playwright on GitHub Actions budget; restore-drill `--apply` ops proof.
- **CRDT/offline (25):** lesson-plan browser Client callers wired; multi-day full-app CRDT convergence on Postgres + green moat CI still EXTERNAL/partial.
- **Docs honesty:** Part 2 must stay reconciled with `A_PLUS_PROGRESS.md` (this section).

## PART 3 — THE A+ RUBRIC (every metric must reach ≥98 / A+)

Each metric is scored /100. **A+ = ≥98.** A metric is ≥98 only when **all** of: (a) every listed gate is GREEN at its baseline, (b) the capability is wired end-to-end with `file:line` evidence, (c) new behavior is covered by tests that pass **on Postgres where correctness-critical**, (d) no regression in the full suite, (e) docs describe only what's wired.

| # | Metric | A+ bar (objective, must all hold) |
|---|---|---|
| 1 | **Tenant Isolation** | All RLS gates green (`scan_rls_force_coverage`, `scan_rls_policy_coverage`, `scan_rls_bypass`, `scan_tenant_queryset_safety`=0, `verify_unscoped_tenant_writes`, `verify_websocket_tenant_scope`, `audit_celery_tenant_task_scoping`); `tenants-rls.yml` green on Postgres; every tenant model has enable+default-deny migration; pooler-safe (`SET LOCAL` in txn or documented constraint). |
| 2 | **Tenant Experience (BEST-IN-CLASS)** | Sticky chrome, collapsible nav + copilot, balanced content, zero layout-contract violations (`audit_shell_scroll_contract`, `scan_undefined_css_classes`=0); onboarding wizard genesis→launch fully wired; 5 role dashboards live-data, no dead space; Lighthouse ≥98 perf/best-practices/SEO on tenant shell; WCAG 2.2 AA (axe/pa11y 0 serious). |
| 3 | **Grading Engine** | Polymorphic formula engine **wired into the live grade path** (not tests); ≥15 country scales first-class incl. UK GCSE 9–1, IB 1–7, German 1–6, CBSE, WAEC, French 0–20, US GPA, T-score; durable seed (migration+command); displayed on report card/gradebook/transcript/rankings; gate `verify_grading_scale_registry_coverage` extended to assert band-table+display per scale, green. |
| 4 | **Report Cards** | End-to-end render → approve → **PDF (WeasyPrint)** → distribute (parent portal + export); per-term & annual; scale-aware bands; immutable archive; tenant-scoped; Playwright E2E proving a teacher/admin can produce & a parent can view a report card. |
| 5 | **EAV / Metadata Delivery** | `DynamicFieldDefinition` rendered into **real student/teacher/parent forms** with validation; values persisted via `set_dynamic_field_value`; surfaced in **reports + search** (indexed); country catalog **auto-seeded at provisioning**; no-op bridge removed; E2E proving a school adds "Aadhaar/Civil ID" at runtime and it appears in form+detail+search with **zero migration**. |
| 6 | **Billing / PPP / Currency** | `CountryMultiplier` **seeded for all supported countries** (migration+command, real PPP data + source noted); PPP applied to **subscriptions AND tuition** (opt-in per tenant); Decimal everywhere (`scan_money_float`=0); locale display (`scan_locale_display`=0); ≥2 local PSPs **live (real HTTP, sandbox-verified)** behind config + the Stripe path; entitlement freeze/unfreeze tested. |
| 7 | **Payments Reliability** | Webhook signature verification, idempotency keys, retry/outbox, reconciliation; no money lost on retry; tests cover duplicate-webhook and partial-failure. |
| 8 | **Offline / PWA** | `verify_offline_capability_implementation`=0 with **homework applier real + UI wired** (no latent); background-sync on reconnect functional (not just "sync now"); manifest+SW gates green; SW version monotonic; E2E offline→online replay for attendance, grades, messaging, **homework**. |
| 9 | **Security & AuthZ** | Login/reset **rate-limited + lockout FSM**; ReBAC enforced on sensitive ops (`RMC_REBAC_ENFORCE_SENSITIVE=1` for defined classes) with tests; `bandit`/SAST in CI at 0 highs; `audit_role_permission_matrix` candidate_anonymous=0; secrets only via env (no plaintext keys in tracked files); CSP enforce + nonce; security headers complete. |
| 10 | **Core Ops — Booking** | Room/asset/hostel booking model with **Postgres `ExclusionConstraint` (btree_gist) preventing double-booking**, tested on Postgres; fractional capacity honored; UI to book + conflict error surfaced; tenant-scoped. |
| 11 | **Core Ops — Discipline** | Behavior **points ledger** + incident **routing FSM** (escalate to counselor/parent per rules) + **restorative action** tracking; safeguarding-aware; UI + tests. |
| 12 | **Core Ops — People** | Substitute **auto-matching** (availability + qualification + radius) on absence with notify; payroll already real — verify approval FSM + payslip PDF; staff lifecycle complete. |
| 13 | **Athletics / Extracurricular** | Team/roster/sport models, health-clearance workflow with signoff, clubs, event ticketing (already real) — wired with UI + tests. |
| 14 | **Inventory / Assets** | Movement ledger (checkout/return/consume/transfer/loss) with audit trail + reorder alerts, not bare quantity; UI + tests. |
| 15 | **Scheduling / Timetable** | Solver conflict-free under load; respects room booking constraint (#10); publish + clash detection + UI; tested with realistic fixtures. |
| 16 | **Testing & CI** | Main suite runs **green on Postgres** (nightly or PR job), not only SQLite; `django-tests.yml` blocking (no `|| true` masking); coverage gate enforced per-app (finance≥85, security≥90, api≥75) not just global 60; `verify_ci_gate_wiring` REQUIRED_GATES intact + expanded. |
| 17 | **Performance** | No N+1 on hot paths (assert via query-count tests); p95 server time budget documented + met; Lighthouse ≥98; key list endpoints paginated (RFC-8288). |
| 18 | **Observability** | Structured logs (no PII), Sentry wired, Prometheus metrics, `/healthz` covers DB+cache+Celery+queue depth; error-budget/SLO doc; tracing on critical flows. |
| 19 | **Data Privacy / Compliance** | FERPA/GDPR/COPPA mapping doc; DSAR export+erase end-to-end (already partial — complete it); data-residency switch honored; consent + retention policies enforced in code with tests. |
| 20 | **API Quality** | DRF schema coverage gate=0; versioned, paginated, rate-limited, documented (OpenAPI), auth-gated; contract tests; deprecation policy. |
| 21 | **Internationalization** | All 20 locales compile + no missing critical msgids on key flows; **`apps/reports/localization.py::CERTIFICATE_STRINGS` covers all 20 `settings.LANGUAGES` codes (today 20/20 — gate green; residual is native msgstr depth for newly synced non-en msgids)**; RTL verified (Arabic/Hebrew/Farsi) via Playwright; locale number/date/currency formatting correct; pseudo-locale QA. |
| 22 | **Infra / Reliability / DR** | Real Celery **worker+beat** in prod (retries+durability); backups + restore runbook tested; migration safety gate; graceful degradation when Redis/Celery down; documented capacity headroom. |
| 23 | **Reference Integrity (no silent 500s)** | All integrity gates 0: import / get_model / url-name / template-ref / static-ref / settings-key / field-ref / relation-path. |
| 24 | **Documentation & Runbooks** | Architecture, per-app READMEs current, runbooks for deploy/rollback/incident/offboarding; **no doc overstates delivered surface** (audited). |
| 25 | **Zero-Connectivity CRDT Local-First (the Offline Moat)** | Daily flows (attendance, grades, **homework**, fees, behavior) work **fully offline for ≥7 continuous days** — read AND write — from IndexedDB; on reconnect, **CRDT merge with multi-tenant vector clocks** converges deterministically with **zero data loss** under concurrent edits; `verify_crdt_convergence` + `verify_sync_semantics` green; **Postgres** convergence test + an E2E multi-day offline→online simulation. CRDT rail must be the LIVE path (not legacy/superseded), or WAL must provide equivalent multi-day guarantees. |
| 26 | **Micro-Financing & Local Cash Rails** | **≥3 local rails LIVE (real sandbox HTTP, verified)** incl. at least one mobile-money (M-Pesa/MoMo) + one of Pix/UPI, behind config alongside Stripe; **fractional/installment sub-ledger** supports irregular partial payments (incl. cash-over-counter capture) with Decimal precision, partial-payment → enrollment-permission gating, localized tax on partials, and reconciliation; idempotent; tested. Money gates (`scan_money_float`, `scan_locale_display`) = 0. |
| 27 | **Data Sovereignty / Border-Lock Routing** | `country_iso_code` drives a **residency policy enforced at the data layer** — student PII writes/reads are pinned to the tenant's region (real DB router / region binding, or a documented + tested region-deployment topology, not faked); **cross-border PII transfer blocked + audited** (`compliance/cross_border_export.py`); platform sees only anonymized cross-region aggregates; `residency-readiness.yml` green; tests prove a non-region read is denied. |
| 28 | **Immutable DR Snapshots + Self-Host Runtime** | **Daily automated, cryptographically-signed, tenant-key-encrypted** full-state snapshot shipped to **≥2 independent stores**; **restore tested** (snapshot → working school) in CI; tenant can **download a master file** and stand the school back up via a **documented self-host/offline runtime**; tamper-evident (signature verify on restore); runbook complete. |
| 29 | **Academic-Year Lifecycle / EOY Rollover** (added 2026-08-12) | Production-safe **close → open** end-to-end — the "run Z → roll back to A" capability incumbents (PowerSchool/Infinite Campus/Skyward) treat as first-class: (a) structure **clone** into the next year (terms, classrooms w/ unique codes, subject assignments, promotion rules), idempotent; (b) **bulk promote/retain/graduate** with per-student override via an **enrollment open/close lifecycle** (no destructive field overwrite), PromotionRule-driven status; (c) **pre-rollover validation + backup/export gate** enforced before apply (blocker scorecard runs unconditionally; a full-state snapshot/export is a **hard precondition** — PowerSchool "backup before the process button" parity); (d) **immutable historical archive produced BY rollover** (append-only frozen transcripts/grades; year-lock enforced **centrally at the model layer**, not only in grade-entry views); (e) **enrollment date-integrity** validation (entry < exit, no overlapping closed ranges); (f) parent/guardian **notification fires on EVERY apply path** (synchronous AND queued/async — no dropped checkbox); (g) **hemisphere/calendar-independent** (per-tenant academic-year driven, no hardcoded summer); (h) **persisted next-year placement** (advance NYP indicator) + a **staged/sandbox** plan that never mutates the active year until apply; **run-observed** Postgres/browser E2E closes year N and opens N+1 with **zero data loss** (source-read alone is < 98); `docs/WORKFLOW_YEAR_ROLLOVER.md` describes only what is wired. |
| 30 | **Universal Education Model** — Daycare→Tertiary × General/Technical/Vocational × ISCED (added 2026-08-13, research cross-walk) | The "one platform for every education system on Earth" moat: (a) **ISCED-aligned level/grade-progression matrix** (primary / lower-sec / upper-sec / tertiary) that abstracts grade paths so a German Gymnasium, a UK Sixth Form, a Kenyan secondary and a US high school all run **one** progression model driving M29 promotion; (b) **level tiers configured not hardcoded** — Daycare/Early-Childhood (developmental-milestone metrics, guardian check-in/out, teacher:child ratios), K-12 (standards-mapped marks, compulsory-attendance / truancy triggers), Tertiary (credit-hours / CGPA / ECTS, prerequisite gates, thesis); (c) **track differentiation** — General (GPA / exam boards), Technical (lab-safety **prerequisite gate** blocking registration, equipment scheduling), Vocational (apprenticeship / dual-enrollment **work-hours**, **competency / mastery pass** with verified signoff); (d) built on an **atomic entity / metric / interval / gate** primitive, not per-tier hardcoded modules. Proven: a daycare, a K-12 and a tertiary tenant each run their native model with **zero code fork**. (Extends M3 grading + M5 EAV; largely a NEW build.) |
| 31 | **Marketplace App-Injection & Extensibility** — Shopify layer (added 2026-08-13, research cross-walk) | Third-party apps **inject UI + logic + storage** into a tenant safely: (a) **contextual anchor slots / hooks** (e.g. `student.profile.tab`, nav) declared in an **App Manifest** and rendered natively via micro-frontend / sandboxed frame + shared design tokens; (b) **scoped OAuth2** install-consent → short-lived **tenant_id + scope-claimed JWT**; every API call gateway-filtered to that tenant's rows + granted scopes (no master key); (c) app custom data via a **metadata / JSONB `app_extensions`** API (no raw columns on core tables), tenant-isolated; (d) locale / RTL context injected into the app. Proven: a sample installed app injects a slot, reads scoped data, writes a custom field, and **cannot** read another tenant. (Extends S7 ecosystem to first-class.) |
| 32 | **Government / Ministry Reporting Translation Engine** (added 2026-08-13, research cross-walk) | Atomic tenant data → the **exact schema (XML / JSON / CSV) each ministry mandates**, via pluggable per-country report templates (state funding, enrollment, attendance, graduation submissions) — **no per-country software fork**; validated against ≥1 real ministry format end-to-end; tenant / residency-scoped. (Extends M19 / M27.) |
| 33 | **B2B Procurement & Supply Marketplace** — Amazon layer (added 2026-08-13, research cross-walk) | Embedded supply marketplace in the admin portal: **auto-generated purchase orders from class / lab configuration** (e.g. safety goggles per chemistry section), certified-vendor catalog, tenant-scoped ordering + localized tax; GMV tracked. (NEW; Amazon FinTech-B2B layer.) |

> **The platform GO requires EVERY metric ≥98 AND zero items in the "NO-FAKE-GREEN" forbidden list.** Track all 28 + **M29–M33** on the scoreboard.
>
> **Metrics 25–28 are the "frontier moat" — the systemic, real-world-friction dimensions that decide global dominance. Do not let them be scored on scaffolding/readiness alone: a readiness gate that is green but unenforced at runtime is < 98. Enforced + tested + (where ops-gated) documented-and-restore-proven only.**

## PART 4 — WORKSTREAM DETAIL (scope + Definition of Done + verify command)

For **each** item: (1) re-verify current state with `file:line`; (2) implement end-to-end per Part 0; (3) add tests (Postgres where correctness-critical); (4) run the listed gate(s) to green; (5) post evidence to the scoreboard.

> Verify-command convention (Cursor terminal, from `beta/school-management-system/`):
> - Run a gate: `python scripts/<gate>.py` (expect exit 0 / baseline 0).
> - Run app tests: `python manage.py test apps.<app> -v2`.
> - Run Postgres-tagged tests: use the `tenants-rls` / `requires_postgres` path (see `.github/workflows/tenants-rls.yml`).
> - Full gate sweep before A+ claim: `bash scripts/pre_deploy_gate.sh` (chains the scanners).

**W1 — Tenant Experience (A1).** Audit shell + onboarding + dashboards. DoD: sticky-chrome contract green; wizard genesis→launch wired with real data; 5 role dashboards no dead space; Lighthouse ≥98 + axe/pa11y 0 serious on tenant shell. Verify: `python scripts/audit_shell_scroll_contract.py`, `python scripts/scan_undefined_css_classes.py`, Playwright role-home + a11y specs.

**W2 — Grading polymorphic wiring (A2).** Wire `evaluate_grading_formula` into the live grade-save path; make ≥15 scales first-class with band tables; extend `verify_grading_scale_registry_coverage.py` to assert band+display per scale. DoD: changing a tenant's scale changes computed letters/bands across report card+gradebook+transcript+rankings, proven by tests. Verify: `python scripts/verify_grading_scale_registry_coverage.py --strict`; `python manage.py test apps.evals apps.reports`.

**W3 — Report cards (A2).** Build render → approve → WeasyPrint PDF → distribute (parent portal + export), per-term + annual, scale-aware, tenant-scoped, immutable archive. DoD: Playwright E2E: teacher/admin generates, parent views/downloads. Verify: new E2E spec + `apps.reports` tests + render-safety gate.

**W4 — EAV delivery (A3).** Render `DynamicFieldDefinition` into student/teacher/parent forms with validation; persist via `set_dynamic_field_value`; surface in reports + indexed search; auto-seed country catalog at provisioning; delete no-op bridge. DoD: E2E adds "Aadhaar"/"Civil ID" at runtime → appears in form+detail+search, zero migration. Verify: `apps.metadata` + `apps.people` tests + new E2E.

**W5 — PPP + tuition + PSPs (A4).** Seed `CountryMultiplier` for all supported countries (migration + command, real data + source); apply PPP to tuition (opt-in per tenant) and subscriptions; make ≥2 local PSPs perform **real sandbox HTTP** behind config; keep Decimal + locale gates at 0. DoD: tests prove PPP scales tuition for IN/NG/etc., and a sandbox PSP charge round-trips. Verify: `python scripts/scan_money_float.py`, `python scripts/scan_locale_display.py`, `apps.billing` + `apps.finance` tests.

**W6 — Booking + exclusion constraint (A5).** New booking model with Postgres `ExclusionConstraint` (`btree_gist`, `tstzrange`) preventing overlap per resource+tenant; fractional capacity; UI + conflict error. DoD: **Postgres** test asserts a second overlapping booking raises IntegrityError. Verify: `requires_postgres`-tagged test in `playwright-tenant-postgres.yml` path.

**W7 — Discipline engine (A5).** Behavior points ledger + incident routing FSM + restorative actions; safeguarding hooks. DoD: incident escalates per rule, points accrue, restorative task tracked; UI + tests.

**W8 — Substitute auto-match (A5/A12).** On teacher absence, match available+qualified+nearby substitutes and notify. DoD: service returns ranked matches; absence triggers notification; tests.

**W9 — Athletics + Inventory (A5).** Team/roster/sport + health-clearance signoff; inventory movement ledger + reorder alerts. DoD: UI + tests for each.

**W10 — Security hardening (A6).** Login/reset rate-limit + lockout FSM (use `django-ratelimit`); enforce ReBAC on sensitive classes; add `bandit`/SAST to CI (0 highs); confirm no plaintext secrets in tracked files; verify CSP/headers. DoD: brute-force test gets throttled+locked; ReBAC denial test; bandit job green. Verify: `python scripts/audit_role_permission_matrix.py`, new `bandit` CI job, security tests.

**W11 — Compliance/DSAR/residency (A6).** Complete DSAR export+erase; residency switch; consent + retention enforcement. DoD: E2E export+erase; residency-routed write test. Verify: `apps.compliance` + `apps.lifecycle` tests, `residency-readiness.yml`.

**W12 — Infra/Celery/Postgres-tests/Perf/Obs/DR (A7).** Stand up real Celery worker+beat in `render.yaml`; add a Postgres run of the main suite; N+1 query-count tests on hot paths; `/healthz` covers DB+cache+Celery+queue; backup/restore runbook. DoD: worker processes a real task with retry; Postgres suite green; query-count tests pass; healthz reflects dependencies. Verify: new workflow job + `apps.observability` tests.

**W13 — Offline homework + background-sync (A8).** Implement homework applier (real write) + UI surface; background-sync on reconnect. DoD: `verify_offline_capability_implementation.py`=0 with **no latent**; E2E offline homework → online replay. Verify: `python scripts/verify_offline_capability_implementation.py`.

**W14 — API + i18n + reference integrity + docs (A1/A3/A0).** DRF schema coverage=0; pagination+rate-limit+versioning; 20-locale compile + RTL Playwright; all reference-integrity gates 0; docs corrected to not overstate. Verify: `python scripts/scan_drf_schema_coverage.py`, the 8 reference-integrity gates, `python manage.py compilemessages`.

**W15 — EXPANSIVE SWEEP (all agents).** Beyond the list: hunt and fix anything blocking A+ — accessibility on every surface, empty-states, error pages, email/SMS deliverability, AI copilot/at-risk-ML quality+safety+guardrails, notification preferences, audit-log completeness, rate-limit coverage on all mutating endpoints, file-upload validation/AV, timezone correctness, soft-delete/restore, bulk-import validation, idempotent webhooks everywhere. **If a reasonable best-in-class platform would have it and we don't, build it.**

### FRONTIER MOAT WORKSTREAMS (W16–W19) — the systemic real-world dimensions

**W16 — Zero-Connectivity CRDT Local-First (A8, metric 25).** Make the daily flows survive **5–7 days fully offline** (read + write) from IndexedDB, then converge via CRDT + multi-tenant vector clocks with zero loss. Re-verify `apps/sync_engine/crdt*.py` vs the live WAL rail; pick ONE as the authoritative multi-day path and wire it end-to-end (don't leave CRDT as legacy-dead). Homework must no longer be latent. DoD: `verify_crdt_convergence` + `verify_sync_semantics` green; a **Postgres** convergence test for concurrent multi-device edits; an E2E that goes offline for a simulated week of attendance/grades/homework/fees and replays with deterministic merge + zero loss. Verify: `python manage.py verify_crdt_convergence`, `python manage.py verify_sync_semantics`, `python scripts/verify_offline_capability_implementation.py`.

**W17 — Micro-Financing & Local Cash Rails (A4, metric 26).** Make **≥3 local rails live** (real sandbox HTTP) — at least one mobile-money (M-Pesa/MoMo) and one of Pix/UPI — behind config alongside Stripe (extend `apps/finance/gateways/` + `psp_adapter_registry`/`regional_payment_profiles.json`). Build the **fractional/installment sub-ledger** on top of the existing `payment_plans.py`/`wallet_payment`/`split_billing`: irregular partial payments (incl. bursar cash-over-counter capture), Decimal precision, partial-payment → enrollment-permission gating, localized tax on partials, idempotent posting, reconciliation. DoD: sandbox charge round-trips on ≥3 rails; tests prove a sequence of small partial payments settles a fee and updates enrollment permissions. Verify: `python scripts/scan_money_float.py`, `python scripts/scan_locale_display.py`, `apps.finance` + `apps.billing` tests.

**W18 — Data Sovereignty / Border-Lock Routing (A6/A7, metric 27).** Turn residency from policy-scaffolding into **data-layer enforcement**: `country_iso_code` pins student-PII storage to the tenant's region — via a real Django `DATABASE_ROUTERS` region router, region-bound connection, or a documented + tested multi-region deployment topology (no faking). Block + audit cross-border PII transfer (`compliance/cross_border_export.py`); expose only anonymized cross-region aggregates to the platform. DoD: a test proves a read/write for a region-A tenant cannot touch region-B PII storage; `residency-readiness.yml` green with enforcement (not just readiness flags). Verify: `.github/workflows/residency-readiness.yml`, `apps.compliance` tests, new router test.

**W19 — Immutable DR Snapshots + Self-Host Runtime (A7, metric 28).** Build a **daily automated** job that compiles each tenant's full state into a compressed, **cryptographically signed, tenant-key-encrypted** snapshot shipped to **≥2 independent stores**; verify signature on restore (tamper-evident). Provide a tenant-downloadable **master file** and a **documented self-host/offline runtime** that stands the school back up. DoD: CI test does snapshot → restore → working school; signature-tamper test fails closed; restore + self-host runbook written. Verify: new Celery beat task + restore test (Postgres) + runbook in `docs/`.

**W20 — Academic-Year Lifecycle / EOY Rollover (A5/A7, metric 29).** Harden the year **close → open** flow to production-safe. Current state (run-observed 2026-08-12 — a throwaway `TestCase` exercised the real machinery: 8/8 audit assertions + `python manage.py check` 0 issues): the core is REAL — clone (`apps/academics/services_year_setup.py:25-139`), rollover apply + tenant-scoped **year lock** (`apps/accounts/views_rollover.py:100-333`), PromotionRule status (`apps/reports/services.py:244-294`), alumni (`views_rollover.py:198-210`), `ClassroomPromotionMapping` (`apps/academics/models.py:248-280`), read-only blocker scorecard (`apps/academics/year_close.py:18-130`), hemisphere-independent by design, bulk + per-student override. Gaps (each a DoD item): no pre-rollover **backup/export gate**; the "immutable" transcript is **overwrite-able** (`apps/student360/services.py:296`, `update_or_create`) and **not produced by rollover**; no `Enrollment.clean()` **date-integrity** (`apps/people/models.py:1017-1072`); **year-lock proven NOT DB-enforced** (run-observed: an enrollment written into a locked year + a student mutated within it both succeeded; only `apps/evals/views.py:221,289` honor it); **notify-parents silently dropped on the async apply path** (`apps/accounts/tasks.py:263-391` vs the working sync block `apps/accounts/views_rollover.py:238-277`) though the queue UI posts the checkbox (`templates/accounts/rollover_proposal_detail.html:97`); doc divergence (`docs/WORKFLOW_YEAR_ROLLOVER.md:50,57,73`). DoD: backup/export precondition enforced before apply; `batch_freeze_transcripts` (`apps/academics/year_close.py:184-197`) called by every apply path + transcripts append-only; `Enrollment.clean()` added; a central `assert_year_writable` guard on locked-year writes; notify parity across sync + async; `docs/WORKFLOW_YEAR_ROLLOVER.md` corrected to the enrollment-lifecycle reality; a **run-observed Postgres E2E** closes year N and opens N+1 with zero loss. Verify: `python manage.py test apps.academics apps.accounts apps.reports`, the rollover E2E, `python manage.py check`. **STATUS 2026-08-13 — all six code-addressable gaps SHIPPED** (reviewed diffs + must-fire tests, fail-before observed): year-lock write guard / async notify-parity / `Enrollment.clean` date-integrity / doc fix (`02c4dec38`); pre-rollover **backup/export gate** wired to the M28 `TenantImmutableSnapshot` + operator override + "Back up now" UI (`9d81dc9c1`); **freeze-on-apply** immutable archive (frozen before the move → graduating cohort captured) + genuine **write-once** `ImmutableTranscript` (`6e17e58e6`). M29 re-scored **66 → ≈ 85 (still NO-GO)**. Remaining W20 DoD (now the residual < 98): next-year calendar / bell-schedule, persisted NYP placement fields, parallel-planning sandbox depth, and a run-proven **Postgres / browser** close→open E2E.

## PART 4C — RESEARCH-DERIVED BACKLOG (2026-08-13 cross-walk of the EOY / global-platform research)

> The 2026-08-13 cross-walk mapped the pasted EOY + "A-Z global platform" research (PowerSchool/Infinite-Campus EOY norms; the Amazon/AWS/Shopify/Salesforce four-pillar model; Daycare→Tertiary + General/Technical/Vocational scaling; the atomic education engine; the "revolving year loop") against the whole rubric. **Already tracked** (no new tasker — mapped only): multi-tenancy → M1; data residency / sovereignty → M27; local FinTech rails (M-Pesa/Pix/SEPA) + tax/subsidy → M26; offline / local-first → M8/M25; grading-scale adaptability → M3; runtime custom fields (EAV) → M5; EOY rollover / revolving-year loop / hemisphere-independence → **M29/W20**; RTL i18n → M21; API/microservices → M20; immutable DR snapshots → M28; marketplace/SDK ecosystem → S7; proactive at-risk ML interventions → W15. The genuinely-uncovered capabilities are lifted to **new metrics M30–M33** (Part 3) plus the operational-cycle **taskers W21–W31** below. These are **NET-NEW capability gaps** (mostly real builds, not one-pass fixes); until delivered they score **NO-GO / not-yet-built** on the scoreboard.

**W21 — Master-scheduling depth (extends M15).** Course-request / elective collection → section-count + staffing calc → algorithmic timetable for irregular technical/vocational patterns (multi-week rotating blocks, lab-equipment limits) → ML year-over-year refinement (room-vacancy / travel-time / teacher-preference from prior cycles). Verify: `apps.academics` scheduling tests.
**W22 — Graduation audit (extends M29 / M3).** Rising-senior multi-point transcript / track-alignment check that flags off-track students before rollover. **STATUS 2026-08-13 — SHIPPED `a47fc6e60`** (13/13 must-fire tests green): `apps/academics/graduation_audit.py` connects the previously-orphaned `run_degree_audit` engine (higher-ed) + a no-hardcoding K-12 settings check (`School.settings["graduation_requirements"]`); hard gate + operator override on BOTH rollover apply paths; behaviour-preserving when no requirements configured. Residual (future increments): in-product requirements editor, cumulative multi-year GPA, sync-path override checkbox UI.
**W23 — Compute-as-a-service headless APIs (extends M20 / S7).** Expose grading / timetable / report-builder engines as subscribable, tenant-scoped microservice APIs for regional networks (AWS layer).
**W24 — Immunization & health records (NEW).** Medical-record tracking + automated missing-vaccine / health-filter alerts for rising grades (year-end + intake).
**W25 — HR year-end lifecycle (extends M12).** Intent-to-return surveys, hiring pipeline (vacancy → interview → contract), PD / new-staff onboarding schedule.
**W26 — Inventory / asset year-end cycle (extends M14).** Device collect / clean / inventory at year-end + classroom-allocation / room-move plan for teachers changing grades.
**W27 — Transport & food-service year-end (extends `apps.schoolops`).** Bus-route recompute from new addresses / boundary shifts; lunch-debt clearing + POS / vendor-contract renewal.
**W28 — Governance & compliance year-end (NEW).** Board-approval records (calendar / budget / handbook), state-funding audit-submission artifact, policy / grading-scale propagation to all portals.
**W29 — i18n depth: Hijri calendar + regional numerals + phone formats (extends M21).** Beyond RTL: Hijri calendar option, Eastern-Arabic numerals, regional phone-format validation.
**W30 — No-code Blueprint Constructor completeness (extends onboarding / blueprint).** Signup wizard **Level × Track × Metric × Regulation** → auto-provision fields + privacy posture (GDPR/FERPA) + UI, end-to-end (research §"Master Configuration Interface"). First verify current blueprint coverage before building.
**W31 — Parallel planning sandbox depth (extends M29 item 7 / W20).** A true 6-months-ahead next-year environment + staged registration open during the active year without disruption (real isolation / branch, not just future-year rows).

## PART 5 — TENANT BEST-IN-CLASS MANDATE (explicit, weighted heavily)

The **tenant (the school) experience is the product.** Hold it to Shopify/Salesforce/Linear-grade polish:
- **Instant genesis:** a school self-serves from signup → branded workspace → guided activation checklist → operating, with real data at every step (no placeholders, no dead space).
- **Locally native from day one:** correct currency, grading scale, identity fields, language, and date/number formats auto-resolved from the school's country — **no migration, no consultant**.
- **Sovereign & programmable:** runtime custom fields (EAV) that flow into forms+reports+search; academic-year clone/branch; clean one-click offboarding with encrypted export.
- **Works on cheap devices / bad networks:** offline-first for the daily flows (attendance, grades, homework, messaging) with reliable resync.
- **Premium chrome:** sticky header+sidebar, collapsible nav + copilot, balanced content, WCAG 2.2 AA, Lighthouse ≥98, zero layout-contract violations.
- **Trustworthy:** strict tenant isolation, no cross-tenant leakage, fast, observable, recoverable.

Every workstream must ask: *"Does this make the tenant's experience best-in-class?"* If not, raise the bar until it does.

## PART 6 — EXECUTION LOOP (run until self-green)

```
WHILE any metric < 98 OR any forbidden-pattern present:
  1. A0 refreshes the scoreboard (28 metrics) from real gate runs — never from memory.
  2. Assign open gaps to agents (parallel where files don't collide).
  3. Each agent: audit-first → implement end-to-end → test (Postgres where needed) → gate-green → post file:line evidence.
  4. A0 runs the FULL gate sweep (scripts/pre_deploy_gate.sh + the metric-specific gates + Postgres jobs).
  5. Any red gate, latent flag, overstated doc, or missing E2E → reopen the metric (< 98), back to step 2.
  6. Commit path-scoped, fast-forward over peers, verify tree intact.
END
Then: run PROMPT B.
```

**Do not declare victory from intentions.** Declare it only when the gate sweep is green and the scoreboard shows 28/28 ≥ 98 with evidence.

---

# PROMPT B — THE FINAL AUDIT (run after Prompt A self-reports green)

You are an **independent, adversarial audit fleet**. Assume the implementers are over-optimistic and that docstrings/memory overstate reality (this has happened before). **Trust nothing; verify everything from the actual code and live gate runs.** Deploy multiple parallel auditors (highest-capability model only). Your output is an **A+ scorecard** and a **GO / NO-GO** decision.

## Audit rules
1. **Re-derive every metric from scratch** by reading code and running gates — do not read the implementers' scoreboard as truth (you may use it only as a list of claims to falsify).
2. **For each of the 28 metrics**, attempt to **disprove** the A+ claim. A metric is A+ (≥98) ONLY if you can independently produce: the `file:line` of the end-to-end wiring, the proving test, and the green-gate command output (run it yourself). If any leg is missing → the metric is **< 98**. **Pay special attention to metrics 25–28 (frontier moat): a green readiness gate is NOT proof of runtime enforcement — demand the enforcement test and (for ops-gated items) the restore/self-host proof.**
3. **Hunt the known failure modes:** latent flags (producer without applier), services/formulas called only by tests, tables that ship empty, no-op bridges, `|| true` / `continue-on-error` masking, baseline/allowlist edits hiding findings, deleted/weakened tests, docstrings that overstate, SQLite-only "passing" of Postgres-only logic, cross-tenant leakage, money-as-float, PII in logs, secrets in tracked files.
4. **Expansive:** also score anything a best-in-class platform needs that isn't in the 28 (note it as an extra metric and score it).
5. **Run, don't assume:** execute `bash scripts/pre_deploy_gate.sh`, every metric-specific gate, the Postgres workflows (`tenants-rls.yml`, `playwright-tenant-postgres.yml`), the test suite, Lighthouse, axe/pa11y, `bandit`. Paste real output.
6. **Score under the 9.8 regime (adopted 2026-07; supersedes plain /100 averaging):** a domain's score is its **LOWEST applicable dimension** (arch / completeness / isolation / security / offline / config-consistency / RBAC / reliability / recovery / a11y / UI / AI-grounding / test-depth / runtime-proof / maintainability / portability / auditability), NEVER the average — an average must never hide a weak dimension. Hard ceilings: isolation/security hole → ≤4.9; materially incomplete / duplicate engine → ≤6.9; high repo-side gap → ≤7.9; missing runtime proof (PG / browser / offline / restore / a11y) → ≤8.9; failure-injection or second-audit incomplete → ≤9.4; contradiction register non-empty → ≤9.7. **9.8/10 ≡ 98/100 — the bar is unchanged; the arithmetic is stricter.** Classify every claimed gap as CONFIRMED (repro command) / PHANTOM (evidence it exists) / EXTERNAL_PROOF_REQUIRED (Postgres CI / real browser / prod env / pilots / counsel).
7. **Strategic-drift check (PROMPT S):** score the S1–S8 strategic rows alongside the 28; verify every wave shipped since the last audit traces to a named strategic choice (S3) or a confirmed RED from the previous packet — flag any orphan activity as drift (failure modes 1–2). Verify the not-do list (S3) was not violated. Market legs are classified EXTERNAL_PROOF_REQUIRED honestly — never counted as done, never dropped from the register — but each row's repo-side enabler must still hit ≥9.8.

## Required output — THE SCORECARD

```
RUNMYCAMPUS A+ AUDIT — <date>
Auditor fleet: <models/agents>  | Commit audited: <sha>  | Tree size: <git ls-tree -r HEAD | wc -l>

| # | Metric | Score /100 | A+? | Evidence (file:line + test + gate output) | Gaps if <98 |
|---|--------|-----------|-----|-------------------------------------------|-------------|
| 1 | Tenant Isolation | ... | YES/NO | ... | ... |
| ...                                                                                    |
| 24| Documentation & Runbooks | ... | ... | ... | ... |
| 25| Zero-Connectivity CRDT Local-First | ... | ... | ... | ... |
| 26| Micro-Financing & Local Cash Rails | ... | ... | ... | ... |
| 27| Data Sovereignty / Border-Lock Routing | ... | ... | ... | ... |
| 28| Immutable DR Snapshots + Self-Host Runtime | ... | ... | ... | ... |
| 29| Academic-Year Lifecycle / EOY Rollover | ... | ... | ... | ... |
| 30| Universal Education Model (Daycare→Tertiary × tracks × ISCED) | ... | ... | ... | ... |
| 31| Marketplace App-Injection & Extensibility | ... | ... | ... | ... |
| 32| Government / Ministry Reporting Translation Engine | ... | ... | ... | ... |
| 33| B2B Procurement & Supply Marketplace | ... | ... | ... | ... |
| S1–S8 | Strategic rows (PROMPT S §S8: TTV, migration wedge, country ladder, local money, offline, sovereignty, ecosystem, market loop) | ... | ... | repo-leg evidence + market-leg classification | ... |
| E+| <extra metrics found> | ... | ... | ... | ... |

OVERALL: <average + min>    BLOCKERS (any forbidden pattern): <list or NONE>
DECISION: GO  (only if EVERY metric ≥ 98 AND zero blockers)
       or NO-GO (otherwise) — with the exact, ordered list of gaps to fix.
```

## Decision rule
- **GO** — and only GO — if **every** metric (the 28 + the S-rows' repo-side legs + any extras) is **≥ 98 (9.8/10 lowest-dimension)** AND there are **zero** forbidden patterns AND the full gate sweep + Postgres jobs are green with output you ran yourself. S-row market legs that are EXTERNAL_PROOF_REQUIRED are listed with their exact external closure path (pilot, Postgres CI, counsel, prod env) — they do not block a repo-scope GO, but the verdict must be REPO-SCOPE-QUALIFIED and the external register stays visible.
- **NO-GO** otherwise. Emit the ordered, specific gap list (`file:line`, what's missing, which gate is red, which test is absent), **ordered by (strategic weight per PROMPT S × score gap)** so the next A-wave attacks the lowest-scoring, most strategically loaded domain first.

## On NO-GO
Hand the gap list **back to PROMPT A**, which reopens those metrics and loops. **Repeat A → B → A → B until PROMPT B returns GO.** Do not soften the bar to force a GO — softening the bar is itself a NO-GO.

---

## APPENDIX — KEY FILES, GATES & COMMANDS (starting map; verify against repo)

**Gate runner / meta:** `scripts/pre_deploy_gate.sh`, `scripts/verify_ci_gate_wiring.py` (REQUIRED_GATES), `.github/workflows/{ci,django-tests,architectural-boundaries,coverage-gate,tenants-rls,playwright-tenant-postgres,residency-readiness}.yml`.

**Tenant/RLS:** `apps/schools/rls.py`, `apps/schools/repositories/rls_context_repository.py`, `apps/tenancy/`, gates `scan_rls_force_coverage.py`, `scan_rls_policy_coverage.py`, `scan_rls_bypass.py`, `scan_tenant_queryset_safety.py`, `verify_unscoped_tenant_writes.py`, `verify_websocket_tenant_scope.py`, `audit_celery_tenant_task_scoping.py`.

**Grading:** `apps/evals/grading_formula_engine.py`, `apps/evals/signals.py`, `apps/evals/validators.py`, `apps/evals/grading.py`, `apps/evals/models.py`, `apps/registries/`, gate `verify_grading_scale_registry_coverage.py`.

**Report cards:** `apps/reports/services.py`, `templates/reports/`, WeasyPrint (already a dependency).

**EAV:** `apps/metadata/models.py`, `apps/metadata/services.py`, `apps/metadata/country_eav_catalog.py`, `apps/people/forms_backend.py`.

**Billing/PPP:** `apps/billing/regional_pricing.py`, `apps/siteconfig/models_platform_catalog.py` (`CountryMultiplier`), `apps/billing/services.py`, `apps/finance/gateways/`, `apps/billing/stripe_checkout.py`, gates `scan_money_float.py`, `scan_locale_display.py`.

**Offline/PWA:** `apps/wal_stream/{consumers,writers,tasks}.py`, `apps/platform_runtime/offline_queue.py`, `static/js/service-worker.js`, `apps/brand_experience/pwa_manifest.py`, gates `verify_offline_capability_implementation.py`, `verify_offline_manifest_taxonomy.py`, `scan_pwa_manifest_coverage.py`, `verify_service_worker_version.py`.

**Security:** `apps/accounts/{views.py,middleware.py,permissions.py,rebac.py}`, `config/settings.py`, gate `audit_role_permission_matrix.py`, add `bandit`.

**Reference integrity (no silent 500s):** `scan_import_reference_integrity.py`, `verify_get_model_integrity.py`, `verify_url_name_integrity.py`, `verify_template_reference_integrity.py`, `verify_static_reference_integrity.py`, `verify_settings_key_integrity.py`, `verify_field_reference_integrity.py`, `verify_relation_path_integrity.py`.

**Infra:** `render.yaml` (Celery worker/beat), `config/celery.py`, `config/settings.py` (DB, `CELERY_TASK_ALWAYS_EAGER`), `apps/observability/`.

**Core ops (new work):** `apps/schoolops/`, `apps/academics/` (booking, discipline, scheduling), `apps/people/` (substitute auto-match), `apps/school_events/` (athletics/tickets).

---

### FINAL WORD TO THE FLEET
Build for the school. Make it sovereign, local-first, offline-capable, premium, and provably correct. **Every claim carries evidence; every gate is green; every metric is ≥98 (9.8 minimum, lowest dimension) — or it is not done.** Strategy (PROMPT S) chooses the mountain and the order of the climb; it never shortens the mountain. Loop A→B until B says **GO** — and remember the closing question of the strategy discipline this file now carries: *the decision you are treating as operational (the first pilot cohort) is the most strategic one on the board.*
