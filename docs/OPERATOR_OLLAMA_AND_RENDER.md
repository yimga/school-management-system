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

## Recovery cert on Render shell

`PARTIAL` means at least one **non-Ollama** verifier failed. Ollama-only failure yields
`READY — REPO SCOPE (OLLAMA LIVE PENDING)` instead.

```bash
cd ~/project/src
# After deploy includes commit 89efd95c+ (v5 gear-up lift):
python scripts/generate_v4_recovery_certification.py --runtime
# Prints repo_gaps + verifier tails on PARTIAL.

# Quick read of last run:
python -c "import json; d=json.load(open('docs/generated/ten_x_platform_certification.json')); print('gaps:', d.get('repo_gaps')); print('verdict:', d.get('verdict'))"

# Common fixes on Render:
git pull   # or redeploy latest main — need v5 scripts + var/* baselines + migration 0007
python scripts/generate_orchestrator_journey_manifest.py --write
python scripts/verify_stage_journey_coverage.py
python manage.py migrate --noinput   # if manage.py check fails on pending migrations
```

Set `RMC_RECOVERY_RUNTIME=1` (or `--runtime`) when `.git` is missing in the container.

## Current repo recovery status

- North Star: **75/75 DOMINANT**
- `audit_admin_gravity.py --strict`: **PASS**
- Prompt pack: **v5** — `ORCHESTRATOR_PROMPT_PACK_PASS` (227 checks)
- Ollama live: **not on Render web dyno** — expect `OLLAMA LIVE PENDING` unless sidecar Ollama is wired
