# Offline help appliance (RunMyCampus)

Lane-1 runbook for **category-defining** air-gapped / low-connectivity help (batch 1344).

## Profile

- Django monolith + SQLite or Postgres on LAN
- Optional Ollama on the same host for embeddings and SSE answers
- KB articles + `vector_embedding` JSON stored in DB (no Qdrant required at small scale)
- Service worker precaches help shell assets and top KB routes per role

## Operator checklist

1. Set `enable_ai_help_assistant` in tenant `SiteSettings.backend_feature_flags` (default **true**).
2. Run `python manage.py reindex_kb_help_embeddings` after content publish waves.
3. Run `python manage.py build_code_support_index` for staff-only code RAG.
4. Bump `CACHE_VERSION` in `static/js/service-worker.js` on each help wave deploy.
5. Schedule Celery beat `portal-reindex-kb-embeddings-weekly` when workers are available.

## Offline UX

- When AI is disabled or unreachable, the KB panel shows **Offline help mode** (`data-rmc-kb-ai-offline`).
- Users retain KB search, FAQ, and deflection (`api:support-deflection`) against cached embeddings.
- Platform offline queue (`platform_runtime.process_offline_queues_due`) replays support submissions when connectivity returns.

## Retention

`python manage.py purge_help_telemetry --dry-run` then `--apply` (omit dry-run) honors `help_telemetry_retention_days` (default 365).

## Honest boundary

Live Ollama at scale, pgvector flip, and hosted Playwright help crawls remain **Lane 2** operational proof.
