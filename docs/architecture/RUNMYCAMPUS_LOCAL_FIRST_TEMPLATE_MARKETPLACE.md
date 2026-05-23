# RunMyCampus — Local-First Global Template Marketplace + Experience Blueprint Engine

**Canonical architecture doc.** This document complements the executable plan at
[`docs/plans/LOCAL_FIRST_TEMPLATE_MARKETPLACE_PLAN.md`](../plans/LOCAL_FIRST_TEMPLATE_MARKETPLACE_PLAN.md)
and the per-wave generated audit artifacts under
[`docs/generated/local_first_template_*`](../generated/).

For the executable burndown of every plan section, read the plan. This file is
the *durable* architecture reference — it stays current as the program evolves.

---

## 1 — Mission

Premium operating-experience templates that are:
- **Browsable + comparable + previewable + applicable + customizable + rollback-safe.**
- **Role-aware** (operator / tenant-admin / teacher / parent / student / staff / specialized / local-first).
- **Local-first** (country / language / academic-system / calendar / payment-rails overlay).
- **Governed** (Preview → Impact → Apply → Audit → Rollback through the existing pack lifecycle).

## 2 — Architecture in one diagram

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                       ExperienceTemplate                             │
  │                    (registry, not new ORM model)                     │
  │  apps/platform_runtime/pack_contract.py::EXPERIENCE_TEMPLATE_PACKS   │
  │  apps/brand_experience/experience_templates.py::OVERLAYS             │
  │  apps/siteconfig/local_experience_profiles.py::PROFILES              │
  └──────────────────────────┬───────────────────────────────────────────┘
                             │ uses
                             ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │       Existing pack lifecycle (REUSED, NEVER DUPLICATED)             │
  │                                                                      │
  │  pack_preview ─► pack_simulation ─► pack_impact ─► pack_apply ─►     │
  │  pack_audit ─► pack_rollback     (apps/platform_runtime/)            │
  └──────────────────────────┬───────────────────────────────────────────┘
                             │ writes
                             ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  InstalledPackage (existing) + TemplateAssignment (new, OneToOne)    │
  │  PackageChangeLog (existing) + TemplateAuditEvent (new, append-only) │
  └──────────────────────────────────────────────────────────────────────┘
