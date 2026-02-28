# RunMyCampus Roadmap — Actionable Tasks for Cursor/Codex

Check off items as they are implemented. See [RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP.md](./RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP.md) for context and technical prompts.

---

## Priority 1 — High impact, already adjacent

- [ ] **Rosetta Stone API** — Named API/service for cross-tenant/cross-system grade portability (normalized 0–1 anchor + mapping). Document as official "frictionless global student mobility" API.
- [ ] **normalized_value on grades** — Add optional field to evaluation/grade model + migration and backfill for cross-tenant transcript and conversion APIs.
- [ ] **Parent Wallet** — Model: balance, transactions; top-up flow; "Pay with wallet" at checkout (wallet as payment method with actual balance).
- [ ] **Attendance CSV export** — Dedicated attendance CSV export; explicit bulk-update (PATCH many) endpoint.
- [ ] **MoE / country compliance report presets** — Named "MoE templates" or country compliance packs (WAEC, Ofsted, Common Core); one-click government-compliant PDF. "Regulatory Export" menu with preset list.

---

## Priority 2 — Differentiation

- [ ] **Student Passport / vault** — Lifetime student identity; verified transcript vault; GUID; "invite new school to view" for transfers.
- [ ] **Self-service tenant signup** — Public "Sign up my school" form → validation → create school (is_active=False) → email verification → provisioning + welcome (no super-admin required).
- [ ] **AI narrative feedback** — Achievement-event triggers; optional LLM-generated message (teacher-approved) for parents (e.g. "Student excelling in Algebra this week").

---

## Priority 3 — Global readiness

- [x] **RTL** — `RegionConfig.is_rtl` field; set `<html dir="rtl">` from tenant locale site-wide; logical CSS (ps-/pe-) where needed. *(is_rtl + portal_base + region_settings done; logical CSS optional follow-up.)*
- [ ] **UK/British term preset** — Michaelmas/Lent/Trinity (or UK preset); "Apply a Template" at signup for terms + scale + terminology.
- [ ] **Nested tenancy** — Multi-level hierarchy (e.g. grandparent → parent → child) or first-class "campus" entity if selling to ministries/chains.

---

## Priority 4 — Education-type expansion

- [ ] **Certification/badge expiry alerts** — Digital badges; expiry/renewal alerts (e.g. nursing, flight physical 60-day warning).
- [ ] **Employer portal for apprentices** — Limited employer login: verify apprentice hours, logbook, optional photo log.
- [ ] **Dual transcript** — Academic vs vocational track; separate export for university vs industry.

---

## Priority 5 — Polish

- [ ] **Redis tenant cache** — Optional Redis cache keyed by host/subdomain → school_id for <10ms tenant resolution.
- [ ] **Dedicated admin subdomain** — e.g. admin.runmycampus.com for super-admin (host-based routing).
- [ ] **Marketing landing** — www landing with RunMyCampus brand: pricing, screenshots, testimonials, "Start Free Trial."
- [ ] **WhatsApp Business API + push** — Full server-side WhatsApp sending; web/mobile push for "absent at 9:00 → parent notified by 9:05."

---

## Priority 6 — 2026 trends & predictive powerhouse

- [ ] **Predictive Engine** — StudentSignals table (pgvector/time-series); Risk Score algorithm (e.g. 40% attendance, 60% grade trends); nightly Celery task; RiskFactor + Intervention Suggestion for dashboard.
- [ ] **At-Risk Dashboard** — Heat map (Red/Amber/Green); sparkline per student (30 days); "Why" column (AI short summary).
- [ ] **Automated Intervention** — Level 1 (Amber): draft email, teacher to-do; Level 2 (Red): remedial plan, meeting link, resources. Intervention_Logs; Risk_Thresholds per tenant; Recovery Rate metric.
- [ ] **Executive Dashboard** — Unified Finance + HR + student outcomes view.
- [ ] **Optional** — Blockchain credentials; adaptive learning integration.

---

## Priority 7 — Universal Education OS

- [ ] **Locale middleware** — 100+ languages; RTL + UTF-8; regional formatting (date/time/currency) from tenant locale.
- [ ] **Compliance in Tenant Setup** — GDPR/FERPA/NDPR "Compliance Region" in school provisioning; auto data masking, retention, consent per region.
- [ ] **Polymorphic academic groups + Education DNA JSON** — No fixed Grade 1–12; curriculum templates (British, American, WAEC, Francophone, vocational) from config.
- [ ] **CDN/edge** — Document or add CDN (e.g. Cloudflare) in front of web service for global latency.

---

## Architecture & multi-tenancy (reference)

- [ ] **Schema-based multi-tenancy (optional)** — Evaluate path from current RLS shared-table to schema-per-tenant (e.g. django-tenants) for Gold Standard isolation.
- [ ] **API rate limits and quotas per tenant** — Per-tenant rate limits and usage quotas (API calls/month); expose in super-admin for SaaS billing.

---

## Not in blueprint but suggested (XVI)

- [ ] Promotion/rollover: year-end lock and rollover with optional approval; prevent edits to closed terms except via "reopen" with audit.
- [ ] Intervention tracking: explicit intervention tracking linked to students and outcomes for at-risk and EWS follow-up.
- [ ] Verify RLS: keep `verify_tenant_rls` and `audit_tenant_models --strict` in CI; add new tenant tables to verification list.
- [ ] Health records module: optional feature-flagged module (allergies, immunizations, nurse visits) with FERPA/privacy safeguards.
- [ ] Audit trail: grade changes, fee waivers, role changes, data exports logged with who/when/what.
- [ ] Help and onboarding: in-app onboarding (admin checklist, teacher "daily tasks" tour); contextual help.
- [ ] Accessibility (WCAG): keyboard navigation, focus management, screen-reader labels, contrast.
- [ ] Wildcard SSL: document in deployment guide for *.brand.com when domain is purchased.
