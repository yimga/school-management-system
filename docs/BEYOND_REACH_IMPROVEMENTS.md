# Beyond reach — improvements to take the platform further

**Linkage-first + hybrid narrative (2026-03):** Student story cards in command search, Student 360 page, marketing scrollytelling chapters (day-in-life, admission→roster→invoice, APAC), bento drill-down on backend overview, teacher cross-module hover API, toast/micro-feedback assets — see SOT §8.0.4 bullet “Linkage-first (implemented)”.

**Purpose:** One checklist of high-impact improvements that would take RunMyCampus beyond the current world-class bar. All items map to [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (§0.3, §0.4, North star N1–N29, Phase II–V). Track completion in the SOT; this doc is the **what to do** list.

---

## 1. Experience — zero learning curve and delight

| # | Improvement | Why beyond reach | SOT ref |
|---|-------------|------------------|---------|
| N1 | **Zero learning curve** | New teacher/parent/admin completes first meaningful task in &lt;5 minutes with no manual; guided flows and "what should I do next?" everywhere. | North star N1 |
| N2 | **Delight and polish** | No placeholder copy, no generic cards; micro-interactions, loading states, empty states that feel intentional and on-brand. | North star N2; §8.0.11 |
| N6 | **Role-native personalization** | Dashboard and nav adapt to role, school type, and region; terminology matches "how this school works." | North star N6 |
| N7 | **Progressive disclosure** | No clutter; power features when needed; one primary action per page (one action model) everywhere. | North star N7; §0.4.4 clarity over clutter |
| N8 | **Command palette as primary** | Ctrl+K and role-home make "find anything in 1–2 actions" the norm; intents for heaviest flows. | North star N8; §8.0.4 |
| — | **Measured click reduction** | Fill CLICK_REDUCTION_BASELINE.md with **measured** Baseline and Final (human click-through); prove ~50% reduction. | Phase I.5 §8.0.3; §0.4.3 |

---

## 2. Performance, reliability, and resilience

| # | Improvement | Why beyond reach | SOT ref |
|---|-------------|------------------|---------|
| N9 | **Sub-second for all core actions** | Dashboard, list first page, save, search: &lt;1s p50, &lt;2s p99; no NXT-style multi-second waits. | North star N9; §0.4.3 |
| N10 | **Performance budgets strict in CI** | Gate fails when core metrics regress; LCP, FID, CLS and key API latencies in gate. | North star N10 |
| N11 | **Uptime and resilience story** | SLO/SLA documented; runbooks; "another Bromcom-style outage" designed against. | North star N11; §0.4.2 Arbor |
| N12 | **Graceful degradation** | Rate limits, queue depth, "try again" flows; no silent failures or white screens under load. | North star N12 |
| N5 | **Offline and resilience** | Critical reads (timetable, contacts) available offline or degraded; clear "back online" and sync status. | North star N5 |

---

## 3. Trust, compliance, and security

| # | Improvement | Why beyond reach | SOT ref |
|---|-------------|------------------|---------|
| N13 | **Trust center as product** | Security, compliance, data handling, retention, breach response in one place; kept current and auditable. | North star N13 |
| N14 | **Data residency and sovereignty** | Clear communication and controls; region-specific compliance (GDPR, FERPA) documented and enforced. | North star N14 |
| N15 | **Audit and accountability** | Every sensitive action logged; export for auditors; retention and access controls documented. | North star N15 |
| N16 | **Certifications and attestations** | SOC 2, ISO, or equivalent roadmap; security review and trust signals for marketplace and partners. | North star N16 |
| — | **Security posture post–PowerSchool** | Least-privilege support access; audit of all data access; trust-center-grade transparency. | §0.4.1 Security and trust |

---

## 4. Ecosystem and extensibility

| # | Improvement | Why beyond reach | SOT ref |
|---|-------------|------------------|---------|
| N17 | **Marketplace certification and trust** | App scopes, permissions, security review; **dependency graph and impact preview** for pack apply; "install and trust" story. | North star N17; §0.3 pillar 4 |
| N18 | **Developer experience** | Versioned API docs, sandbox, clear auth and webhooks; third-party apps can build and test without guessing. | North star N18; §0.3 Integration |
| N19 | **Webhooks and events** | Reliable delivery, retry, idempotency; event catalog and schema so integrations are first-class. | North star N19 |
| N20 | **Pack versioning and rollback** | Every pack type versioned; preview and one-click rollback so changes are safe and reversible. | North star N20 |

---

## 5. International and inclusion

| # | Improvement | Why beyond reach | SOT ref |
|---|-------------|------------------|---------|
| N21 | **Full i18n and locale** | All user-facing strings translatable; locale from tenant/region; date, number, currency by region. | North star N21 |
| N22 | **RTL and regional UX** | RTL layout where required; regional packs as installable products (MENA rtl done; extend). | North star N22 |
| N23 | **Inclusive terminology and imagery** | No internal jargon in UI; imagery and examples reflect global diversity and school types. | North star N23 |
| N3 | **Accessibility (WCAG 2.1 AA)** | Keyboard nav, screen-reader support, focus management, color contrast, skip links; audit and fix critical pages. | North star N3 |
| N4 | **Mobile-first and touch-native** | Every high-use flow works on phone/tablet; no horizontal scroll; touch targets ≥44px; responsive lint in CI. | North star N4 |

---

## 6. Innovation and differentiation

| # | Improvement | Why beyond reach | SOT ref |
|---|-------------|------------------|---------|
| N27 | **AI-native workflows** | Setup, recommendations, and **"what should I do next?"** powered by context; no dead ends. | North star N27 |
| N28 | **Predictive and proactive** | Early warnings (at-risk, deadlines); suggested actions; platform feels anticipatory. | North star N28 |
| N29 | **Setup in minutes, not days** | School creation, integration, and first use in minimal steps; Launch Studio as **proven** path (measured). | North star N29 |
| — | **Choose region → Create School** | From Geography (or curriculum packs), link "Create school" with region/pack pre-selected (query param or step 1 default). | WEDGES_7_13_GEOGRAPHY_PLAN §8 |
| — | **Phase 2 advancement in-product** | Full donor/campaign/gift/receipt CRUD (not placeholder); one identity graph visible in UX. | Wedge 5; §0.4.4 |

---

## 7. Operational and support excellence

| # | Improvement | Why beyond reach | SOT ref |
|---|-------------|------------------|---------|
| N24 | **Observability and runbooks** | Metrics, traces, logs; runbooks for common incidents; on-call and escalation path clear. | North star N24 |
| N25 | **Rollout and migration playbooks** | Documented migration, validation, rollback, phased rollout; no go-live disasters. | North star N25; §0.4.3 |
| N26 | **Support and onboarding as product** | Training, post-go-live support, "day two" experience so schools succeed after launch. | North star N26; §0.4.1 |

---

## 8. Foundation and tech debt (enables everything else)

| Improvement | Why beyond reach | SOT ref |
|-------------|------------------|---------|
| **Structural tech debt** | Giant files split; side roads removed; orchestration clear so scale and velocity don’t stall. | §0.3 pillar 1; §6 app-by-app |
| **SiteSettings decomposition** | Move behavior out of get_solo/SiteSettings into bounded domains; tenant paths use runtime/config, not raw settings. | §0.3; §3.2; §5 |
| **Raw SQL and exceptions** | Wrap remaining allowlisted raw SQL in repository/service; add signature/replay where manual_review_required; reduce broad except. | §2.4; §6 |
| **Clever/ClassLink (when unblocked)** | Roster + SSO connector for district/LMS glue so we match Infinite Campus / PowerSchool on "one roster, any LMS." | Wedge 4; §0.4.1 |

---

## 9. Wedge-specific beyond reach

| Wedge | Improvement | Why beyond reach |
|-------|-------------|------------------|
| 1 K–12 | **Go-live &lt;2 weeks proven** | Prove with real-school go-lives; measured time from signup to first use. |
| 2 LMS | **Spine with SLAs** | Document or enforce SLAs for SSO, roster sync, grade passback. |
| 3 UK | **UK statutory as full report pack product** | Sellable UK report pack (Ofsted + statutory) as one installable product. |
| 4 District | **Clever/ClassLink or equivalent** | Unblock when vendor/API allows; district roster + SSO as product. |
| 5 Advancement | **Phase 2 full CRUD** | Donor/campaign/gift/receipt list and detail views, not placeholder. |
| 6 HE | **Months-not-years proven** | HE implementation in months not years; prove with real HE go-lives. |
| 7–13 Geography | **Country-specific presets** | Extend moe_presets and education_dna for India CBSE, Singapore, Canada provincial, MENA country, etc., as we go to market. |

---

## 10. Suggested order (beyond reach)

1. **Quick differentiators:** N27/N29 — "What should I do next?" and setup-in-minutes (guided onboarding + Launch Studio proven path); N8 — command palette intents for heaviest flows; Choose region → Create School from Geography.
2. **Trust and performance:** N9/N10 — sub-second and strict performance gates; N13–N16 — trust center current, SOC 2/ISO roadmap; N11/N12 — SLO and graceful degradation.
3. **Experience bar:** N1, N2, N6, N7 — zero learning curve, delight, role-native, progressive disclosure; measured click reduction (CLICK_REDUCTION_BASELINE).
4. **Ecosystem:** N17–N20 — marketplace dependency/impact preview, developer docs/sandbox, webhooks, pack rollback.
5. **International and a11y:** N21–N23, N3, N4 — full i18n, RTL, inclusive copy/imagery, WCAG, mobile-first.
6. **Operations:** N24–N26 — runbooks, migration playbooks, support as product.
7. **Foundation:** §0.3 pillars to MET; SiteSettings decomposition; structural tech debt per §6.

**Rule:** All status and completion stay in the SOT. When an item above is DONE, mark it in the SOT (North star table, §0.3, or §11.4); do not leave this doc as the source of truth.

---

## 11. Remaining (not yet done — why)

Items below are **left** after implementing everything that could be done in bounded, non–multi-week work. Track completion in the SOT when addressed.

| Category | Items | Why not done in this pass |
|----------|--------|----------------------------|
| **Blocked / vendor** | Clever/ClassLink (Wedge 4); district roster + SSO as product | Vendor/API unblock required. |
| **Multi-week / structural** | SiteSettings decomposition; §6 app-by-app structural tech debt; raw SQL wrap + signature/replay; giant file splits | Large refactors; dependency-ordered per SOT. **Next steps:** [domain_ownership.md](domain_ownership.md) §5 (SiteSettings); raw SQL in repositories only (e.g. siteconfig/repositories/database_recovery_repository.py); evals/performance_optimization raw_sql_replacement_targets. |
| **Proven with real usage** | Go-live &lt;2 weeks proven (Wedge 1); months-not-years HE (Wedge 6); Setup in minutes **measured** (N29) | Requires real-school go-lives and measured baselines. |
| **Full product scope** | Phase 2 advancement full CRUD (donor/campaign/gift/receipt + identity graph); UK statutory as full report pack product; LMS spine with SLAs | Substantial feature build; beyond a single pass. |
| **Ongoing / incremental** | N1 zero learning curve (everywhere); N2 delight/polish (every surface); N6 role-native (all terminology); N7 progressive disclosure (every page); N9 sub-second p50/p99 (all core actions); N12 graceful degradation (all APIs); N18 versioned API docs/sandbox; N19 webhooks/event catalog; N20 pack versioning/rollback UI; N21 full i18n (all strings); N22 RTL extend; N3/N4 WCAG/mobile audit and fix | Incremental rollout; audit-and-fix or extend existing. |
| **Documentation / policy** | Security posture post–PowerSchool (least-privilege, audit); country-specific presets (India CBSE, Singapore, Canada provincial) | Doc and config expansion; extend moe_presets/education_dna as we go to market. |

**Done in this run (recorded in SOT):** Choose region → Create School; command palette intents (Create school, Geography, Trust center); Trust center SLO & uptime (N11), Support & onboarding (N26), Certifications (N16), Resilience/runbooks; N25 RUNBOOKS_INDEX + RELEASE_CHECKLIST links; Tenant Studio i18n; UX checklist N23; N17 roadmap in MARKETPLACE_GAPS.

**Done (BEYOND_REACH remaining pass):** BLOCKED/measurement doc (BEYOND_REACH_BLOCKED_AND_MEASUREMENT.md); structural next-step refs (domain_ownership, raw SQL in repos); Phase 2 advancement placeholder roadmap line; N12 graceful degradation (NORTH_STAR doc + 429 in api/auth_views); N18–N20 Ecosystem card in Trust center; N3/N4 in UX_PAGE_AUDIT_CHECKLIST §5; Security posture card in Trust center; moe_presets india_cbse; BEYOND_REACH §11 table updated with next-step links.

**Blocked and measurement:** [BEYOND_REACH_BLOCKED_AND_MEASUREMENT.md](BEYOND_REACH_BLOCKED_AND_MEASUREMENT.md) — Clever/ClassLink (blocked until vendor unblock); go-live &lt;2 weeks / HE months / N29 setup-in-minutes measurement process.
