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

# Never run makemigrations in CI/production.
python3 manage.py migrate --noinput
python3 manage.py collectstatic --noinput

echo "Build complete - venv is ready at .venv/"
