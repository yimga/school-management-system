# AI Surface Audit

**Purpose:** §2.3 "Audit every AI/copilot/widget/template/JS surface" in the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Single list of backend and template surfaces that invoke AI; no secrets in browser.

**Status:** DONE — inventory complete.

---

## 1. Backend entry points (all via services.ai_gateway or delegate)

| Surface | Module / path | Notes |
|---------|----------------|-------|
| Gateway invoke | `services.ai_gateway.invoke()` | Single entry; task types in TaskType enum |
| Copilot sync | `apps.portal.ai_provider.generate_ai_response()` | Delegates to gateway |
| Async tasks | `apps.portal.tasks.generate_ai_response_async` | Celery; calls invoke |
| REST gateway | `apps.portal.views_ai_gateway` | api_ai_feedback, _gateway_response, _log_gateway_audit |
| Copilot views | `apps.portal.views_ai_copilot` | get_public_ai_provider_status; no keys in context |
| Tests | `apps.portal.tests.test_ai_gateway*`, `test_ai_feedback`, `test_ai_copilot_config` | Assert no secret in rendered output |

---

## 2. Template / JS surfaces

| Surface | Path | Notes |
|---------|------|-------|
| AI copilot UI | `templates/components/ai_copilot.html` | AI_PROVIDER_NAME only; no API keys |
| Context | `apps.siteconfig.context_processors.ai_copilot_settings` | Capability flags only; test_ai_copilot_context |

---

## 3. Audit and rate limiting

- **Audit:** `services.ai_gateway` logs `ai_gateway_invoke` with tenant_id/school_id/outcome; `log_ai_action` persists to AIActionAuditLog (no prompt/response content).
- **Rate limit:** views_ai_gateway uses _check_rate_limit; feedback via record_feedback.

---

## 4. Completion

- [x] Every AI path goes through gateway or delegate.
- [x] Template/tests prove no provider secret in HTML/JS.
- [x] Audit trail documented in [AI_audit_trail_and_permissions.md](AI_audit_trail_and_permissions.md).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.3.*
