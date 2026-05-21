#!/usr/bin/env bash
# Bootstrap a school LAN hub (edge profile). Run on the hub machine — not on Render.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export RMC_DEPLOYMENT_PROFILE="${RMC_DEPLOYMENT_PROFILE:-edge}"
export OLLAMA_AUTO_START="${OLLAMA_AUTO_START:-1}"
export OLLAMA_AUTO_DISCOVER="${OLLAMA_AUTO_DISCOVER:-1}"
export AI_ALLOW_RULES_FALLBACK="${AI_ALLOW_RULES_FALLBACK:-1}"

echo "==> RunMyCampus Local Hub (edge profile)"
echo "    RMC_DEPLOYMENT_PROFILE=$RMC_DEPLOYMENT_PROFILE"

if [[ ! -f .venv/bin/python ]]; then
  echo "Create .venv and install requirements first (see AGENTS.md)."
  exit 1
fi

.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py check

if [[ "${RMC_ENSURE_SUPERUSER:-1}" == "1" ]]; then
  .venv/bin/python manage.py ensure_superuser --no-input || true
fi

echo ""
echo "Start the app bound to LAN (example):"
echo "  .venv/bin/python manage.py runserver 0.0.0.0:8000"
echo ""
echo "On client devices, open http://<hub-ip>:8000/ and install the PWA."
echo "After creating a school, run:"
echo "  .venv/bin/python manage.py apply_offline_mode_bundle --school-id <uuid>"
echo ""
echo "Optional Ollama on this hub:"
echo "  ollama serve"
echo "  ollama create ai-center-master -f ai/Modelfile"
echo "  export OLLAMA_BASE_URL=http://127.0.0.1:11434"
echo ""
echo "See docs/LOCAL_HUB_MODE.md"
