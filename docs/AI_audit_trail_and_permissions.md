# AI Audit Trail and Permissions

**Purpose:** §2.3 "Add AI usage audit trail" and "Add AI permission model by role/task/tenant" in the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

**Status:** **MET (repo baseline)** — `log_ai_action`, gateway + copilot surfaces, `get_ai_permission_for_user`; richer policy matrices and third-party review = §11.4.

---

## 1. Audit trail (implemented)

- **Structured log:** `services.ai_gateway._record_gateway_metric` / invoke path logs `ai_gateway_invoke` with task_type, tier, model, latency_ms, tenant_id, school_id, outcome. **No prompt/response content** (tenant-safe).
- **Persistence:** `apps.platform_runtime.helpers.log_ai_action` called with `action_type=ai_gateway:{task_type}`, payload tier/model/latency/outcome/school_id only.
- **Metrics:** AI gateway metrics model (siteconfig migration 0149/0152) for review/compliance fields.
- **Feedback:** `record_feedback` and api_ai_feedback in views_ai_gateway.

---

## 2. Rotate potentially exposed keys

- **Ops doc:** If keys were ever exposed historically, rotate at provider (Gemini, etc.). Repo hardening prevents re-exposure; `lint_secret_exposure.py` in pre_deploy_gate.

---

## 3. Retention / redaction

- **Policy:** Do not store raw prompts/responses in logs; gateway intentionally omits content. If storing prompts/responses for a feature, add retention/redaction policy and encrypt at rest per security policy.

---

## 4. Permission model

| Layer | Mechanism |
|-------|-----------|
| Entry | Auth required on views_ai_gateway and ai_copilot endpoints |
| Task | `services.ai_permissions.get_ai_permission_for_user(user, task_type, school)` — staff-only for admin_copilot, config_explain, migration_*, policy_explain; extend with plan/entitlement |
| Rate | _check_tenant_quota_limit, rate_limit in api |
| Enforce | Call `get_ai_permission_for_user` before `invoke()` in views; gateway can add optional check inside invoke for consistency |

---

## 5. Completion gate (§2.3)

- [x] No provider secret reaches browser (lint + tests).
- [x] All AI calls flow through backend gateway.
- [x] AI actions auditable (log + log_ai_action + metrics).
- [x] AI permission helper: `services.ai_permissions.get_ai_permission_for_user(user, task_type, school)`; staff-only tasks defined; call before invoke in views (ongoing wiring).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.3.*
