# AI domain assistant registry (canonical)

**Purpose:** Single granular inventory of every RunMyCampus productized AI HTTP endpoint (`/api/ai/*`), how to call it, what comes back, permission rules, and **exact** in-product UI embeddings.  
**Execution source of truth:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) section 0.5. This file is the detailed companion; do not duplicate a parallel “AI roadmap.”

**Control-plane aggregate console:** `super:ai_gateway_console` → `/super/ai-gateway-console/` (`templates/schools/super_ai_gateway_console.html`) — JSON cards for setup, tenant maturity, workflow draft, semantic search, document classify, admin copilot, theme / feature-control / report / design-studio / live-preview / system-config / dashboard-pack recommends, and AI feedback. Sidebar: Platform Overview → “AI gateway console”. Cross-link from AI Model Hub. **Studio / cross-host:** `super:ai_gateway_console` is registered in `apps/studio_os/deep_links._PATHS` for manager-base URL resolution.

**Global behavior**

- All routes: `login_required`, `csrf_protect` on POST; JSON `Content-Type: application/json` for POST bodies unless noted.
- Rate limiting: shared sliding window with admin copilot (`_check_rate_limit` in `views_ai_gateway.py`).
- Gateway: `services.ai_gateway.invoke`; audit: `AuditLog` via `_log_gateway_audit` where implemented.
- Permissions: `services.ai_permissions.get_ai_permission_for_user` — see **RBAC** column. Deny → HTTP 403 JSON `{"success": false, "error": "..."}`.

---

## 1. URL name → path → view (exhaustive)

| `reverse()` name | Path | View (`apps.portal.views_ai_gateway`) |
|------------------|------|----------------------------------------|
| `api:ai-setup-assistant` | `/api/ai/setup-assistant/` | `api_setup_assistant` |
| `api:ai-workflow-draft` | `/api/ai/workflow-draft/` | `api_workflow_draft` |
| `api:ai-policy-explain` | `/api/ai/policy-explain/` | `api_policy_explain` |
| `api:ai-document-classify` | `/api/ai/document-classify/` | `api_document_classify` |
| `api:ai-semantic-search` | `/api/ai/semantic-search/` | `api_semantic_search` |
| `api:ai-migration-suggest` | `/api/ai/migration-suggest/` | `api_migration_suggest` |
| `api:ai-admin-copilot` | `/api/ai/admin-copilot/` | `api_admin_copilot` |
| `api:ai-theme-recommend` | `/api/ai/theme-recommend/` | `api_theme_recommend` |
| `api:ai-feature-control-explain` | `/api/ai/feature-control-explain/` | `api_feature_control_explain` |
| `api:ai-report-recommend` | `/api/ai/report-recommend/` | `api_report_recommend` |
| `api:ai-design-studio-draft` | `/api/ai/design-studio-draft/` | `api_design_studio_draft` |
| `api:ai-live-preview-explain` | `/api/ai/live-preview-explain/` | `api_live_preview_explain` |
| `api:ai-system-config-explain` | `/api/ai/system-config-explain/` | `api_system_config_explain` |
| `api:ai-dashboard-pack-recommend` | `/api/ai/dashboard-pack-recommend/` | `api_dashboard_pack_recommend` |
| `api:ai-support-assistant` | `/api/ai/support-assistant/` | `api_support_assistant` |
| `api:ai-tenant-maturity` | `/api/ai/tenant-maturity/` | `api_tenant_maturity` |
| `api:ai-data-quality-assistant` | `/api/ai/data-quality-assistant/` | `api_data_quality_assistant` |
| `api:ai-marketplace-recommend` | `/api/ai/marketplace-recommend/` | `api_marketplace_recommend` |
| `api:ai-control-plane-intelligence` | `/api/ai/control-plane-intelligence/` | `api_control_plane_intelligence` |
| `api:ai-interop-assistant` | `/api/ai/interop-assistant/` | `api_interop_assistant` |
| `api:ai-runtime-config-explain` | `/api/ai/runtime-config-explain/` | `api_runtime_config_explain` |
| `api:ai-observability-assistant` | `/api/ai/observability-assistant/` | `api_observability_assistant` |
| `api:ai-billing-usage-explain` | `/api/ai/billing-usage-explain/` | `api_billing_usage_explain` |
| `api:ai-trust-compliance-assistant` | `/api/ai/trust-compliance-assistant/` | `api_trust_compliance_assistant` |
| `api:ai-studio-os-assistant` | `/api/ai/studio-os-assistant/` | `api_studio_os_assistant` |
| `api:ai-feedback` | `/api/ai/feedback/` | `api_ai_feedback` |

