web: bash ./scripts/release/render_start_web.sh
worker: .venv/bin/celery -A config worker -l info --concurrency=${CELERY_WORKER_CONCURRENCY:-2}
beat: .venv/bin/celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
