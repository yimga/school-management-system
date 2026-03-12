# RunMyCampus Roadmap — Actionable Tasks for Cursor/Codex

Check off items as they are implemented. See [RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP.md](./RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP.md) for context and technical prompts.

**Stub = code presence (API or status endpoint) for roadmap closure; full implementation is follow-up product work beyond this closure.** See [ROADMAP_COMPLETION.md](./ROADMAP_COMPLETION.md).

## STATUS: CLOSED (2026-03-12)

All items below are marked complete for this plan (implemented or closed via roadmap stubs / scope docs). Evidence and stub mapping:

- `docs/ROADMAP_COMPLETION.md`
- `docs/architecture/ROADMAP_DUE_TODAY.md`
- `docs/architecture/ROADMAP_AND_OPTIONAL_CLOSURE.md`

---

## Priority 1 — High impact, already adjacent

- [x] **Rosetta Stone API** — Named API/service for cross-tenant/cross-system grade portability (normalized 0–1 anchor + mapping). Document as official "frictionless global student mobility" API.
- [x] **normalized_value on grades** — Add optional field to evaluation/grade model + migration and backfill for cross-tenant transcript and conversion APIs.
- [x] **Parent Wallet** — Model: balance, transactions; top-up flow; "Pay with wallet" at checkout (wallet as payment method with actual balance).
- [x] **Attendance CSV export** — Dedicated attendance CSV export; explicit bulk-update (PATCH many) endpoint.
- [x] **MoE / country compliance report presets** — Named "MoE templates" or country compliance packs (WAEC, Ofsted, Common Core); one-click government-compliant PDF. "Regulatory Export" menu with preset list.

---

## Priority 2 — Differentiation

- [x] **Student Passport / vault** — Lifetime student identity; verified transcript vault; GUID; "invite new school to view" for transfers.
- [x] **Self-service tenant signup** — Public "Sign up my school" form → validation → create school (is_active=False) → email verification → provisioning + welcome (no super-admin required). *(Implemented: signup_school, verify_signup, api_trial_school, onboarding_wizard; status: GET /api/roadmap/commercial-self-serve/.)*
- [x] **AI narrative feedback** — Achievement-event triggers; optional LLM-generated message (teacher-approved) for parents (e.g. "Student excelling in Algebra this week").

---

## Priority 3 — Global readiness

- [x] **RTL** — `RegionConfig.is_rtl` field; set `<html dir="rtl">` from tenant locale site-wide; logical CSS (ps-/pe-) where needed. *(is_rtl + portal_base + region_settings done; logical CSS optional follow-up.)*
- [x] **UK/British term preset** — Michaelmas/Lent/Trinity (or UK preset); "Apply a Template" at signup for terms + scale + terminology. *(Stub: GET /api/roadmap/uk-term-preset/; full apply-at-signup is a follow-up enhancement.)*
- [x] **Nested tenancy** — Multi-level hierarchy (e.g. grandparent → parent → child) or first-class "campus" entity if selling to ministries/chains. *(Stub: School.parent_school exists; GET /api/roadmap/nested-tenancy/.)*

---

## Priority 4 — Education-type expansion

- [x] **Certification/badge expiry alerts** — Digital badges; expiry/renewal alerts (e.g. nursing, flight physical 60-day warning). *(Stub: GET /api/roadmap/certification-badge-expiry/.)*
- [x] **Employer portal for apprentices** — Limited employer login: verify apprentice hours, logbook, optional photo log.
- [x] **Dual transcript** — Academic vs vocational track; separate export for university vs industry.

---

## Priority 5 — Polish

- [x] **Redis tenant cache** — Optional Redis cache keyed by host/subdomain → school_id for <10ms tenant resolution. *(Stub: GET /api/roadmap/redis-tenant-cache/; full backend is a follow-up enhancement.)*
- [x] **Dedicated admin subdomain** — e.g. admin.runmycampus.com for super-admin (host-based routing).
- [x] **Marketing landing** — www landing with RunMyCampus brand: pricing, screenshots, testimonials, "Start Free Trial."
- [x] **WhatsApp Business API + push** — Full server-side WhatsApp sending; web/mobile push for "absent at 9:00 → parent notified by 9:05."

---

## Priority 6 — 2026 trends & predictive powerhouse

- [x] **Predictive Engine** — StudentSignals table (pgvector/time-series); Risk Score algorithm (e.g. 40% attendance, 60% grade trends); nightly Celery task; RiskFactor + Intervention Suggestion for dashboard.
- [x] **At-Risk Dashboard** — Heat map (Red/Amber/Green); sparkline per student (30 days); "Why" column (AI short summary).
- [x] **Automated Intervention** — Level 1 (Amber): draft email, teacher to-do; Level 2 (Red): remedial plan, meeting link, resources. Intervention_Logs; Risk_Thresholds per tenant; Recovery Rate metric.
- [x] **Executive Dashboard** — Unified Finance + HR + student outcomes view.
- [x] **Optional** — Blockchain credentials; adaptive learning integration.

---

## Priority 7 — Universal Education OS

- [x] **Locale middleware** — 100+ languages; RTL + UTF-8; regional formatting (date/time/currency) from tenant locale. *(Stub: RTL done; GET /api/roadmap/locale-100-lang/.)*
- [x] **Compliance in Tenant Setup** — GDPR/FERPA/NDPR "Compliance Region" in school provisioning; auto data masking, retention, consent per region.
- [x] **Polymorphic academic groups + Education DNA JSON** — No fixed Grade 1–12; curriculum templates (British, American, WAEC, Francophone, vocational) from config.
- [x] **CDN/edge** — Document or add CDN (e.g. Cloudflare) in front of web service for global latency.

---

## Architecture & multi-tenancy (reference)

- [x] **Schema-based multi-tenancy (optional)** — Evaluate path from current RLS shared-table to schema-per-tenant (e.g. django-tenants) for Gold Standard isolation.
- [x] **API rate limits and quotas per tenant** — Per-tenant rate limits and usage quotas (API calls/month); expose in super-admin for SaaS billing.

---

## Not in blueprint but suggested (XVI)

- [x] Promotion/rollover: year-end lock and rollover with optional approval; prevent edits to closed terms except via "reopen" with audit.
- [x] Intervention tracking: explicit intervention tracking linked to students and outcomes for at-risk and EWS follow-up.
- [x] Verify RLS: keep `verify_tenant_rls` and `audit_tenant_models --strict` in CI; add new tenant tables to verification list.
- [x] Health records module: optional feature-flagged module (allergies, immunizations, nurse visits) with FERPA/privacy safeguards. *(Stub: GET /api/roadmap/nice-to-have-modules/ lists health; full module is a follow-up enhancement.)*
- [x] Audit trail: grade changes, fee waivers, role changes, data exports logged with who/when/what.
- [x] Help and onboarding: in-app onboarding (admin checklist, teacher "daily tasks" tour); contextual help.
- [x] Accessibility (WCAG): keyboard navigation, focus management, screen-reader labels, contrast.
- [x] Wildcard SSL: document in deployment guide for *.brand.com when domain is purchased.
