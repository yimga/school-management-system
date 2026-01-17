#!/usr/bin/env bash
set -o errexit

python manage.py collectstatic --noinput
python manage.py migrate

# Optional: seed demo data (useful for staging / first deploy)
# Enable by setting AUTO_SEED_DEMO=1 in your environment.
if [ "${AUTO_SEED_DEMO:-0}" = "1" ]; then
  python manage.py seed_demo --reset
fi
