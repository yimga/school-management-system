# SSE Deployment Runbook — Migration Cloud (v3.33.0)

This runbook is the SOT for deploying the Migration Cloud Server-Sent
Events (SSE) progress stream at:

    GET /super/migration/api/v1/bundles/<pk>/events/stream/
    GET /portal/configure/migration/api/v1/bundles/<pk>/events/stream/

The endpoint emits `text/event-stream` frames as bundle-lifecycle
progress events arrive. It runs in one of two transports — selected by
the `MIGRATION_CLOUD_SSE_TRANSPORT` environment variable (consumed by
`config/settings.py`).

| Transport | Setting value | Behavior | When to use |
|---|---|---|---|
| **WSGI fallback** | `wsgi-fallback` (default) | One-shot snapshot frame + `stream.close` sentinel; client re-polls. Worker is released immediately. | Sync Gunicorn or any WSGI server. Safe default — never burns a worker. |
| **ASGI/Daphne long-poll** | `asgi-daphne` | Full 60-second long-poll loop, heartbeat every 30s, graceful close on max-duration. | Daphne / Uvicorn / any ASGI server with non-blocking I/O. |

---

## 1. Why the WSGI fallback exists

Django under sync Gunicorn binds **one worker per concurrent HTTP
connection**. A 60-second SSE long-poll therefore monopolizes one
worker for the entire duration. Five concurrent SSE clients with a
default `--workers 4` Gunicorn process group **wedges the platform** —
every other request queues behind the long-polls.

Worse, Gunicorn's `--worker-class sync` (the default) does not honor
SSE's progress-as-you-go semantics: the response body is buffered by
the WSGI middleware chain until the generator completes, so clients
see nothing for the full 60 seconds.

Async worker classes (`gevent`, `eventlet`, `uvicorn.workers.UvicornWorker`)
exist but each has caveats:

* **gevent / eventlet** monkey-patch the stdlib — interactions with
  `psycopg2`, `pyOpenSSL`, and the Celery client can deadlock.
  Production-grade only with explicit auditing of every socket-touching
  dependency. Not recommended for SSE-only.
* **uvicorn.workers.UvicornWorker** runs an ASGI app inside Gunicorn —
  this is fine but pulls all the Gunicorn complexity. If you're on
  ASGI, run Daphne or Uvicorn directly.

The clean answer: **run a separate Daphne process for the
SSE-emitting URL patterns**, or run the entire app under Daphne if the
ASGI app graph is stable.

## 2. ASGI / Daphne deployment recipe

### 2.1 Install + verify

```
pip install "daphne>=4.1,<5.0" "channels>=4.0,<5.0"
```

Confirm the project's ASGI entry point is wired:

```
$ python -c "from config.asgi import application; print(type(application).__name__)"
ASGIHandler
```

### 2.2 Process group

Run two process groups behind nginx:

* **Gunicorn (WSGI)** — handles `*.html`, REST API JSON, static, file
  uploads. Continues to run at `--workers $(nproc * 2 + 1)`.
* **Daphne (ASGI)** — handles SSE only, routed by path.

systemd unit for Daphne:

    [Unit]
    Description=RunMyCampus ASGI (Migration Cloud SSE)
    After=network.target
    Requires=postgresql.service

    [Service]
    User=runmycampus
    WorkingDirectory=/srv/runmycampus/current
    Environment=DJANGO_SETTINGS_MODULE=config.settings
    Environment=MIGRATION_CLOUD_SSE_TRANSPORT=asgi-daphne
    EnvironmentFile=/etc/runmycampus/runmycampus.env
    ExecStart=/srv/runmycampus/venv/bin/daphne \
      --bind 127.0.0.1 --port 8001 \
      --proxy-headers \
      --access-log /var/log/runmycampus/daphne-access.log \
      config.asgi:application
    Restart=on-failure
    RestartSec=5

    [Install]
    WantedBy=multi-user.target

`MIGRATION_CLOUD_SSE_TRANSPORT=asgi-daphne` is the load-bearing line —
the SSE view consults it and switches from one-shot snapshot to full
long-poll when set.

### 2.3 nginx upstream + buffering directives

