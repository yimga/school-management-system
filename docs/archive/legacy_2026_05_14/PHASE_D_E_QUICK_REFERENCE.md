# Phase D & E quick reference

## Phase D — Feature gate & plan

- **Plan model:** `apps.siteconfig.models.Plan` (name, slug, max_students, max_staff, included_features, billing_model, base_price, price_per_student, tier_rules, is_active).
- **School:** `plan` (FK), `addons` (JSON list of feature codes). Feature check: `is_feature_enabled(school, code)` in `apps.schools.models` (plan.included_features + school.addons + legacy fallback).
- **FeatureGatekeeperMiddleware:** `apps.schools.middleware`. Path → feature map: `FEATURE_GATE_PATH_MAP` (e.g. `/portal/design-studio/` → `design_studio`). Add new gated paths there; middleware returns 403 if path is gated and feature not enabled.
- **UsageLimitMiddleware:** Same file; on by default. Enforces plan max_students / max_staff; skipped for COMPLIMENTARY/MANUAL_OVERRIDE. Disable with `DISABLE_USAGE_LIMIT_MIDDLEWARE=1`.
- **Upgrade placeholder:** `templates/components/upgrade_modal_placeholder.html`; use in UI when feature is gated. In templates: `{% load feature_control %}` then `{% feature_enabled "design_studio" as has_ds %}`; if not has_ds, `{% include "components/upgrade_modal_placeholder.html" %}` instead of gated content.

## Phase E — Monetization & billing UX

- **School:** `billing_type`, `waiver_note` (migration 0006). BillingType: REGULAR, FREE_TRIAL, COMPLIMENTARY, MANUAL_OVERRIDE.
- **Plan Configurator API:** `GET /super/api/plans-configurator/?country_code=XX` — plans, addons, country_multiplier. See `docs/PLAN_CONFIGURATOR_API.md`.
- **RevenueSnapshot:** `apps.siteconfig.models`; filled by `calculate_monthly_stats` (Celery task `siteconfig.calculate_monthly_revenue_stats` or management command `calculate_monthly_revenue_stats`).
- **Financial Bento:** Super dashboard shows total_mrr, total_waived, waiver_%, revenue_by_country, billing_model_breakdown from RevenueSnapshot.
- **WaiverRequest:** proof_file, reason, status (PENDING/APPROVED/DENIED), decided_by, decided_at. Admin actions: approve (sets school.billing_type=COMPLIMENTARY, waiver_note, BillingWaiverAuditLog), deny.
- **School request waiver:** `accounts:request_waiver` — Backend → Request subscription waiver (reason + optional proof); staff with settings.manage.
