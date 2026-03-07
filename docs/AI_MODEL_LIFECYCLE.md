# AI Model Lifecycle — Sovereign Stack

Procedures for regional model sync, hot-swap, LoRA adapters, and offline/sneakernet upgrades. See also [WORLD_ENGINE_SCALE_OPERATIONS.md](WORLD_ENGINE_SCALE_OPERATIONS.md) for regional sidecar deployment.

## Model Registry and sync

- **AIModelRegistry** (public schema) stores per-region, per–hardware-tier model IDs and optional LoRA paths. **RegionalAIConfig** holds the Ollama base URL and default/fallback model per region.
- **Sync command:** `python manage.py sync_regional_models [--cluster CLUSTER] [--dry-run]`
  - Reads AIModelRegistry for the given cluster (or all clusters if omitted).
  - For each active `model_id`, runs `ollama pull <model_id>` (via subprocess; optionally in background threads so the DB is not locked).
  - Target path for models is managed by the Ollama daemon (e.g. `/var/lib/ollama` or `OLLAMA_MODELS_PATH`); the command only triggers the pull.
  - Use `--dry-run` to list models that would be pulled.

## Hot-swap (no downtime)

- Operators can switch to a new model version without downtime:
  1. Run two Ollama instances: **A** (current) and **B** (new). Ensure B has the new model pulled (`sync_regional_models --cluster <region>` or manual `ollama pull`).
  2. Point the load balancer (or NGINX) in front of Ollama to **B** when B is healthy (e.g. `GET /api/tags` returns 200).
  3. Decommission **A** after traffic has moved.
- **OllamaInferenceService** and **RegionalAIConfig** use only the base URL (no hardcoded instance); changing the LB target is the only switch. Optional: set **preferred_model_id** (or default_model) in RegionalAIConfig so Super Admin can flip the default without touching the LB immediately.

## LoRA (country/region adapter)

- **AIModelRegistry** has `lora_adapter_path` (optional). At inference time, **OllamaInferenceService** can apply a small country/region adapter when configured so the model gets local clues without full reload.
- To add a LoRA: place the adapter file on the Ollama host (or a path reachable by the service), then set `lora_adapter_path` in the registry for that region/hardware_tier. See AI_MODEL_LIFECYCLE and service code for how the path is used (e.g. Modelfile with ADAPTER or pre-created per-country model_id).

## Offline and sneakernet

- **Regional mirror:** One hub per region downloads the model; other nodes sync via local network or physical drive from that hub.
- **Delta updates:** Use LoRA adapters for curriculum/tax changes; keep the base model static and ship only LoRA deltas.
- **Sneakernet:** Export the model as a Docker image or use `ollama create -f Modelfile` from a tarball. Step-by-step import on the target:
  1. Copy the tarball or image to the target.
  2. Load into Ollama (e.g. `ollama create -f Modelfile` or Docker load + run).
  3. Run `sync_regional_models --cluster <region>` or register the model_id in AIModelRegistry and pull locally.
- Link from [WORLD_ENGINE_SCALE_OPERATIONS.md](WORLD_ENGINE_SCALE_OPERATIONS.md) for full regional sidecar and LB setup.
