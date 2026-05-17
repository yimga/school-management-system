# AI surfaces FAQ — RunMyCampus

Quick reference for operators and engineers: which AI UI to use, and what each layer does.

## Which surface should I use?

| I want to… | Use | URL (typical) |
|------------|-----|----------------|
| Ask a governed assistant a question in plain language | **AI Center** | `/siteconfig/ai-center/` (tenant or manager) |
| Debug a raw `/api/ai/*` JSON contract as super-admin | **AI gateway console** | `/super/ai-gateway-console/` (manager only) |
| Govern OAuth clients, webhooks, and integration keys | **API Center** | `/api-center/` (manager; **not** LLM chat) |
| Change models, prompts, or Ollama host settings | **AI model hub** / operator setup | Control plane → AI configuration |

## Layer stack (bottom to top)

1. **`services/ai_gateway.py`** — Single orchestration entry for all LLM calls (Ollama + rules fallback). App code must use `services.ai_helpers`, not import the gateway directly.
2. **`/api/ai/*`** — REST endpoints per assistant task (`guided_assistant` JSON schema, setup assistant, etc.). RBAC + school scope enforced in `apps/portal/views_ai_gateway.py`.
3. **AI Center** — One conversational shell listing every assistant from `apps/siteconfig/ai_assistants.py`. Shared JS: `static/js/rmc_ai_guided_assistant.js`.
4. **AI gateway console** — Super-admin test bench with JSON API cards (`templates/components/ai_json_api_card.html`). Same provider health as AI Center; use for contract debugging, not day-to-day school work.
5. **API Center** — Integration governance (OAuth, audit, developer platform stubs). No chat UI.

## Rules-only vs live (Ollama)

- **Live:** `OLLAMA_BASE_URL` + model configured → model returns validated `guided_assistant` JSON when possible.
- **Rules / degraded:** No Ollama → `services/ai_guided_fallback.build_guided_fallback` still returns a **non-empty** `guided.summary` (RAG snippets + domain hints + “connect Ollama” caution). `meta.degraded` / `meta.fallback` are set.

See [OLLAMA_OPERATIONS_AND_UPDATES.md](OLLAMA_OPERATIONS_AND_UPDATES.md) and [AI_DOMAIN_ASSISTANT_REGISTRY.md](AI_DOMAIN_ASSISTANT_REGISTRY.md).

## Related docs

- [AI_CENTER_AND_GAP_CLOSURE_2026_05_16.md](AI_CENTER_AND_GAP_CLOSURE_2026_05_16.md) — canonical AI Center implementation
- [AI_GATEWAY_AND_CAPABILITY_FLAGS.md](AI_GATEWAY_AND_CAPABILITY_FLAGS.md) — capability flags and degraded mode
- [apicenter_integration_governance.md](apicenter_integration_governance.md) — API Center (integrations, not LLM)
