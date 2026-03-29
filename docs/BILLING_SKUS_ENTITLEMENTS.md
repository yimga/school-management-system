# Billing SKUs and entitlements (BR-10)

**Canonical machine registry:** `apps/siteconfig/billing_sku_registry.py` (tier → feature-code bundles; exposed under `plan_entitlements` on `/api/v1/manifest.json`). Keep this table aligned when marketing or trust-center wording changes.

| SKU tier | Includes | Notes |
|----------|----------|-------|
| **Core** | SIS, academics, people, portal, basic reports | Default tenant |
| **Interop** | OneRoster, district hub, LTI/OIDC/SAML, SCIM | Add-on or bundle |
| **Intelligence** | Analytics benchmarks, ML stubs, at-risk (EWS), AI gateway quotas | Entitlement-gated |

Align `Plan` / marketplace listings with this matrix; document in trust center and `/api/v1/manifest.json` feature flags where applicable.

## Report platform SKUs (Batch 14+)

Granular **plan/add-on** feature codes for the reports bounded context, **additive** to the coarse module gate `reports` (still the default `Plan.included_features` entry for “has reports”). Bundle slugs and code lists are machine-readable in `billing_sku_registry.REPORT_PLATFORM_SKU_BUNDLES` and under `plan_entitlements.report_platform_skus` on `/api/v1/manifest.json`.

**Operator default bundle (platform singleton):** When set in platform admin (**`PlatformReportPlatformSkuDefault`**, migration **`platform_runtime.0036`**), `/api/v1/manifest.json` may also include **`plan_entitlements.operator_default_report_platform_bundle`** (a known bundle slug such as **`reports-standard`**). Empty or unknown stored values are omitted from the manifest.

**HTTP / API gates (tenant):** For paths that use **`is_plan_entitlement_feature_enabled`**, granular report-platform feature codes in that operator bundle are treated as **enabled in addition to** explicit plan/addons/School.features **only when** the tenant already has coarse **`reports`** on plan/addons/features. Coarse **`reports`** itself is **not** implied by the operator bundle (manifest-only **`reports`** still does not satisfy SKU gates). **Per-tenant override:** **`School.report_platform_bundle_slug`** (`reports-standard` / `reports-advanced`, empty = operator default only) **replaces** the platform operator default for the floor on that school. Implementation: **`get_effective_report_platform_floor_codes_for_school()`**, **`get_operator_report_platform_bundle_feature_codes()`** in **`billing_sku_registry`**, **`is_plan_entitlement_feature_enabled`** in **`apps/schools/models.py`** (platform admin **Schools**).

**Authenticated API read-model (tenant context):** For clients that already resolve the current school, **`GET /api/v1/me/schools`** includes **`report_platform_bundle_slug`** (normalized stored value, may be empty) and **`effective_report_platform_bundle`** (known bundle slug or JSON **`null`**) on each **`schools[]`** and **`child_schools[]`** row. **`GET /api/v1/config/education-dna`** (requires **`request.school`** + auth) echoes the same two keys for the active tenant. Resolution uses **`get_operator_default_report_platform_bundle_slug()`** once per response where multiple schools are listed to avoid N+1 queries.

| Bundle slug | Intent |
|-------------|--------|
| **reports-standard** | PDF exports + shared template library on top of coarse `reports` |
| **reports-advanced** | Standard plus custom builder, scheduled delivery, ministry-oriented exports |

### HTTP feature gates (tenant)

When `request.school` is set, **`FeatureGatekeeperMiddleware`** enforces:

