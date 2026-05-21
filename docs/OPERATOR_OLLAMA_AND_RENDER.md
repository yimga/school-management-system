# Operator: AI on Render and LAN hubs

Canonical architecture: **`docs/AI_DEPLOYMENT_POSTURE.md`**.

## Render SaaS (default — `RMC_DEPLOYMENT_PROFILE=online`)

1. In Render Dashboard → Environment:

   ```bash
   RMC_DEPLOYMENT_PROFILE=online
   AI_GATEWAY_ENABLED=1
   AI_ALLOW_RULES_FALLBACK=1
   LITELLM_PROXY_URL=https://your-openai-compatible-endpoint/v1
   LITELLM_API_KEY=...
   LITELLM_MODEL=gpt-3.5-turbo
   RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION=1
   ```

2. Redeploy. Open **AI Center** on manager — health pill should show **Live — cloud AI** when the proxy is reachable.

3. Repo verifier (no secrets): `python scripts/verify_render_online_ai_posture.py`

4. **Offline schools:** `python manage.py apply_offline_mode_bundle --all-active` for existing tenants; new schools get the bundle at provision time.

**Do not** expect `ollama serve` on the Render web dyno for production inference.

## Local dev (optional Ollama on your PC)

For developer machines only:

```bash
ollama serve
ollama pull llama3
# .env
AI_GATEWAY_ENABLED=1
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3
python scripts/verify_ollama_live.py --invoke
```

With `RMC_DEPLOYMENT_PROFILE=online` and **no** `LITELLM_PROXY_URL`, the gateway still tries Ollama after cloud tier (usually unreachable on Render).

## LAN hub (`edge`)

1. `bash scripts/install_local_hub.sh` or manual install per `docs/LOCAL_HUB_MODE.md`
2. `RMC_DEPLOYMENT_PROFILE=edge` in hub `.env`
3. Optional: `ollama serve` + `docs/OLLAMA_OPERATIONS_AND_UPDATES.md`

## Render deploy parity (moderator)

When ready, provide (do not commit): `RENDER_API_KEY`, service ID, expected deploy SHA. Run recovery cert scripts per `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`.

## Recovery cert on Render shell

```bash
cd ~/project/src
python scripts/generate_v4_recovery_certification.py --runtime
python scripts/verify_render_online_ai_posture.py
python scripts/verify_online_edge_dual_mode.py
```

Ollama-on-Render is **not** the production path; expect cloud AI or guided mode unless you operate an edge hub.
