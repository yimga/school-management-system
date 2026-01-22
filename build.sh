#!/usr/bin/env bash
set -o errexit

echo "Removing old virtual environment..."
rm -rf .venv 2>/dev/null || true

# Aggressively clear all Python cache to ensure fresh deployment
echo "Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Create a fresh virtual environment to avoid PEP 668 restrictions
echo "Creating virtual environment..."
python3 -m venv .venv

# Define venv executables
VENV_PY=".venv/bin/python"
VENV_PIP=".venv/bin/pip"

# Clear pip cache within venv
echo "Clearing pip cache (venv)..."
$VENV_PY -m pip cache purge 2>/dev/null || true

# Install dependencies within venv
echo "Installing dependencies (venv)..."
$VENV_PY -m pip install --upgrade pip --no-cache-dir
$VENV_PIP install --no-cache-dir --force-reinstall -r requirements.txt

# Never run makemigrations in CI/production.
echo "Running migrations..."
$VENV_PY manage.py migrate --noinput
echo "Collecting static files..."
$VENV_PY manage.py collectstatic --noinput