```nginx
upstream rmc_wsgi   { server 127.0.0.1:8000; }
upstream rmc_asgi   { server 127.0.0.1:8001; }

server {
    listen 443 ssl http2;
    server_name manager.runmycampus.com;

    # ── SSE — long-lived, must NOT buffer ──────────────────────────
    location ~ ^/(super|portal/configure)/migration/api/v1/bundles/[0-9]+/events/stream/ {
        proxy_pass         http://rmc_asgi;
        proxy_http_version 1.1;
        proxy_set_header   Connection "";          # disable upstream keepalive
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        proxy_buffering             off;            # CRITICAL — stream as bytes arrive
        proxy_cache                 off;
        proxy_read_timeout          120s;           # > SSE_MAX_DURATION_SECONDS
        proxy_send_timeout          120s;
        chunked_transfer_encoding   on;
        gzip                        off;            # gzip breaks SSE framing
    }

    # ── Everything else — fast WSGI path ───────────────────────────
    location / {
        proxy_pass http://rmc_wsgi;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Key directives:

| Directive | Why |
|---|---|
| `proxy_buffering off` | nginx default buffers entire response before sending — SSE clients see nothing until 60s timeout. |
| `proxy_cache off` | Caching a `text/event-stream` is meaningless and can serve stale frames. |
| `proxy_read_timeout 120s` | Must exceed `SSE_MAX_DURATION_SECONDS` (60s) + heartbeat (30s). 120s is comfortable. |
| `gzip off` for the route | gzip combines frames into a compressed block; clients can't parse partial frames mid-decompression. |
| `Connection ""` | Disables upstream keepalive so Daphne sees one connection = one request, simpler request lifecycle. |

### 2.4 Health-check exclusion

The platform's uptime probe (`/health/` or `/-/healthz`) MUST be routed
to the WSGI upstream — never to Daphne. Reasons:

1. The health-check stays sync (a Daphne event-loop hiccup should not
   mark the WSGI app down).
2. ASGI startup is heavier; pointing every health check at Daphne
   means a Daphne restart marks the whole site DOWN even when WSGI is
   healthy.

```nginx
    location = /health/        { proxy_pass http://rmc_wsgi; }
    location = /-/healthz      { proxy_pass http://rmc_wsgi; }
    location = /-/readyz       { proxy_pass http://rmc_wsgi; }
```

If your monitoring tool (Datadog, UptimeRobot, etc.) probes the SSE
endpoint directly, configure it to follow only the **first** SSE frame
and disconnect. Long-poll-as-health-check will wedge a Daphne worker
per probe.

## 3. Graceful-disconnect contract

The platform guarantees:

1. **Initial frame** — every connection receives a `bundle.status`
   frame within 200ms of connection, even on a quiet bundle.
2. **Heartbeats** — `: ping\n\n` comment lines arrive every 30s
   (per `SSE_HEARTBEAT_SECONDS`).
3. **Max duration** — connections close gracefully after 60s with a
   `stream.close` event carrying `reason: "max-duration-reached"` and
   `reconnect: true`.
4. **Header advertising the mode** — every response carries
   `X-Migration-Cloud-SSE-Transport: asgi-daphne | wsgi-fallback` so
   clients can adapt their reconnect strategy without parsing the
   payload.
5. **WSGI fallback contract** — when the transport is `wsgi-fallback`,
   the server emits exactly two frames (`bundle.status` + `stream.close`
   with `reason: "wsgi-fallback-one-shot"`) and closes. Clients should
   re-poll on a 5-10s timer, not reconnect-immediately.

Clients should use the browser's `EventSource` retry semantics (default
3s backoff) OR a hand-rolled exponential reconnect (1s → 2s → 4s →
30s cap) — never reconnect with zero delay on `stream.close`.

## 4. Operator runbook

### 4.1 Promoting from `wsgi-fallback` to `asgi-daphne`

1. Provision the Daphne systemd unit (§2.2).
2. Add the nginx SSE route (§2.3) — **do NOT remove `proxy_buffering off`**.
3. Deploy with `MIGRATION_CLOUD_SSE_TRANSPORT=asgi-daphne` set in
   `/etc/runmycampus/runmycampus.env`.
4. `systemctl reload nginx && systemctl restart rmc-asgi.service`.
5. Verify with curl:

       curl -N -H 'Authorization: Bearer mc_…' \
         https://manager.runmycampus.com/super/migration/api/v1/bundles/42/events/stream/

   Expect: one `bundle.status` frame immediately, then `: ping` lines
   every 30s, then `stream.close` after 60s.
6. Check `X-Migration-Cloud-SSE-Transport: asgi-daphne` header in
   response.

### 4.2 Rolling back to `wsgi-fallback`

If Daphne misbehaves under load:

1. `systemctl stop rmc-asgi.service`.
2. Set `MIGRATION_CLOUD_SSE_TRANSPORT=wsgi-fallback` (or unset — that's
   the default).
3. `systemctl reload gunicorn`.

The nginx SSE route can stay in place; with Daphne down it will
502-fail-over to the WSGI upstream if the upstream block lists both,
OR you remove the route to short-circuit straight to WSGI.

### 4.3 Health checks

```
# Liveness — never hits SSE.
curl -fsS https://manager.runmycampus.com/-/healthz

# Daphne probe — expect Server: daphne header and a single frame.
curl -sI https://manager.runmycampus.com/super/migration/api/v1/bundles/1/events/stream/ \
  -H 'Authorization: Bearer ...' | grep -i 'sse-transport\|server'
```

### 4.4 Capacity planning

* **wsgi-fallback** — no capacity impact; each SSE request is a normal
  ≤200ms response.
* **asgi-daphne** — each connection holds ~30KB of Python heap and an
  open Postgres cursor for the 60s polling window. Daphne can hold
  ~2-5k concurrent SSE connections per CPU core on a small box;
  scaling is horizontal (more Daphne instances behind the upstream).

## 5. Known limitations

* **No multiplexing** — every bundle gets its own connection. A user
  watching 10 bundles holds 10 sockets. A future v3.34 may add a
  `/events/multi/?bundle_ids=…` endpoint with a single
  fan-out connection.
* **No backpressure** — if a client reads slowly, frames buffer in
  nginx (we disable buffering) and eventually TCP-window-close the
  upstream. The platform does not detect the slow client — it just
  hits max-duration normally.
* **No replay-after-disconnect** — `Last-Event-ID` header is not yet
  honored; clients reconnect and receive all events since the bundle
  was created (deduplicated client-side by event id).

## 6. References

* `apps/migration_cloud/api/sse.py` — view + transport-mode resolver.
* `config/settings.py::MIGRATION_CLOUD_SSE_TRANSPORT` — env-driven SOT.
* SSE spec: https://html.spec.whatwg.org/multipage/server-sent-events.html
* Daphne docs: https://channels.readthedocs.io/projects/daphne/

---

*Runbook version: v3.33.0 — 2026-05-18.*
