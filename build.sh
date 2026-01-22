#!/usr/bin/env bash
set -o errexit

echo "Removing old virtual environment..."
rm -rf .venv 2>/dev/null || true

# Aggressively clear all Python cache to ensure fresh deployment
echo "Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Render uses an externally managed Python environment (PEP 668)
# Use break-system-packages to allow installation during build.
export PIP_BREAK_SYSTEM_PACKAGES=1

echo "Clearing pip cache..."
python3 -m pip cache purge 2>/dev/null || true

echo "Installing dependencies..."
python3 -m pip install --upgrade pip --no-cache-dir
python3 -m pip install --no-cache-dir --force-reinstall -r requirements.txt

# Never run makemigrations in CI/production.
echo "Running migrations..."
python3 manage.py migrate --noinput
echo "Collecting static files..."
python3 manage.py collectstatic --noinput