```

The architectural commitment: **never duplicate the pack lifecycle.** Every
template lifecycle event flows through the existing pack engine. The only new
ORM additions are `TemplateAssignment` (extends `InstalledPackage` 1:1) and
`TemplateAuditEvent` (append-only audit trail).

## 3 — Surfaces

- **Operator catalog:** `/configuration/experience-templates/*` (6 routes — reuses `pack_marketplace` / `pack_detail` / `pack_preview_view` / `pack_simulation_view` / `pack_impact_view` / `pack_apply_view`).
- **Tenant catalog:** `/school/studio/templates/*` (9 routes — `browse` / `recommend` / `local_catalog` / `detail` / `preview` / `compare` / `apply` / `rollback` / `customize`). Every view calls `_gate_operator_only()` before the underlying pack call.
- **Studio OS Experience section:** `templates/studio_os/partials/experience_templates_fold.html` — category quick-filter rail + dynamic overlay list.
- **Setup Studio:** new onboarding step `select_experience_template` between `branding` and `starter_stack`.

## 4 — Heritage design system

- 10 palette families: `editorial-cream`, `warm-terracotta`, `cool-indigo`, `green-emerald`, `desert-amber`, `monsoon-teal`, `sakura-blush`, `andes-clay`, `savanna-ochre`, `nordic-slate`.
- 3 typography stacks: `stack-editorial-serif`, `stack-system-sans`, `stack-bilingual-mixed`.
- 10 layout families (1=executive-command ... 10=premium-international).
- 75 thumbnail SVGs generated programmatically from registry state.
- **No flags in design.** No religious or political imagery. No ethnic-coded color choices.

Palette overrides arrive via `data-rmc-template-palette="<family>"` on root elements, resolving through the per-family `:root[data-rmc-local-palette="<family>"]` selector in `static/css/design-tokens-local-<family>.css`.

## 5 — AI recommendations

`apps.brand_experience.template_ai_recommender.recommend_for_school(school, *, user, request, use_ai=True)`:
- Routes through `services.ai_helpers.invoke_with_request` ONLY. **`services.ai_gateway` is forbidden** (boundary scanner + dedicated `verify_template_ai_recommender_boundary` enforce this).
- Registry-validates every AI proposal — refuses keys not in `OVERLAYS` and refuses operator-only proposals to tenants.
- Deterministic rules-based fallback when gateway absent or returns junk.
- PII-safe audit entry via `recommendation_audit_entry(rec, signals)` (omits raw user/school identifiers).

Live smoke: `python scripts/verify_template_ai_recommender_live_smoke.py` — reports `TEMPLATE_AI_RECOMMENDER_FALLBACK_PASS` today (gateway absent), auto-upgrades to `TEMPLATE_AI_RECOMMENDER_LIVE_PASS` when `LITELLM_*` + `RMC_PRODUCT_MCP_ENABLED=1` are configured on Render.

## 6 — Governance and external blockers

Wave E+ (live partner publishing + monetization billing) is gated behind:
- `RMC_TEMPLATE_PARTNER_PUBLISH_ENABLED` (default `0`).
- `RMC_TEMPLATE_MONETIZATION_ENABLED` (default `0`).

The 6-gate counsel docket at [`docs/TEMPLATE_MARKETPLACE_WAVE_E_COUNSEL_PENDING.md`](../TEMPLATE_MARKETPLACE_WAVE_E_COUNSEL_PENDING.md) lists every gate the operator + counsel must clear before either flag flips.

Manifest schemas for both partner-published templates and monetization are scaffolded in `apps/marketplace/template_partner_manifest.py` and `apps/marketplace/template_monetization_manifest.py` so partners can self-check manifests against the contract the platform will eventually accept.

## 7 — Verifiers (the bar for green)

| Verifier | Purpose |
|---|---|
| `verify_experience_template_registry` | 75 templates / 25 profiles / category distribution matches plan |
| `verify_template_marketplace_routes` | 6 operator routes resolve |
| `verify_template_tenant_boundaries` | Operator templates never appear in tenant catalog |
| `verify_template_local_first_coverage` | 23 priority markets coverage report; orphan-profile-ref check |
| `verify_template_a11y_floor` | Every template ≥ WCAG AA |
| `verify_template_ai_recommender_boundary` | Recommender never imports `services.ai_gateway` |
| `verify_template_ai_recommender_live_smoke` | End-to-end recommender invocation; fallback OK; LIVE when LiteLLM configured |
| `verify_template_marketplace_plan_compliance` | Audits every plan section against repo state |
| `audit_template_render_safety` | (Existing) Catches multi-line `{# … #}` regressions |
| `scan_off_token_colors` / `scan_undefined_css_classes` / 20 more | (Existing) Zero-tolerance gates that must stay 0 |

## 8 — Status

- **Batch 1400 (SW v3.63.0, 2026-05-23):** Foundational wave — 75 templates + 25 profiles + 10 palettes + AI recommender + 6 verifiers + 24 tests + 6 marketplace templates.
- **Batch 1401 (SW v3.64.0, 2026-05-23):** Plan §11.5 burndown — TemplateAssignment + TemplateAuditEvent + migration 0004 + Setup Studio step + Studio OS fold + Playwright + live-iframe compare + 10 palette splits + 75 thumbnails + AI live-smoke verifier + Wave E manifest scaffolds + counsel docket.
- **Plan compliance:** `TEMPLATE_MARKETPLACE_PLAN_COMPLIANCE_PASS` (71/71 checks PASS).
- **Verdict:** **75 PREMIUM TEMPLATE SYSTEM READY — REPO SCOPE.** Wave E+ live monetization explicitly counsel-pending.
