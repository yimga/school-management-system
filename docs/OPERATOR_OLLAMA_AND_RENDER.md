# Operator: Live Ollama + Render (v4 recovery)

## Ollama (permission granted — run on operator PC)

1. Install (Windows): run `powershell -ExecutionPolicy Bypass -File scripts/install_ollama_windows.ps1`  
   Or download from https://ollama.com/download
2. Start daemon: `ollama serve` (keep terminal open) or use system tray app
3. Pull base model: `ollama pull llama3.1:8b`
4. Create governed model: `ollama create ai-center-master -f ai/Modelfile`
5. Verify:
   ```bash
   set AI_GATEWAY_ENABLED=1
   set OLLAMA_ENDPOINT=http://127.0.0.1:11434
   set OLLAMA_MODEL=ai-center-master
   python scripts/verify_ollama_live.py --strict --invoke
   python scripts/generate_ollama_live_proof.py
   ```

## Render LIVE (provide when ready)

Send moderator (do not commit secrets):

- `RENDER_API_KEY`
- Service ID or service name for `manager.runmycampus.com`
- Latest deploy SHA you expect parity against

Moderator runs `scripts/verify_render_live_parity.py` (if present) or `render_predeploy.sh` log capture.

## Current repo recovery status

- North Star: **75/75 DOMINANT**
- `audit_admin_gravity.py --strict`: **PASS**
- Prompt pack: **v4** — `ORCHESTRATOR_PROMPT_PACK_PASS` (164 checks)
- Ollama live: **pending operator install** (rules fallback active until daemon up)
