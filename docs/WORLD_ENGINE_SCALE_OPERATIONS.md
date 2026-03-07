# World Engine — Scale & HA Operations

Notes for KEDA, CDN, WebSocket, JIT consent, and read replicas as per the master plan.

## Settings (World Engine)

- **JIT impersonation consent:** `JIT_IMPERSONATION_REQUIRE_CONSENT` (default `True`) — Super Admin must have principal consent before impersonating a tenant. `JIT_IMPERSONATION_CONSENT_DAYS` (e.g. `30`) — consent expires after this many days; re-grant required.
- **Read replica:** `DATABASE_READ_REPLICA_ALIAS` — when set (e.g. `"replica"`), `TenantDatabaseRouter.db_for_read()` routes read queries to this alias for dashboard/reports; writes still go to the primary. Omit or leave empty to use the default DB for reads.

## OIDC / Identity (Plan §3)

- OIDC is present; extend as needed for 195-country SSO. Add django-allauth only if required for social or local account flows.

## Celery workers (high concurrency)

- **Pool:** For bulk workloads use a high-concurrency pool:
  - `celery -A config worker -P gevent -c 100 -l info`
  - Or `-P eventlet` if preferred. Requires: `pip install gevent` or `eventlet`.
- **Chunking:** Bulk tasks (e.g. `evals.process_bulk_grades`) use batches of 100; for 10k+ records they chunk automatically.
- **Tenant context:** When a task operates on tenant data, pass `schema_name` and run inside `schema_context(schema_name)` (see `apps.evals.tasks.process_bulk_grades`).

## KEDA (Kubernetes Event-Driven Autoscaling)

- Scale Celery workers by queue depth (e.g. when queue > 1000 messages, scale up).
- Example ScaledObject (concept): scale the Celery worker Deployment when Redis list length for the Celery queue exceeds a threshold. See [KEDA Redis scaler](https://keda.sh/docs/2.12/scalers/redis/).
- Ensure worker pod template uses the same app and broker URL as the rest of the stack.

## CDN (Cloudflare / CloudFront)

- Serve static assets and school logos from the CDN; set `STATIC_URL` / `MEDIA_URL` to the CDN origin or use a separate `STATIC_CDN_URL` for assets.
- Target ~100ms latency for regions such as Cameroon; use regional edge caches when available.

## WebSocket (cross-node)

- For real-time features (e.g. emergency broadcast, live updates), use Redis Pub/Sub so messages published on one app node are received by clients connected to another node.
- Configure Django Channels or similar with Redis as the channel layer backend so all ASGI workers share the same pub/sub stream.

## AI chat (Channels)

- **In-app AI chat** (World Engine B.3): Real-time ChatGPT-like chat for teachers and students over WebSocket at `ws/ai/chat/`. Implemented in `apps.api.consumers.AIChatConsumer`; calls `OllamaInferenceService` (single AI path).
- **To enable:** Install `channels` and `channels-redis`, add them to `INSTALLED_APPS`, set `ASGI_APPLICATION = "config.asgi.application"`, and configure `CHANNEL_LAYERS` (see commented block in `config/settings.py`). Run the app with an ASGI server (e.g. `daphne config.asgi:application` or `uvicorn config.asgi:application`) so WebSocket connections are accepted. Channels is required for AI chat; without it, only HTTP-based copilot is available.

## Cache keys (tenant isolation)

- All tenant-scoped cache keys are prefixed via `apps.siteconfig.cache_utils.get_tenant_cache_prefix()` or `tenant_cache_key(base_key, request)` so shared Redis does not leak data between tenants.

### Cache key audit (F.2)

| Location | Key / pattern | Scope | Status |
|----------|----------------|-------|--------|
| evals/performance_optimization.py | CacheManager (student_grades_, class_stats_, etc.), QueryCaching (query_result_) | Tenant | Prefixed with `get_tenant_cache_prefix()` |
| siteconfig/portal_sidebar_items.py | portal_sidebar_badges:{user_id}:{role}:{staff_like} | Tenant | Prefixed with `get_tenant_cache_prefix(request)` |
| api/offline_replay_views.py, accounts/views.py | sms_offline_queue_metrics | Tenant | Uses `tenant_cache_key("sms_offline_queue_metrics", request)` |
| services/inference.py | ai:inference:{hash} | Global (prompt-based) | Not tenant-scoped; safe |

## Regional AI sidecar (Sovereign AI)

- **Single source of config:** Per-region Ollama endpoint and model are stored in **RegionalAIConfig** (public schema). Do not maintain a separate `REGIONAL_AI_CONFIG` dict in settings; the table is the only source. Settings `OLLAMA_ENDPOINT` and `OLLAMA_MODEL` are used only when no row exists for the region.
- **Entry point:** All Ollama-backed inference goes through **services.inference.OllamaInferenceService.infer()** (region from request/school/country_code, country dossier, Redis cache, fallback model, PII stripping).
- **Deployment:** Run one or more Ollama instances per region (e.g. Docker or Kubernetes). Use a load balancer (e.g. NGINX) in front of Ollama so the app talks to `http://ollama-region:11434` (or the LB URL). Configure GPU passthrough when available (e.g. `nvidia-container-toolkit` for Docker, or node selector for GPU nodes in K8s). Set **RegionalAIConfig.ollama_base_url** to the LB or instance URL for that region. Hot-swap: run two instances (A = current, B = new); point the LB to B when B is healthy; decommission A. See [docs/AI_MODEL_LIFECYCLE.md](AI_MODEL_LIFECYCLE.md) for model sync and offline procedures.

---

## Operational checklist (KEDA / CDN / WebSocket)

Use this when enabling scale or real-time features in production.

### KEDA (worker autoscaling)

- [ ] Redis broker is used for Celery (`CELERY_BROKER_URL` / `REDIS_URL`).
- [ ] Create a KEDA ScaledObject that watches the Celery queue (e.g. Redis list length for the queue key). See [KEDA Redis scaler](https://keda.sh/docs/2.12/scalers/redis/).
- [ ] Set min/max replicas (e.g. min 1, max 50) and target queue depth (e.g. scale when queue > 500).
- [ ] Worker Deployment uses the same image and env as the app; `celery -A config worker` with appropriate concurrency.

### CDN (static/media at edge)

- [ ] Choose provider (Cloudflare, CloudFront, or Render CDN). Configure origin to the app URL.
- [ ] Set `STATIC_URL` and optionally `MEDIA_URL` to CDN URLs (e.g. `https://cdn.example.com/static/`).
- [ ] Ensure cache-control headers: long `max-age` for hashed static files; short or no-store for tenant-specific media.
- [ ] Run `collectstatic` and optionally sync to CDN origin (or let the app serve static and put CDN in front).

### WebSocket (Channels + Redis)

- [ ] Install: `pip install channels channels-redis`.
- [ ] In settings, Channels and CHANNEL_LAYERS are auto-configured when packages are present (see `config/settings.py`).
- [ ] Run app with ASGI: `daphne config.asgi:application` or `uvicorn config.asgi:application` (and bind to `0.0.0.0:$PORT`).
- [ ] Set `REDIS_URL` so CHANNEL_LAYERS uses Redis; all ASGI workers share the same pub/sub.
- [ ] For production, run multiple Daphne/Uvicorn workers behind a process manager; Redis ensures cross-node delivery.
