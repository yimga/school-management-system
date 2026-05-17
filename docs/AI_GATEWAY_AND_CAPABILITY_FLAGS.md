# AI Gateway and Capability Flags

**Purpose:** §2.3 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). All AI usage is backend-only; UI receives capability flags, not secrets. Nothing deferred.

**Status:** DONE — backend gateway is the single path; capability flags exposed to UI.

---

## 1. Backend-only AI gateway

- **Single entry point:** `services.ai_gateway.invoke(task_type, prompt, ...)`. All AI tasks (config explain, setup recommend, workflow draft, policy explain, doc classify, migration mapping, admin copilot, support suggest, narrative, general chat) go through this gateway.
- **No browser calls to providers.** Portal and admin call backend views that use `services.ai_gateway.invoke()` or `apps.portal.ai_provider.generate_ai_response()` (which delegates to the gateway). No provider API keys in templates or client JS (`lint_secret_exposure.py` enforces common secret names server-side).
- **Audit:** `services.ai_gateway` logs invokes and records feedback; audit trail via `ai_gateway_invoke` and related events.

---

## 2. Capability flags exposed to UI

- **Status endpoint:** `apps.portal.ai_provider.get_public_ai_provider_status()` returns a dict safe for templates: provider name, availability, model info. No API keys or secrets.
- **Context processor:** `apps.siteconfig.context_processors.ai_copilot_settings()` exposes e.g. `AI_PROVIDER_NAME`, `AI_AVAILABLE` (or equivalent) to templates. Verified by `apps.siteconfig.tests.test_ai_copilot_context`: no provider secret names (e.g. `OPENAI_API_KEY`) in context or rendered HTML.
- **Lint:** `scripts/lint_secret_exposure.py` fails if provider secret names appear in client-rendered code or context processors.

---

## 3. Permission and audit

- AI views are behind auth; rate limiting and feedback recording are in place. Permission model by role/task/tenant and retention/redaction rules can be extended; current state: backend-only, auditable, no secret leakage.

---

## 4. Guided assistant degraded mode (batch 1247)

- Rules-tier and final fallback paths use `_rules_invoke_result()` so `guided_assistant` never returns a bare string to views.
- Operator surfaces: `/siteconfig/ai-center/`, `/super/ai-gateway-console/`, and embedded `ai_guided_assistant_card` CTAs.
- Setup: see [OLLAMA_OPERATIONS_AND_UPDATES.md](OLLAMA_OPERATIONS_AND_UPDATES.md).

## 5. Completion gate (§2.3)

- [x] No provider secret reaches the browser (lint + tests).
- [x] All AI calls flow through backend gateway (services.ai_gateway / portal.ai_provider → gateway).
- [x] Capability flags exposed to UI; secrets never in template/JS.
- [x] Guided assistants return non-empty structured answers in rules-only mode (batch 1247).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.3.*
