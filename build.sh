#!/usr/bin/env bash
set -o errexit

# Aggressively clear all Python cache to ensure fresh deployment
echo "Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Clear pip cache
echo "Clearing pip cache..."
python -m pip cache purge 2>/dev/null || true

# Force reinstall without cache
echo "Installing dependencies..."
python -m pip install --upgrade pip --no-cache-dir
pip install -r requirements.txt --no-cache-dir --force-reinstall

# Never run makemigrations in CI/production.
python manage.py migrate --noinput
python manage.py collectstatic --noinput
