#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
pip install -r requirements.txt

# Never run makemigrations in CI/production.
python manage.py migrate --noinput
if [[ "${SEED_DEMO}" == "1" ]]; then
  python manage.py seed_demo --reset
fi
python manage.py collectstatic --noinput
