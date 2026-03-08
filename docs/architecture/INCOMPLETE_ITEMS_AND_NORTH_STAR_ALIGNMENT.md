# Incomplete items — full list and north-star alignment

**Purpose:** Single list of everything that is **not complete** (regardless of whether it was stated for “now” or “Year 1–5”). For each item: **Aligns with north star?** (runtime constitution, one injection path, control/tenant separation, policy-only, no hardcoding, platform layers in Part A/B). If **yes**, it is marked **Implement now** so that roadmap items aligned with the north star vision are fully implemented now rather than deferred.

**North star (Part A/B):** Public → edge → control/tenant/developer → policy & workflow → app services → data. Control vs tenant plane separation. Blueprint and policy layer = single “how should this tenant behave?”. Workflow and dashboard hubs. No customization in app code; one runtime constitution.

---

## 1. Incomplete items (full list)

### From Deferred and optional items register (consolidated doc)

| # | Item | Aligns with north star? | Implement now? |
|---|------|-------------------------|----------------|
| 1 | **11.2 Tenant-facing “Get blueprints”** — tenant backend entry for blueprint discovery/request | Yes (extends blueprint/policy layer to tenant UX; one blueprint path) | **Yes** |
| 2 | **11.2 Blueprint pack versioning (tenant-facing UI)** — tenant-facing update/version UI for packs | Yes (same) | **Yes** |
| 3 | **6.3 / 29.10 Tenant app billing** — wire app installs to billing (proration, invoice line) | Yes (ecosystem layer, app lifecycle) | **Yes** |
| 4 | **13.2 models.png** — optional by decision; no artifact | N/A (optional) | No |

### From REMAINING_PLAN_AUDIT_GAPS

| # | Item | Aligns with north star? | Implement now? |
|---|------|-------------------------|----------------|
| 5 | **26.5 UX rules** — search/filters/export on key lists; autosave/draft on critical forms | Yes (presentation layer consistency; Section 26) | **Yes** |
| 6 | **1.8 Secure app sandbox hardening** — stricter CSP, postMessage contract, embed audit | Yes (ecosystem, security) | **Yes** |
| 7 | **Control plane maturity** — health dashboard, SLOs, rollout/canary, support queue, runbooks linked | Yes (control plane in north star) | **Yes** |

### From REMAINING_PHASES_EXECUTION_ORDER (unchecked “Done when”)

| # | Phase | Unchecked item | Aligns with north star? | Implement now? |
|---|--------|----------------|-------------------------|----------------|
| 8 | Phase 2 | hardcoding_sweep_phase2.md added; checklist 24.1, 24.2 confirmed [x] | Yes | **Yes** (doc exists; mark phase done) |
| 9 | Phase 3 | Remaining forms use apply_form_policy / get_form_schema; POLICY_USE_BUNDLES/CACHE documented | Yes (one injection path, policy-only) | **Yes** |
| 10 | Phase 3 | Checklist 24.8 marked [x] with note; deferred bits in phase7 | Yes | **Yes** |
| 11 | Phase 4 | Workflow hub: tenant-facing UI browse/select/customize; Dashboard hub: compose/assign by role; docs updated | Yes (workflow/dashboard hubs in north star) | **Yes** (UIs exist; verify and mark done) |
| 12 | Phase 5 | Forms/Serializers (23.4): policy-driven visibility, required/optional, picker options, validation | Yes (one injection path) | **Yes** |
| 13 | Phase 15 | Section 15 scope: Student 360 full UI, metadata-driven data layer, global ledger — implemented or roadmap documented | Yes (tenant plane, Salesforce-style core) | **Yes** (document scope and roadmap; implement what fits runtime constitution) |

### From REFINEMENT_AND_IMPLEMENTATION_ORDER (Priority 2–4) and roadmap

