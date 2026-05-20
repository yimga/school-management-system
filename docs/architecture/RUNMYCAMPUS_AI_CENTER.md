# RunMyCampus AI Center architecture

**Status:** API CENTER + AI CENTER READY — REPO SCOPE (batch 1328, 2026-05-20)  
**Engine room:** `services/ai/` (gateway, knowledge, tenant_isolation)  
**AI Center layer:** `services/ai_center/` (indexing, query, Ollama client, KB drafts, friction)  
**Verifier:** `python scripts/verify_ai_engine_room.py`  
**Proof bundle:** `python scripts/generate_stage9_api_ai_proof_bundle.py`  
**Governed model:** [`ai/Modelfile`](../../ai/Modelfile)

## Purpose

The AI Center is not a generic chatbot. It is a permission-filtered, evidence-backed layer for:

- operator technical guidance and runbooks (`/super/ai-center/`)
- tenant-safe in-app help (`/school/help/ai/`, feature-flagged)
- KB/FAQ draft generation (human review before tenant publish)
- support deflection using indexed route/schema/proof metadata
- friction analysis from aggregated, non-PII signals

## Response contract

| Condition | Exact response prefix |
|-----------|----------------------|
| Feature absent from app ledger | `FEATURE CODESPACE DISCONNECT:` |
| Detail missing from indexed KB | `DATA DEFAULTER:` |

## Components

| Component | Path | Status |
|-----------|------|--------|
| Modelfile | `ai/Modelfile` | shipped |
| Platform inventory | `scripts/generate_ai_center_inventory.py` | shipped |
| Indexing contract | `services/ai_center/indexing.py` | shipped |
| Query service | `services/ai_center/query_service.py` | shipped |
| Ollama client | `services/ai_center/ollama_client.py` | shipped |
| Super UI | `apps/apicenter/views_ai_center_super.py` | shipped |
| Tenant help | `apps/siteconfig/views_school_help_ai.py` | shipped |
| API contracts | `docs/architecture/RUNMYCAMPUS_AI_CENTER_API_CONTRACTS.md` | shipped |

## Live readiness

**Live Ollama inference** remains **EXTERNAL** until `python scripts/verify_ollama_live.py` passes on the operator host. RAG freshness follows the last `generate_ai_center_inventory.py --write` / index build.
