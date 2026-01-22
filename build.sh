#!/usr/bin/env bash
set -o errexit

# Clear Python cache to ensure fresh code deployment
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

python -m pip install --upgrade pip
pip install -r requirements.txt

# Never run makemigrations in CI/production.
python manage.py migrate --noinput
python manage.py collectstatic --noinput