**Smoke test:** `apps.accounts.tests.test_smoke_urls.SmokeUrlResolutionTests.test_all_ai_gateway_api_paths_resolve`.

---

## 2. Request bodies, task types, response shapes

Task type strings below are `TaskType` enum names / `invoke` keys as passed from views (lowercase where applicable). `guided_assistant` schema: `services.ai_schemas.validate_guided_assistant`.

| Endpoint | HTTP | Required / typical JSON keys | Gateway task type(s) | Success JSON (top-level keys) |
|----------|------|------------------------------|------------------------|-------------------------------|
| setup-assistant | POST | `query` | `setup_recommend` | `success`, `response`, `citations`, `meta` |
| workflow-draft | POST | `description` or `query` | `workflow_draft` | `success`, `draft`, `meta` |
| policy-explain | POST | `query` or `policy_text` | `policy_explain` | `success`, `explanation`, `citations`, `meta` |
| document-classify | POST | `text` | `doc_classify` | `success`, `classification`, `meta` |
| semantic-search | GET or POST | `query`; optional `scope` (POST body or GET query) | `semantic_search` (optional summarize branch) | `success`, `results`, optional `summary`, `meta` |
| migration-suggest | POST | `source_fields` + `target_fields` **or** `source_sample` + `target_schema` | `migration_mapping` | `success`, `mappings`, `meta` |
| admin-copilot | POST | `query` | `admin_copilot` | `success`, `response`, `citations`, `meta` |
| theme-recommend | POST | `query` | `config_explain` + schema `theme_experience` | `success`, `suggestions`, `rationale`, `meta` |
| feature-control-explain | POST | `query` | `config_explain` | `success`, `explanation`, `meta` |
| report-recommend | POST | `query` | `setup_recommend` + schema `report_recommend` | `success`, `recommendations`, `meta` |
| design-studio-draft | POST | `query` | `config_explain` + schema `design_studio` | `success`, `suggestions`, `components`, `meta` |
| live-preview-explain | POST | `query` | `config_explain` | `success`, `explanation`, `meta` |
| system-config-explain | POST | `query` | `config_explain` | `success`, `explanation`, `meta` |
| dashboard-pack-recommend | POST | `query` | `setup_recommend` + schema `dashboard_pack_recommend` | `success`, `dashboards`, `packs`, `rationale`, `meta` |
| support-assistant | POST | `query` | `support_suggest` | `success`, `response`, `meta` |
| tenant-maturity | GET, POST | none (computed server-side) | none (no `invoke` in view) | `success`, `score`, `tier`, `recommendations`, `meta` |
| data-quality-assistant | POST | `query` | `config_explain` | `success`, `response`, `meta` |
| marketplace-recommend | POST | `query` or `institution_type` | `setup_recommend` + schema `marketplace_recommend` | `success`, `recommendations`, `rationale`, `meta` |
| control-plane-intelligence | POST | `query` | `admin_copilot` | `success`, `response`, `meta` |
| interop-assistant | POST | `query`; optional `context_snapshot`, non-secret | `interop_assistant` + `guided_assistant` | `success`, `guided` `{summary, actions, cautions, references}`, `meta` |
| runtime-config-explain | POST | `query`; optional `context_snapshot` | `runtime_config_explain` + `guided_assistant` | same guided shape |
| observability-assistant | POST | `query`; optional `context_snapshot` | `observability_assistant` + `guided_assistant` | same guided shape |
| billing-usage-explain | POST | `query`; optional `context_snapshot` | `billing_usage_explain` + `guided_assistant` | same guided shape |
| trust-compliance-assistant | POST | `query`; optional `context_snapshot` | `trust_compliance_assistant` + `guided_assistant` | same guided shape |
| studio-os-assistant | POST | `query`; optional `context_snapshot`, `studio_mode` | `studio_os_assistant` + `guided_assistant` | same guided shape |
| feedback | POST | `task_type`, `tier`; optional `accepted`, `manual_correction`, `feature`, `request_id`, `request_date` | n/a (records feedback) | `success`, `meta` |

---

## 3. RBAC (`services/ai_permissions.py`)

