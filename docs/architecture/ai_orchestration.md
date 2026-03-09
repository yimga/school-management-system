# AI orchestration (internal-first)

All LLM usage goes through a single orchestration layer. Providers (Ollama, Gemini, future OpenAI/Azure) are swappable adapters. No view or service must call a provider SDK directly.

## Single entry points

| Use case | Entry point | Notes |
|----------|-------------|--------|
| Sync single-turn (copilot, narrative) | `apps.portal.ai_provider.generate_ai_response(prompt, user_query=..., metadata=...)` | Returns (text, meta); policy guard (prompt injection) applied. |
| Async / bulk (syllabus, report remarks, support suggestion) | `apps.portal.tasks.generate_ai_response_async` + poll `ai:async_result:{task_id}` | Uses `OllamaInferenceService.infer` and cache. |
| WebSocket chat | `apps.api.consumers` | Calls `OllamaInferenceService.infer` (sync_to_async). |
| Workflow / country suggestions | `apps.portal.ai_provider.get_workflow_setup_suggestions` / `get_country_dossier_summary` | Delegates to OllamaInferenceService with country/school. |

## Provider order and adapters

- **Preference:** `AI_PROVIDER_PREFERENCE` (e.g. `ollama,gemini,rules`). Default: `ollama`, then `rules` (no Gemini unless tenant opts in).
- **Ollama:** Implemented in `services.inference.OllamaInferenceService` (region, dossier, cache, fallback model, PII stripping). Called by `ai_provider._call_ollama`.
- **Gemini:** Implemented in `apps.portal.ai_provider._call_gemini` (REST to Google API). No SDK in app code; key from env/settings.
- **Rules fallback:** When no live provider returns, `_rules_fallback` returns a fixed message. No external call.

## Prompts, RAG, audit

- **Prompts:** Owned in code (ai_provider, inference). No tenant identifiers or internal IDs are appended to prompts sent to external providers (`metadata` is not added to prompt text).
- **RAG:** When RAG is used, source data must come from internal APIs or DB; no raw PII in context sent to external LLMs. `strip_pii_for_inference` in services.inference used for Ollama path.
- **Audit:** Logging and `metadata` returned from `generate_ai_response` are for observability only; extend to structured audit (e.g. event or log line per request) as needed.
- **Evaluation:** Add evaluation harness (e.g. golden set, safety checks) behind the same entry points; no separate provider calls for evals.

## Audit result (no direct provider usage outside facade)

- **portal/views_ai_copilot:** Uses `generate_ai_response` only.
- **communication/narrative_feedback:** Uses `generate_ai_response` only.
- **portal/tasks:** Uses `OllamaInferenceService.infer` (internal); async path does not call Gemini directly.
- **api/consumers:** Uses `OllamaInferenceService.infer` only.
- **portal/ai_provider:** Contains the only Gemini call (`_call_gemini`) and Ollama delegation (`_call_ollama` → OllamaInferenceService).

No `openai`, `anthropic`, or `google.generativeai` SDK imports in app code; Gemini is invoked via REST in ai_provider.

## References

- `apps/portal/ai_provider.py`
- `services/inference.py`
- `docs/architecture/SERVICE_CATALOG.md` (Zone B AI adapter)
