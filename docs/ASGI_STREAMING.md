# ASGI streaming (async SSE) — branch `asgi-streaming`

## Why
Long-lived SSE streams each pin one gthread worker thread for their lifetime.
The SSE concurrency cap (`services/sse_wsgi_limits.py`) prevents that from
starving `/health/`, but it does so by *rejecting* streams past capacity. Under
**ASGI**, an open SSE stream is a **coroutine**, not a pinned thread — so a
single worker can hold many concurrent streams cheaply and `/health/` is never
starved. This branch makes the two SSE views async and adds an opt-in ASGI
server mode.

## What changed (all open-source, $0)
- `requirements.txt`: `uvicorn[standard]` (BSD).
- `services/http_auth_guards.py`: `login_required_api` is now **async-aware**
  (async wrapper for `async def` views; sync views unchanged).
- `services/sse_response.py`: added `guarded_async_sse_response()` — async twin
  of the concurrency-capped helper.
- `apps/platform_runtime/views_workflow_progress.py` `stream_view` and
  `apps/assist_dock/views.py` `dock_context_stream_view` are now `async def`
  (async generators; `await asyncio.sleep`; DB calls via `sync_to_async` with
  `thread_sensitive=True` so django-tenants `search_path` state stays correct).
- `scripts/release/render_start_web.sh`: `WEB_SERVER_MODE=asgi` runs gunicorn
  with `uvicorn.workers.UvicornWorker` against `config.asgi:application`.
  **Default is still WSGI/gthread** — fully reversible.

## ⚠️ Validate on staging before prod
The app has ~141 middleware and uses django-tenants (per-request `search_path`).
Sync middleware runs fine under ASGI via Django's adapter, but this MUST be
exercised against a real Postgres + multiple tenants before going to prod. Do
**not** flip prod straight to `asgi`.

### Staging test plan
1. Deploy this branch to a **staging** Render service (or a Render preview).
2. Set `WEB_SERVER_MODE=asgi` on that service only.
3. Confirm boot log shows `ASGI mode enabled (uvicorn workers)`.
4. **Tenant correctness (the django-tenants risk):** log into 2+ different
   tenants in parallel; load tenant-scoped pages; confirm **no cross-tenant
   data** and no `SynchronousOnlyOperation` errors in logs.
5. **Streaming:** open 10+ browser tabs (each opens 2 SSE streams). Confirm:
   - streams deliver snapshots/heartbeats,
   - `/health/` stays 200 the whole time (the win — no starvation),
   - normal pages stay responsive.
6. Exercise a representative set of normal (sync) views, POST forms, file
   downloads, admin — confirm parity with WSGI.
7. Watch memory/CPU on the 2GB Standard box under load.

### Enable on prod (only after staging passes)
Set `WEB_SERVER_MODE=asgi` on the prod web service and redeploy.

### Rollback (instant)
Unset `WEB_SERVER_MODE` (or set `=wsgi`) and redeploy — back to gthread WSGI.
No code revert needed. The async views also run correctly under the WSGI path
in Django 5.2 (via async_to_sync), but the thread-pinning benefit only applies
under ASGI, so run WSGI with the concurrency cap as the safe default.

## Notes
- Under `UvicornWorker`, `GUNICORN_THREADS` is ignored (async, not threadpool);
  `WEB_CONCURRENCY` (process count) still applies.
- The SSE concurrency cap still applies under ASGI as a backstop, but with much
  higher effective headroom since streams no longer consume threads.
