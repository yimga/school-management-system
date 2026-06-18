"""Secured internal cron endpoint (Option 2) — external schedulers trigger jobs.

A token-authed, CSRF-exempt machine endpoint so a FREE external scheduler
(GitHub Actions cron, cron-job.org, UptimeRobot, ...) or Render cron can drive
the periodic-job registry — including HEAVY jobs that should not run in the web
dyno's threads off ``/health/``.

Auth mirrors ``apps.platform_runtime.views_rum.rum_ingest``: a shared secret in
``settings.INTERNAL_CRON_TOKEN`` (env ``INTERNAL_CRON_TOKEN``), constant-time
compared. The endpoint is DISABLED (404, indistinguishable from "no such URL")
whenever the token is unset or shorter than ``MIN_TOKEN_LEN`` — so it is never an
open door, even before the secret is provisioned.

  POST /api/internal/cron/run/
    Authorization: Bearer <INTERNAL_CRON_TOKEN>     (or header X-Cron-Key, or body token)
    body (optional JSON):
      {"job": "<name>"}     run just this job (omit → run all DUE jobs)
      {"force": true}       run even if not yet due (operator override)
      {"background": true}  fire-and-forget in a daemon thread, return 202

  GET /api/internal/cron/run/
    → registry status (jobs, intervals, last_run, due_now) for monitoring.

Every path converges on ``apps.platform_runtime.periodic`` — the SAME registry +
per-job locking the in-process scheduler uses, so triggers can't double-fire.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

MIN_TOKEN_LEN = 16
MAX_BODY_BYTES = 4096  # magic-number-allow: max request body bytes (mirrors views_rum)
RATE_LIMIT_PER_MINUTE = 30
RATE_WINDOW_SECONDS = 60


def _configured_token() -> str:
    return (getattr(settings, "INTERNAL_CRON_TOKEN", None) or "").strip()


def _read_body(request) -> bytes | None:
    """Read the request body once, safely. None ⇒ unreadable/oversized (caller 400s).

    ``request.body`` can raise UnreadablePostError (client disconnect) or
    RequestDataTooBig (Django's DATA_UPLOAD_MAX_MEMORY_SIZE) — neither must 500.
    """
    try:
        return request.body or b""
    except Exception:  # noqa: BLE001 — any body-read failure → treat as bad request
        return None


def _presented_token(request, body_bytes: bytes) -> str:
    raw = request.headers.get("Authorization") or request.META.get("HTTP_AUTHORIZATION") or ""
    raw = raw.strip()
    if raw:
        parts = raw.split()
        if len(parts) == 2 and parts[0].lower() in ("bearer", "token"):
            return parts[1].strip()
        if len(parts) == 1:
            return parts[0].strip()
    header_key = (
        request.headers.get("X-Cron-Key") or request.META.get("HTTP_X_CRON_KEY") or ""
    ).strip()
    if header_key:
        return header_key
    if request.method == "POST" and body_bytes:
        try:
            body = json.loads(body_bytes.decode("utf-8") or "{}")
            if isinstance(body, dict) and isinstance(body.get("token"), str):
                return body["token"].strip()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ""
    return ""


def _authorized(request, body_bytes: bytes) -> bool:
    configured = _configured_token()
    if len(configured) < MIN_TOKEN_LEN:
        return False  # disabled
    presented = _presented_token(request, body_bytes)
    if len(presented) != len(configured):
        return False
    try:
        return secrets.compare_digest(presented, configured)
    except (TypeError, ValueError):
        # Non-ASCII / non-str token must never escalate to a 500.
        return False


def _rate_ok(request) -> bool:
    ip = request.META.get("REMOTE_ADDR") or "0"
    key = f"rmc:cron:rl:{ip}"
    try:
        cache.add(key, 0, timeout=RATE_WINDOW_SECONDS)
        n = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=RATE_WINDOW_SECONDS)
        n = 1
    except Exception:  # noqa: BLE001 — cache down → don't block the trigger
        logger.debug("cron rate cache unavailable", exc_info=True)
        return True
    return n <= RATE_LIMIT_PER_MINUTE


@csrf_exempt
@require_http_methods(["GET", "POST"])
def internal_cron_run(request):
    """Token-authed trigger for the periodic-job registry. See module docstring."""
    # Token unset/short → behave as if the route does not exist.
    if len(_configured_token()) < MIN_TOKEN_LEN:
        return HttpResponse(status=404)
    # Read the POST body ONCE (Django caches it, but reading can raise) and reuse
    # it for both auth and directive parsing below.
    body_bytes = b""
    if request.method == "POST":
        body_bytes = _read_body(request)
        if body_bytes is None:
            return HttpResponse(status=400)
        if len(body_bytes) > MAX_BODY_BYTES:
            return HttpResponse(status=413)
    if not _authorized(request, body_bytes):
        return HttpResponse(status=403)
    if not _rate_ok(request):
        return HttpResponse(status=429)

    from apps.platform_runtime import periodic

    if request.method == "GET":
        return JsonResponse({"jobs": periodic.registry_status()})

    # POST — parse optional directives from the already-read body.
    job = None
    force = False
    background = False
    try:
        body = json.loads(body_bytes.decode("utf-8") or "{}")
        if isinstance(body, dict):
            job = body.get("job") or None
            force = bool(body.get("force"))
            background = bool(body.get("background"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse(status=400)

    if job is not None and not isinstance(job, str):
        return HttpResponse(status=400)

    def _do() -> list[dict]:
        if job:
            return [periodic.run_job(job, force=force)]
        return periodic.run_due_jobs(force=force)

    if background:
        def _bg() -> None:
            try:
                _do()
            finally:
                # One-shot thread: release its DB connections (don't leak the budget).
                periodic.close_thread_connections()

        threading.Thread(target=_bg, name="rmc-cron-endpoint", daemon=True).start()
        logger.info("internal_cron_run dispatched in background (job=%s force=%s)", job, force)
        return JsonResponse({"status": "accepted", "job": job, "force": force}, status=202)

    results = _do()
    logger.info("internal_cron_run ran synchronously: %s", results)
    return JsonResponse({"status": "ok", "results": results})
