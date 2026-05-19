# Ollama — operations, updates, and patching

RunMyCampus **in-product chat** (`general_chat` / copilot / WebSocket) uses **Ollama** (self-hosted) and **rules** fallback only. This document is the operator workflow for keeping that stack current and safe.

## Practical posture (offline-first + live Ollama)

| Layer | What to enable | What it does |
| --- | --- | --- |
| **School operations** | Tenant `enable_offline_mode` (feature control) | Teachers queue attendance, grades, payments, notes on device; sync when online. **Not AI.** |
| **Live AI** | Ollama on the **same host as Django** (or a LAN URL the server can reach) | AI Center, copilot, guided assistants, semantic search use natural-language answers. |
| **Safety net** | `AI_ALLOW_RULES_FALLBACK=1` (default) | When Ollama is down, structured **rules** answers — no 500s. |

**Do not expect** full AI on a teacher phone with zero connectivity. That would require a future slice (on-device model or queued AI questions).

### Five-minute operator setup

On the app server (Lane 2 — not committed to git):

```bash
ollama serve
ollama pull llama3   # or your pinned OLLAMA_MODEL
```

Copy into `.env` / host environment (see `.env.example`):

```bash
AI_GATEWAY_ENABLED=1
AI_ALLOW_RULES_FALLBACK=1
OLLAMA_ENDPOINT=http://localhost:11434/api/generate
OLLAMA_MODEL=llama3
```

Verify from the repo:

```bash
python scripts/verify_ollama_live.py --invoke
```

**Acceptance:** AI Center shows live answers when Ollama is up; with Ollama stopped, AI Center still returns grounded rules responses. Offline capture continues independently.

### Functional proof (not mocked)

Unit tests under `apps/portal/tests/test_ai_gateway.py` mock `_call_ollama` for speed. **Live** proof uses real HTTP to Ollama:

| Check | Command |
| --- | --- |
| Operator smoke | `python scripts/verify_ollama_live.py --strict --invoke` |
| Gateway + inference (no mocks) | `RMC_AI_REQUIRE_LIVE=1 python manage.py test --tag=ai_live_ollama -v 2` |
| CI | GitHub Actions workflow `ai-live-ollama.yml` (Ollama service + `llama3.2:1b`) |

Live tests **fail** (not skip) when `RMC_AI_REQUIRE_LIVE=1` and Ollama is down. They assert `meta.tier == "ollama"` and non-empty model text — not rules fallback.

## What you configure

| Variable | Role |
|----------|------|
| `OLLAMA_ENDPOINT` | Base URL for Ollama’s generate API (default in code: `http://localhost:11434/api/generate`). |
| `OLLAMA_MODEL` | Tag pulled in Ollama (default in code: `llama3`). |
| `AI_GATEWAY_ENABLED` | Default `1` — keep on so all AI goes through `services.ai_gateway`. |
| `AI_ENGINE_ROOM_SUPPORT` | Default `1` — zero-fluff first-line support on `POST /api/ai/support-assistant/` (`services/ai/`). |
| `AI_ENGINE_ROOM_TIMEOUT_SECONDS` | Ollama latency cap for support assistant (default `15`). |
| `AI_ENGINE_ROOM_MAX_INPUT_TOKENS` | Prompt budget for RAG + context (default `6000`). |
| `AI_PROVIDER_PREFERENCE` | Default `ollama,rules`. Legacy token `gemini` is **ignored**. |

### First-line support engine room

When `AI_ENGINE_ROOM_SUPPORT=1`, support queries use **RAG** (tenant KB/FAQ + `index_ai_knowledge` embeddings), **live URL topology** (`DynamicSystemInspector`), **tenant isolation**, and the **master persona** in `services/ai/prompts.py` (sections: Direct Answer, Execution Path, Action Steps, System Bound). No docs → escalation string with `escalation_required: true` (model skipped).

```bash
python scripts/verify_ai_engine_room.py
python manage.py index_ai_knowledge --scope help
python manage.py engine_room_sync_ollama
```

API body: `{"query":"…","active_url":"/current/path","history":"optional prior turns"}`.

### Universal command bar (⌘K)

The global palette (`static/js/rmc-command-palette.js`) calls `POST /api/ai/command-bar/` with topology matches from `services/ai/topology_map.py` (`SYSTEM_TOPOLOGY_MAP`). Locked rows show missing permission tokens; **Ask AI** deep-links to AI Center `?assistant=first_line_support&q=…`. React mirror: `src/components/shared/navigation/CommandBar.tsx`.

**Portal header:** `data-rmc-page-help` opens AI Center with `first_line_support` and the current `active_url`.

### Product assistants (tiers 2–4)

| Endpoint | Purpose |
| --- | --- |
| `POST /api/ai/smart-settings/` | Natural-language SiteSettings / feature-flag guidance (engine room) |
| `POST /api/ai/import-error-resolver/` | CSV validation errors → fix steps |
| `POST /api/ai/guardrail-report/` | Permission-aware report library recommendations |
| `POST /api/ai/guided-tour/` | Onboarding tour steps from topology + engine room narrative |

All are registered in AI Center as assistants (`smart_settings`, `import_resolver`, `report_generator`, `guided_tour`).

### Production beats (recommended)

| Variable | Schedule |
| --- | --- |
| `ENABLE_AI_KNOWLEDGE_INDEX_BEAT=1` | Daily RAG re-index (`index_ai_knowledge`) |
| `ENABLE_OLLAMA_MODEL_SYNC_BEAT=1` | Weekly `sync_ollama_models` + `engine_room_sync_ollama --no-pull` smoke |