| Task string | Rule |
|-------------|------|
| `admin_copilot`, `config_explain`, `migration_mapping`, `migration_fingerprint`, `migration_parity`, `policy_explain` | `is_staff` required |
| `interop_assistant`, `runtime_config_explain`, `studio_os_assistant` | staff/superuser **or** tenant school context + tenant config role (ADMIN, IT_ADMIN, LEADERSHIP, PROPRIETOR, PRINCIPAL, VICE_PRINCIPAL) |
| `observability_assistant`, `trust_compliance_assistant` | staff or superuser |
| `billing_usage_explain` | staff/superuser **or** school context + finance-capable role (BURSAR, FINANCE_STAFF, ACCOUNTANT, ADMIN, PROPRIETOR, LEADERSHIP) |
| *(default)* | authenticated user allowed for tasks not listed above |

Guided assistants call `get_ai_permission_for_user` **before** prompt formatting (`_api_guided_domain_assistant`).

---

## 4. In-product UI embedding inventory

**Component: guided query → POST `{query, context_snapshot?, studio_mode?}`**  
`templates/components/ai_guided_assistant_card.html` + `static/js/rmc_ai_guided_assistant.js`

| Template | Included block context | `reverse()` / `field_id` |
|----------|------------------------|-------------------------|
| `templates/studio_os/shell.html` | Studio shell | `api:ai-studio-os-assistant`, `studioOsAiQShell` |
| `templates/studio_os/partials/shell_main_content.html` | Studio main | `api:ai-studio-os-assistant`, `studioOsAiQ` |
| `templates/accounts/district_lms_interop.html` | District interop hub | `api:ai-interop-assistant` (`distInteropAiQ`), `api:ai-runtime-config-explain` (`distRuntimeAiQ`) |
| `templates/schools/super_dashboard.html` | Control plane home | `api:ai-observability-assistant` (`cpObsAiQ`), `api:ai-billing-usage-explain` (`cpBillAiQ`), `api:ai-trust-compliance-assistant` (`cpTrustAiQ`) |
| `templates/schools/super_migration_cloud.html` | Migration cloud | `api:ai-trust-compliance-assistant` (`cpMigTrustAiQ`) |
| `templates/schools/billing_dashboard.html` | Platform billing | `api:ai-billing-usage-explain` (`billDashAiQ`) |
| `templates/marketplace/governance_console.html` | Marketplace governance | `api:ai-trust-compliance-assistant` (`govTrustAiQ`) |
| `templates/schools/super_trust_center.html` | Trust center | `api:ai-trust-compliance-assistant` (`trustCenterAiQ`) |

**Component: raw JSON body POST**  
`templates/components/ai_json_api_card.html` + `static/js/rmc_ai_json_api_card.js`

| Template | Endpoint | `field_id` |
|----------|----------|------------|
| `templates/schools/super_migration_cloud.html` | `api:ai-migration-suggest` | `cpMigMapJson` |
| `templates/schools/billing_dashboard.html` | `api:ai-data-quality-assistant` | `billDashDqJson` |
| `templates/marketplace/governance_console.html` | `api:ai-marketplace-recommend` | `govMktJson` |
| `templates/schools/super_trust_center.html` | `api:ai-policy-explain` | `trustCenterPolicyJson` |
| `templates/schools/super_command_center.html` | `api:ai-control-plane-intelligence` | `cmdCtrCpIntelJson` |
| `templates/schools/super_command_center.html` | `api:ai-support-assistant` | `cmdCtrSupportJson` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-setup-assistant` | `gwSetup` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-tenant-maturity` | `gwMaturity` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-workflow-draft` | `gwWorkflow` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-semantic-search` | `gwSemantic` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-document-classify` | `gwDoc` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-admin-copilot` | `gwCopilot` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-theme-recommend` | `gwTheme` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-feature-control-explain` | `gwFeat` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-report-recommend` | `gwReport` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-design-studio-draft` | `gwDesign` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-live-preview-explain` | `gwLive` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-system-config-explain` | `gwSysCfg` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-dashboard-pack-recommend` | `gwDash` |
| `templates/schools/super_ai_gateway_console.html` | `api:ai-feedback` | `gwFeedback` |

**Single-script rule:** On `super_ai_gateway_console.html`, every include passes `include_script=False`; the page loads `rmc_ai_json_api_card.js` once at the bottom (avoid duplicate deferred script tags).

---

## 5. External API manifest

`apps/api/api_v1_manifest.py` lists **integrator-facing** stable URLs only. Internal `/api/ai/*` console endpoints are **not** part of that manifest by design; use this registry for operators and engineers.