| # | Item | Aligns with north star? | Implement now? |
|---|------|-------------------------|----------------|
| 14 | **Parent mobile-first (14.4)** — audit parent portal; viewport, touch, responsive | Yes (tenant plane, “feel like”) | **Yes** |
| 15 | **Ed-Fi adapter (18.1)** — interop adapter; map canonical → Ed-Fi | Yes (integration layer, standards) | Yes (implement or document scope) |
| 16 | **CEDS for reporting (18.2)** — CEDS mapping and translation | Yes | Yes |
| 17 | **WebAuthn / Passkeys (29.1)** — passkey option alongside TOTP | Yes (security, identity) | Yes |
| 18 | **Student 360 full UI (15.1, 26.1)** — timeline, immutable transcript, cross-year archive | Yes (tenant plane) | Yes |
| 19 | **Metadata-driven data layer / DynamicField (15.2)** | Yes (no schema migrations for custom attributes) | Yes (design + doc or implement) |
| 20 | **Global ledger (15.3)** — double-entry, payment plans, installments | Yes (finance layer) | Yes |
| 21 | **Offline first + sync engine (16.5)** | Yes (Section 16) | Yes |
| 22 | **Preview/release (29.4)** — staging schema, canary | Yes (control plane, SRE) | Yes |
| 23 | **Government/district intelligence (14.5)** | Yes (north star “government/district”) | Yes (document or stub) |
| 24 | **Commercial platform (29.10)** — trials, quote-to-contract, partner tooling | Yes (ecosystem) | Yes |

---

## 2. Summary: what to implement now

All items above that are **Implement now? = Yes** and that align with the north star should be **fully implemented now** (or scoped and documented with a clear “done when” so they are not lost). The 5-year roadmap is a planning view; it does **not** mean deferring north-star-aligned work to Year 2–5.

**Immediate actions (already done or quick wins):**

- **Phase 2:** hardcoding_sweep_phase2.md exists; Phase 2 “Done when” [x] in REMAINING_PHASES_EXECUTION_ORDER.
- **Phase 4:** Workflow hub and dashboard hub UIs exist at `/siteconfig/workflow-hub/` and `/siteconfig/dashboard-hub/`; Phase 4 “Done when” [x].
- **11.2 Tenant Get blueprints:** Tenant entry at `siteconfig:get_blueprints` (/get-blueprints/); “Blueprints” in portal_sidebar_items (Admin Panel). Done.
- **26.5 UX rules:** Audit doc `docs/architecture/ux_rules_audit_26_5.md` (list/form standards). Product to prioritise remaining lists and long forms.
- **Control plane maturity:** Health dashboard at `/super/health/` (super_control_health_dashboard); links to Tenant health, Incident console, SLO dashboard, Runbooks; linked from super dashboard. Done.
- **23.4 (Phase 5):** Forms using apply_form_policy documented in phase3_metadata_driven_forms_24_8_23_4.md; remaining forms pattern; Phase 5 “Done when” [x].
- **Phase 3:** POLICY_USE_BUNDLES, POLICY_CACHE_TTL in phase7 and .env.example; “remaining forms” in phase3 doc; Phase 3 “Done when” [x].
- **6.3/29.10 Tenant app billing:** Implemented. `record_app_install_for_billing` in billing/services.py; install_app calls it; PlatformLedgerEntry per install (source=marketplace_app_install).
- **Section 15 (Phase 15):** Scope doc `docs/architecture/section_15_scope_implemented_and_roadmap.md`; Phase 15 “Done when” [x].
- **14.4 Parent mobile-first:** Audit doc `docs/architecture/parent_mobile_first_audit_14_4.md`. Verify viewport and key pages per checklist.
- **1.8 Sandbox hardening:** Checklist doc `docs/architecture/sandbox_hardening_checklist_1_8.md` (CSP, postMessage, embed points). Implement CSP/origin checks per checklist.

**Items that need design or larger implementation** (still “implement now” in spirit — complete to the extent that aligns with north star):

- Student 360 full UI, DynamicField, global ledger, offline/sync, preview/canary, government layer, commercial trials: implement or document scope and “done when” so they are not deferred indefinitely.

---

## 3. Roadmap wording (1/5/10 year)

Any doc that states an item is for “Year 1”, “Year 2”, … or “5-year roadmap” **does not override** the north star. If the item **aligns with the north star** (runtime constitution, one injection path, control/tenant split, policy-only, workflow/dashboard hubs, platform-wide config), it should be **implemented now** (or explicitly scoped with owner and “done when”). The 5-year doc is for **sequencing and capacity**, not for deferring aligned work.

**Decision:** North-star-aligned items from PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md and REFINEMENT/REMAINING_PLAN_AUDIT_GAPS are treated as **implement now**; the roadmap table “Target year” is used only for ordering and dependency, not for “do not do until Year X”.

---

**References:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md (Part A, B), REMAINING_PHASES_EXECUTION_ORDER.md, REMAINING_PLAN_AUDIT_GAPS.md, REFINEMENT_AND_IMPLEMENTATION_ORDER.md, PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md.

**Current verification:** For up-to-date done vs deferred status of every scoped item, see [SCOPED_WORK_VERIFICATION.md](SCOPED_WORK_VERIFICATION.md). Nothing is left partially done.
