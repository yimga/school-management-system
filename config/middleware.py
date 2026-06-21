"""
Early middleware to block common scanner/probe paths with 404.
Reduces log noise and avoids any redirect (e.g. .git) that could leak info.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import re

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound

logger = logging.getLogger(__name__)


# Path prefixes and patterns that are known scanner targets; return 404 immediately.
_SCANNER_PATH_PREFIXES = (
    "/.git",
    "/.terraform",
    "/.env",
    "/.vite/",
    "/terraform",
    "/infra/",
    "/infrastructure/",
    "/wp-config",
    "/wp-content/debug.log",
    "/wp-admin",
    "/update/index.php",
    "/_internal/",
    "/setup/",
    "/main.yml",
    "/cloudformation",
    "/serverless.yml",
    "/secrets.tfvars",
    "/prod.tfvars",
    "/staging.tfvars",
    "/dev.tfvars",
    "/variables.tf",
    "/config.js",
    "/env.js",
    "/__env.js",
    "/app.js",
    "/bundle.js",
    "/vendor.js",
    "/stripe.js",
    "/checkout.js",
    "/payment.js",
    # NOTE: /sw.js is the legitimate platform service worker — never block it here.
    "/settings.js",
)
_SCANNER_PATH_PATTERN = re.compile(
    r"^/(terraform\.tfstate|terraform\.tfvars|main\.yml|\.env\.vite)(\.json)?$",
    re.IGNORECASE,
)


class BlockScannerPathsMiddleware:
    """
    Return 404 for known scanner/probe paths before any URL resolution or redirect.
    Logs show probes for .git, terraform, wp-config, env files, etc.; this
    short-circuits them without hitting the rest of the stack.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = (request.path or "").strip()
        if not path or path == "/":
            return self.get_response(request)

        path_lower = path.lower()
        for prefix in _SCANNER_PATH_PREFIXES:
            if path_lower.startswith(prefix.lower()):
                return HttpResponseNotFound()

        if _SCANNER_PATH_PATTERN.match(path):
            return HttpResponseNotFound()

        return self.get_response(request)


class GlobalHotPathRateLimitMiddleware:
    """
    Per-IP rate limit on high-abuse public-ish paths (§0.3 security — noisy neighbor).
    Disabled when GLOBAL_HOT_PATH_RATE_LIMIT_RPM is 0 or DISABLE_GLOBAL_HOT_PATH_RATE_LIMIT=1.
    """

    _PREFIXES = (
        "/api/oneroster/",
        "/scim/",
        "/finance/payments/webhook/",
        "/lti/launch/",
        "/lti/service/",
        "/api/auth/token/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import os

        if os.getenv("DISABLE_GLOBAL_HOT_PATH_RATE_LIMIT", "").strip() in (
            "1",
            "true",
            "yes",
        ):
            return self.get_response(request)
        from django.conf import settings
        from django.http import JsonResponse

        from apps.api.rate_limit import throttle_ip_request

        rpm = int(getattr(settings, "GLOBAL_HOT_PATH_RATE_LIMIT_RPM", 240) or 0)
        if rpm <= 0:
            return self.get_response(request)
        path = (request.path or "").lower()
        if not any(path.startswith(p.lower()) for p in self._PREFIXES):
            return self.get_response(request)
        ok, retry = throttle_ip_request(
            request, scope="global_hot_path", max_count=rpm, window_seconds=60
        )
        if not ok:
            r = JsonResponse({"detail": "Rate limit exceeded"}, status=429)
            if retry:
                r["Retry-After"] = str(retry)
            return r
        return self.get_response(request)


class RequestTimeoutMiddleware:
    """
    Best-effort wall-clock cap on synchronous WSGI requests (rural / slow-network UX).

    Disabled when REQUEST_TIMEOUT_SECONDS is 0 or DISABLE_REQUEST_TIMEOUT=1.
    Does not cancel the worker thread on timeout; returns 504 to the client.
    """

    _SKIP_PREFIXES = (
        "/static/",
        "/media/",
        "/health",
        "/healthz",
        "/ready",
        "/live",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if os.getenv("DISABLE_REQUEST_TIMEOUT", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            return self.get_response(request)

        timeout = int(getattr(settings, "REQUEST_TIMEOUT_SECONDS", 0) or 0)
        if timeout <= 0:
            return self.get_response(request)

        path = (request.path or "").lower()
        if any(path.startswith(prefix) for prefix in self._SKIP_PREFIXES):
            return self.get_response(request)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.get_response, request)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "request_timeout path=%s method=%s timeout_s=%s",
                    request.path,
                    request.method,
                    timeout,
                )
                return HttpResponse(
                    "Gateway timeout — request exceeded server time limit.",
                    status=504,
                    content_type="text/plain; charset=utf-8",
                )
