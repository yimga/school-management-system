# Degradation and load testing

1. **Celery:** Stop workers; confirm user-facing actions queue tasks and show "processing" without 500.
2. **Redis:** Unset `REDIS_URL`; confirm cache miss fallback and session behavior per settings.
3. **OpenSearch:** Point to dead host; confirm search returns graceful empty/degraded (see `search_read_layer` tests).
4. **DB connection pool:** Simulate saturation; confirm 503 or queue message, not raw traceback to client.

Run quarterly in staging; record results in release notes.
