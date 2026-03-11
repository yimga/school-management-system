# Tiered AI and Ollama (north-star stack)

RunMyCampus uses a **governed AI operating layer**: LiteLLM as gateway/router, Ollama for private/lightweight tasks, vLLM for structured self-hosted inference, optional premium via LiteLLM. **Implementation and phase tracking live in the single RunMyCampus Open-Source AI Adoption Blueprint (plan); this doc does not duplicate scope or deliverables.**

## Stack

| Layer | Role |
|-------|------|
| **LiteLLM** | Request routing, fallback, project budgets, provider abstraction, central logging. |
| **Ollama** | Local/private inference; config explanation; setup recommendations; document tagging; workflow drafts (light); classification. |
| **vLLM** | OpenAI-compatible API; structured JSON (workflow, migration, policy); higher-throughput self-hosted. |
| **Open WebUI** | Internal ops only: prompt testing, model comparison, admin experimentation. Not customer-facing. |
| **Embeddings** | Pluggable (Ollama or OpenAI-compatible); semantic search over policies, packs, docs, config. |

## When to use which

- **Ollama:** Low-cost summaries, classification, setup suggestions, config/feature explanation, document tagging, light drafting.
- **vLLM:** Structured JSON outputs, workflow generation, migration mapping, policy diff objects, dashboard/report recommendations.
- **LiteLLM:** Routing, fallback, budgets, premium models for complex reasoning when policy allows.
- **Premium hosted:** Only for highest-complexity tasks when cost is justified and data tier allows.

## Risks

- **Quality drift:** Open-source models vary; validate structured outputs and use fallbacks.
- **GPU/infra cost:** Self-hosted is not free; plan capacity and ops.
- **Security/data governance:** No PII to premium unless tenant opts in; data-tier checks in gateway; audit every invoke.
- **Product scope:** Add AI where it removes labor and improves outcomes, not where it only looks modern.

## Entry points and blueprint

- All product AI: `services.ai_gateway.invoke(...)` or `generate_ai_response` (which uses the gateway for general_chat).
- Productized endpoints: `/api/ai/setup-assistant/`, `/api/ai/workflow-draft/`, `/api/ai/policy-explain/`, `/api/ai/document-classify/`, `/api/ai/semantic-search/`, `/api/ai/migration-suggest/`.
- **Single source of truth for scope and phases:** RunMyCampus Open-Source AI Adoption Blueprint (plan). Do not track AI adoption deliverables in other files.

## Deploying Open WebUI (internal ops)

Open WebUI is for **internal use only**: prompt testing, model comparison, admin experimentation. Not customer-facing.

1. **Deploy:** Use Docker or install alongside Ollama. Example (Docker):
   ```bash
   docker run -d -p 3000:8080 --add-host=host.docker.internal:host-gateway \
     -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
     --name open-webui ghcr.io/open-webui/open-webui:main
   ```
2. **Environment:** Set `OLLAMA_BASE_URL` to your Ollama instance (e.g. `http://ollama:11434` in Docker Compose). Optional: `OPENAI_API_KEY` if using OpenAI-compatible proxy.
3. **Access:** Restrict to internal network or VPN. Do not expose to the public internet.
4. **Control Plane link:** In the manager/backend dashboard, add an optional link (e.g. "AI Ops (Open WebUI)") that points to the internal Open WebUI URL (configurable via `OPEN_WEBUI_URL` or similar). When unset, hide the link.

See [Open WebUI docs](https://docs.openwebui.com/) for auth and multi-user setup.

## References

- [ai_orchestration.md](ai_orchestration.md)
- [RunMyCampus_AI_Architecture_and_Model_Improvement.md](../RunMyCampus_AI_Architecture_and_Model_Improvement.md)
- `services/ai_gateway.py`, `services/ai_schemas.py`, `services/embeddings.py`