Gate: `python scripts/verify_ai_engine_room.py` (also in `release_readiness_check.sh` §4b and `verify_phases_3_11_gates.py`).

Optional: `AI_GATEWAY_TASK_TIERS` overrides per-task backends; do **not** add `gemini` (removed from product).

### Open-source posture (product defaults)

- **Required inference for in-product chat:** self-hosted **Ollama** (+ deterministic **rules** fallback). Do not route required school workflows through closed SaaS APIs unless you have an explicit compliance exception.
- **Embeddings:** prefer `AI_EMBEDDING_BACKEND=ollama` and open models (e.g. `nomic-embed-text`). `openai_compatible` is optional for self-hosted OpenAI-compatible endpoints only.
- **Optional tiers** (`vllm`, `litellm` in `AI_GATEWAY_TASK_TIERS`): use **self-hosted** endpoints you control; avoid sending regulated payloads to third-party clouds without review.
- **Scheduled RAG re-indexing** (embedding store; typically **Ollama** embeddings when `AI_EMBEDDING_BACKEND=ollama`): opt-in Celery beat **`ENABLE_AI_KNOWLEDGE_INDEX_BEAT`** and task **`siteconfig.index_ai_knowledge_beat`** — see [architecture/ai_orchestration.md](architecture/ai_orchestration.md).
- **AI quality scorecards:** opt-in beat **`ENABLE_AI_QUALITY_SCORECARD_BEAT`** runs `aggregate_ai_metrics` and `ai_quality_scorecard` weekly for task-level acceptance/manual-correction/schema-fail rates.

## Automated model pulls (guarded)

The management command **`sync_ollama_models`** runs `ollama pull` for:

- `OLLAMA_MODEL` (chat),
- `AI_EMBEDDING_OLLAMA_MODEL` when `AI_EMBEDDING_BACKEND` is `ollama` (default),
- comma-separated `OLLAMA_SYNC_EXTRA_MODELS`,
- and, if enabled, active rows in **`AIModelRegistry`** (`--include-registry` or `OLLAMA_SYNC_INCLUDE_REGISTRY=1`).

Model names are **allowlisted** (alphanumeric plus safe punctuation for Ollama library IDs); anything else is skipped. The subprocess uses a **fixed argv** (no shell), with **`OLLAMA_PULL_TIMEOUT_SECONDS`** (default 3600, clamped 60–86400 in settings).

**Manual:** `python manage.py sync_ollama_models --dry-run` then without `--dry-run`.

**Celery Beat (opt-in):** set `ENABLE_OLLAMA_MODEL_SYNC_BEAT=1` on the environment that runs **both** beat and a worker **on a host that has the Ollama CLI** (same machine as Ollama, or your ops pattern). Schedule: **weekly** (604800s). Registry inclusion follows `OLLAMA_SYNC_INCLUDE_REGISTRY`.

| Variable | Role |
|----------|------|
| `ENABLE_OLLAMA_MODEL_SYNC_BEAT` | `1` / `true` / `yes` adds the weekly beat entry. |
| `OLLAMA_CLI_PATH` | Path to `ollama` binary (default `ollama`). |
| `OLLAMA_PULL_TIMEOUT_SECONDS` | Per-pull timeout (seconds). |
| `OLLAMA_SYNC_EXTRA_MODELS` | Extra models to pull, comma-separated. |
| `OLLAMA_SYNC_INCLUDE_REGISTRY` | If `1`, include `AIModelRegistry` active `model_id` values. |

**Container image digest:** workflow [ollama-image-digest-weekly.yml](../.github/workflows/ollama-image-digest-weekly.yml) logs `ollama/ollama:latest` **RepoDigest** weekly for operators who pin images.

## Keeping Ollama updated

1. **Ollama server**
   - Follow [Ollama release notes](https://github.com/ollama/ollama/releases) for your OS/package manager.
   - In production: pin a **known-good** Ollama version in your image or package manifest; upgrade on a **schedule** (e.g. monthly) after reading release notes.

2. **Model weights**
   - `ollama pull <OLLAMA_MODEL>` after you change `OLLAMA_MODEL` or when upstream publishes security/critical fixes for that tag.
   - Prefer **immutable tags** (e.g. manifest digest or explicit version) in serious deployments; avoid floating `latest` for production without a rollback plan.

3. **RunMyCampus app**
   - This repo controls **routing and prompts**, not Ollama binaries. Ship app updates via your normal **CI + `pre_deploy_gate.sh`** process.

## Verification

- Health: from the app host, `curl` your `OLLAMA_ENDPOINT` or use Ollama’s own health patterns; confirm copilot returns model text when Ollama is up.
- Degraded: stop Ollama briefly — UI should fall back to **rules** (if `AI_ALLOW_RULES_FALLBACK` is true), not 500.
- Code policy: there is **no** `GEMINI_API_KEY` or `_call_gemini` in `apps/` / `services/` for chat; optional `rg -i "generativelanguage\\.googleapis"` should find no app references.

## Security notes

- Do **not** expose Ollama to the public internet without authentication; bind to internal network or use your platform’s API layer only.
- Chat prompts may contain sensitive school context; keeping inference **on-prem** (Ollama) aligns with the internal-first data tier in `docs/architecture/ai_orchestration.md`.

## Related docs

- [architecture/ai_orchestration.md](architecture/ai_orchestration.md) — gateway, tiers, PII / premium rules.
- [AI_GATEWAY_AND_CAPABILITY_FLAGS.md](AI_GATEWAY_AND_CAPABILITY_FLAGS.md) — capability flags and template safety.
