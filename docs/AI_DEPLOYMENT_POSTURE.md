# AI deployment posture (canonical)

Single reference for how RunMyCampus routes **live AI**, **guided fallback**, and **offline school operations**. Execution checklist: `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` §11.4 batch **1370**.

## Three layers (do not conflate)

| Layer | Runs where | Needs internet to school server? | Technology |
| --- | --- | --- | --- |
| **School operations (offline mode)** | Teacher/staff browser (PWA + service worker) | Only to sync queued writes | Dexie + `/api/offline/delta/` — **not LLM** |
| **Live AI** | Django app server (Render or LAN hub) | Yes, for new AI answers | `services.ai_gateway` tier chain |
| **Guided fallback** | Django (rules + KB + topology) | Yes for first load; cached UI may show hints | `services.ai_guided_fallback` |

**Never** install Ollama on each teacher laptop. **Never** expect full AI on a device with zero connectivity to the tenant origin.

## Deployment profiles (`RMC_DEPLOYMENT_PROFILE`)

| Profile | Typical host | Default gateway tiers (when env set) |
| --- | --- | --- |
| `online` (default) | Render SaaS | `litellm` → `ollama` → `rules` if `LITELLM_PROXY_URL` set; else `ollama` → `rules` |
| `edge` | School LAN hub | `ollama` → `rules` |
| `hybrid` | Render + optional `RMC_HUB_BASE_URL` | `litellm` → `ollama` → `rules` when LiteLLM configured; else same as edge |

Implementation: `services/ai_deployment_posture.py` — merged into `services/ai_gateway._task_tiers()`.

Override per task only via Django `settings.AI_GATEWAY_TASK_TIERS` (dict), not env strings.

## Render SaaS (production default)

```bash
RMC_DEPLOYMENT_PROFILE=online
RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION=1
AI_GATEWAY_ENABLED=1
AI_ALLOW_RULES_FALLBACK=1
LITELLM_PROXY_URL=https://your-openai-compatible-endpoint/v1
LITELLM_API_KEY=...
LITELLM_MODEL=gpt-3.5-turbo
```

- **Do not** rely on Ollama inside a Render web dyno for primary inference.
- **Do** set LiteLLM to any OpenAI-compatible proxy (LiteLLM, Azure OpenAI, provider gateway).
- UI surfaces posture via AI Center, copilot health pill, `/api/ai/health/`.

Verify repo contracts: `python scripts/verify_render_online_ai_posture.py`

## LAN hub (edge)

See `docs/LOCAL_HUB_MODE.md` and `docs/OLLAMA_OPERATIONS_AND_UPDATES.md` for `ollama serve`, Modelfile, and `verify_ollama_live.py`.

## Health and UI contract

| Field | Meaning |
| --- | --- |
| `posture_mode` | `live_cloud` \| `live_local` \| `guided` \| `unavailable` |
| `posture_label` | Human badge text (AI Center + JS pill) |
| `gateway_tier_chain` | Ordered tiers for this profile |
| `has_live_provider` | Reachability probe succeeded (cloud or Ollama) |

Probes: `apps.portal.ai_provider.probe_ai_provider_reachable()` — LiteLLM `/v1/models` on `online`/`hybrid`, then Ollama.

## Related docs

- Connectivity + offline bundle: `docs/LOCAL_HUB_MODE.md`
- Ollama install/update (edge/on-prem): `docs/OLLAMA_OPERATIONS_AND_UPDATES.md`
- Operator quick start (Render + optional local Ollama dev): `docs/OPERATOR_OLLAMA_AND_RENDER.md`
