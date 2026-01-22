#!/usr/bin/env bash
set -o errexit

# NUCLEAR OPTION: Remove entire virtual environment to force fresh install
echo "Removing old virtual environment..."
rm -rf .venv 2>/dev/null || true

# Aggressively clear all Python cache to ensure fresh deployment
echo "Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Clear pip cache
echo "Clearing pip cache..."
python3 -m pip cache purge 2>/dev/null || true

# Force reinstall without cache
echo "Installing dependencies..."
python3 -m pip install --upgrade pip --no-cache-dir
python3 -m pip install -r requirements.txt --no-cache-dir --force-reinstall

# Never run makemigrations in CI/production.
python3 manage.py migrate --noinput
python3 manage.py collectstatic --noinput
