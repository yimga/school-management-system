# API usage for integrators

## Discovery

- **`GET /api/v1/manifest.json`** — platform manifest including `plan_entitlements` (BR-10 bundles, report-platform SKUs, and `commercial_packaging` tier ladder). Implemented via `apps.siteconfig.billing_sku_registry.manifest_plan_entitlements_block()` and related helpers.

## Authenticated tenant APIs

- Resolve the active school from host + session (multi-tenant middleware).
- Read models such as **`GET /api/v1/me/schools`** and **`GET /api/v1/config/education-dna`** echo entitlement-related fields where documented in `docs/BILLING_SKUS_ENTITLEMENTS.md`.

## Feature gating

Server-side checks use `School.has_feature`, `is_plan_entitlement_feature_enabled`, and marketplace **`entitlement_hints_for_school`** for catalog UX. Do not rely on client-side flags alone for authorization.

## Webhooks and keys

Tenant **API Center** routes (linked from the marketplace ecosystem hub) cover keys and delivery health; keep secrets out of manifests and VCS.