| Path prefix | Capabilities (any) |
|-------------|-------------------|
| `/reports/regulatory-export/` | `reports_ministry_exports` **or** `reports` |
| `/reports/statistical-return/` | `reports_ministry_exports` **or** `reports` |
| `/reports/publish/`, `/reports/promotion-preview/` | coarse **`reports`** only (plan / addons / `School.features`) |
| `/api/v1/reports/regulatory-presets`, `/api/v1/reports/regulatory-export` (and subpaths) | `reports_ministry_exports` **or** `reports` |
| `/api/v1/reports/emis` (and subpaths such as `/api/v1/reports/emis/prepare`) | `reports_ministry_exports` **or** `reports` |
| `/reports/parent/report/` | `reports_pdf_exports` **or** `reports` |
| `/siteconfig/reports/builder/`, `/siteconfig/reports/preview/`, `/siteconfig/reports/embed-preview/`, `/siteconfig/reports/live-preview/` | `reports_custom_builder` **or** `reports` |
| `/siteconfig/reports/download/` (per-template paths under this prefix) | `reports_custom_builder` **or** `reports` |
| `/siteconfig/reports/bulk-letters/` | `reports_custom_builder` **or** `reports` |
| `/api/v1/reports/adhoc` (list/create/run under this prefix) | `reports_custom_builder` **or** `reports` |
| `/siteconfig/reports/scheduled/` | `reports_scheduled_delivery` **or** `reports` |
| `/api/v1/reports/scheduled` | `reports_scheduled_delivery` **or** `reports` |
| `/analytics/` (tenant analytics app; all subpaths) | **`analytics`** only (BR-10 Intelligence — not implied by core manifest) |

Implementation: **`FEATURE_GATE_PATH_ANY_OF`** in `apps/schools/middleware.py`, resolved with **`is_plan_entitlement_feature_enabled`** (plan, addons, `School.features` — not module-manifest `required_apps`) for the rows above that use “any” SKU semantics; **`analytics`** uses the same resolver with a single code. Coarse **`reports`** on the plan preserves legacy access for report rows; sell **`reports_ministry_exports`**, **`reports_pdf_exports`**, **`reports_custom_builder`**, or **`reports_scheduled_delivery`** alone when product packaging calls for it.

**`reports_scheduled_delivery`:** tenant hub **`siteconfig:scheduled_reports_delivery_hub`** (staff see a link to **`admin:reports_tenantreportschedule_changelist`**; non-staff users with **`settings.manage`** still use the hub but do not get the admin deep link; template summarizes REST paths (list URL uses **`reverse("api_v1:reports-scheduled-list")`** when the name resolves) and command flags; **active** rows with **zero** recipients show an on-page warning). **`GET` / `POST /api/v1/reports/scheduled`** list or create **`TenantReportSchedule`** (optional list query **`?is_active=`** / **`?delivery_ready=`** as boolean strings; each list row includes **`recipient_count`**, **`has_recipients`**, **`delivery_ready`** — no raw addresses on list; **POST** returns the same three flags plus **`name`**, **`report_key`**, **`is_active`** on **201**). **`GET` / `PATCH` / `DELETE /api/v1/reports/scheduled/<id>`** — detail includes full **`recipients`** plus the same flags; **`PATCH`** echoes **`name`**, **`report_key`**, **`is_active`** and flags after update; **`DELETE`** includes **`schema`:** **`reports_scheduled_delivery_v2`**; **`PATCH`** runs **`full_clean()`** so legacy rows cannot be re-activated without addresses. **POST** with **`is_active: false`** may use **`recipients: []`**; active creates still require ≥1 email. **Tenant admin:** **`TenantReportSchedule`** changelist includes **`last_run`**, **recipient count**, bulk action to **deactivate** rows that are **active** with **empty** **`recipients`**. **Model:** **`clean()`** enforces at least one recipient when **`is_active`**; **`recipients`** allows **`blank=True`** (migration **`reports.0020`**) so inactive rows may store **`[]`**. Operators run **`python manage.py send_scheduled_reports`** (or Celery **`ScheduledReportRunner.run_due_reports`** with optional **`school_id`**, **`limit`**, **`dry_run`**, **`strict_no_skip`**, **`json_summary`**) to process due rows — CLI also supports **`--school-id`**, **`--limit`**, **`--strict-no-skip`**, **`--json-summary`**; **`CommandError`** when a run ends with failures or (with strict) skipped empty-recipient rows; **stderr** / **`--dry-run`** warn when a due **active** row has no recipient addresses (delivery skipped for that run; cadence still advances). **DDL:** **`reports.0018`**, **`reports.0020`** ( **`reports.0019`** RLS PostgreSQL).
