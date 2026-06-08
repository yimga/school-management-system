#!/usr/bin/env bash
set -o errexit

# Create a persistent virtual environment in the project
echo "Setting up virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# Aggressively clear all Python cache to ensure fresh deployment
echo "Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Clear pip cache
echo "Clearing pip cache..."
python3 -m pip cache purge 2>/dev/null || true

# Install dependencies into venv (no PIP_BREAK_SYSTEM_PACKAGES needed)
echo "Installing dependencies..."
python3 -m pip install --upgrade pip --no-cache-dir
python3 -m pip install -r requirements.txt --no-cache-dir

# World Footprint WebGL bundle (static/js/dist is gitignored — must build on deploy).
echo "Building world globe bundle..."
if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required to build static/js/dist/world-globe.* for the manager globe."
  exit 1
fi
npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund
npm run build:world-globe
python3 scripts/generate_globe_earth_night_texture.py

# Set Django settings module for production build
export DJANGO_SETTINGS_MODULE=config.settings

# Never run makemigrations in CI/production.
python3 manage.py collectstatic --noinput

# Render dashboard often overrides startCommand to bare `.venv/bin/gunicorn ...`.
# Wrap the venv entrypoint so every deploy still loads config/gunicorn.conf.py
# (120s timeout, gthread workers, PORT bind) even when the dashboard omits -c.
echo "Installing Gunicorn wrapper (forces config/gunicorn.conf.py)..."
if [[ -x .venv/bin/gunicorn && ! -x .venv/bin/gunicorn.real ]]; then
  mv .venv/bin/gunicorn .venv/bin/gunicorn.real
fi
if [[ -x .venv/bin/gunicorn.real ]]; then
  cat > .venv/bin/gunicorn <<'GUNWRAP'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/release/sanitize_gunicorn_env.sh
source "$ROOT/scripts/release/sanitize_gunicorn_env.sh"
export RMC_WEB_START_SCRIPT="${RMC_WEB_START_SCRIPT:-gunicorn_conf_wrapper}"
exec "$(dirname "$0")/gunicorn.real" -c config/gunicorn.conf.py "$@"
GUNWRAP
  chmod +x .venv/bin/gunicorn
fi

echo "Build complete - venv is ready at .venv/"
