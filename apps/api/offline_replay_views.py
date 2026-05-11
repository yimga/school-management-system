"""
Generic offline replay batch endpoint.
Accepts a list of { method, path, body } and replays each as the current user.
Used when the service worker or client wants to sync many queued writes in one round-trip.
"""

import json
from json import JSONDecodeError
from django.core.cache import cache
from django.test import Client
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform_runtime.helpers import get_effective_offline_runtime_settings
from apps.siteconfig.cache_utils import tenant_cache_key
from apps.accounts.models import User  # role enum

QUEUE_METRICS_CACHE_KEY = "sms_offline_queue_metrics"
QUEUE_METRICS_CACHE_TIMEOUT = 86400


def _offline_runtime_settings(request) -> dict:
    return get_effective_offline_runtime_settings(request=request)


# Paths allowed for batch replay (prefixes). Restrict to avoid abuse.
ALLOWED_PATH_PREFIXES = (
    "/api/attendance/",
    "/api/entities/",
    "/api/entity/",
    "/api/finance/",
    "/api/requests/",
)


def _allowed_path(path: str) -> bool:
    path = (path or "").strip()
    if not path.startswith("/"):
        path = "/" + path
    return any(path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES)


class OfflineReplayBatchAPI(APIView):
    """
    POST body: { "items": [ { "id": 1, "method": "PATCH", "path": "/api/finance/invoices/1/", "body": {...} } ] }
    Returns: { "results": [...], "removed_ids": [...], "failed_count": N, "failed_items": [ { "url": path, "status": 409, "message": "..." } ] }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        offline_settings = _offline_runtime_settings(request)
        if not bool(offline_settings.get("enable_offline_mode", False)):
            return Response(
                {"error": "Offline sync is disabled by system configuration."},
                status=status.HTTP_403_FORBIDDEN,
            )

        items = request.data.get("items") or []
        if not isinstance(items, list):
            return Response(
                {"error": "items must be a list"}, status=status.HTTP_400_BAD_REQUEST
            )
        if len(items) > 100:
            return Response(
                {"error": "Maximum 100 items per batch"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        removed_ids = []
        failed_items = []
        client = Client()
        client.force_login(request.user)

        for idx, item in enumerate(items):
            item_id = item.get("id")
            method = (item.get("method") or "POST").upper()
            path = (item.get("path") or "").strip()
            body = item.get("body")

            if not path.startswith("/"):
                path = "/" + path
            if not _allowed_path(path):
                results.append(
                    {
                        "index": idx,
                        "status": 403,
                        "data": {"error": "path not allowed for batch replay"},
                    }
                )
                if item_id is not None:
                    failed_items.append(
                        {"url": path, "status": 403, "message": "path not allowed"}
                    )
                continue

            if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                results.append(
                    {"index": idx, "status": 400, "data": {"error": "invalid method"}}
                )
                if item_id is not None:
                    failed_items.append(
                        {"url": path, "status": 400, "message": "invalid method"}
                    )
                continue

            content = None
            if body is not None and method in ("POST", "PUT", "PATCH"):
                content = json.dumps(body) if not isinstance(body, str) else body

            try:
                resp = client.generic(
                    method,
                    path,
                    data=content or b"",
                    content_type="application/json",
                )
            except (TypeError, ValueError, RuntimeError) as e:
                results.append({"index": idx, "status": 500, "data": {"error": str(e)}})
                if item_id is not None:
                    failed_items.append({"url": path, "status": 500, "message": str(e)})
                continue

            try:
                resp_data = (
                    resp.json()
                    if resp.get("Content-Type", "").startswith("application/json")
                    else {"_raw": resp.content.decode("utf-8", errors="replace")[:500]}
                )
            except (AttributeError, TypeError, ValueError, JSONDecodeError):
                resp_data = {"_status": resp.status_code}

            results.append(
                {"index": idx, "status": resp.status_code, "data": resp_data}
            )

            if 200 <= resp.status_code < 300 and item_id is not None:
                removed_ids.append(item_id)
            elif resp.status_code >= 400 and item_id is not None:
                msg = (
                    resp_data.get("error")
                    or resp_data.get("message")
                    or resp_data.get("detail")
                    or f"HTTP {resp.status_code}"
                )
                if isinstance(msg, list):
                    msg = " ".join(str(m) for m in msg)
                failed_items.append(
                    {"url": path, "status": resp.status_code, "message": str(msg)}
                )

        return Response(
            {
                "results": results,
                "removed_ids": removed_ids,
                "failed_count": len(failed_items),
                "failed_items": failed_items,
            }
        )


class PrefetchUrlsAPI(APIView):
    """
    GET: Returns a list of URLs the client should prefetch for offline (Auto-Pilot).
    Role-based: teacher gets dashboard/teacher, entities/students, attendance; etc.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        offline_settings = _offline_runtime_settings(request)
        if not bool(offline_settings.get("enable_offline_mode", False)):
            return Response({"urls": []})
        role = (getattr(request.user, "role", "") or "").upper()
        base = request.build_absolute_uri("/").rstrip("/")
        urls = []
        if role == User.Role.TEACHER:
            urls = [
                base + "/api/dashboard/teacher/",
                base + "/api/entities/students/",
                base + "/api/attendance/",
                base + "/api/entities/classrooms/",
                base + "/portal/calendar/",
                base + "/portal/teacher/timetable/",
                base + "/portal/teacher/lesson-notes/",
            ]
        elif role in (
            "ADMIN",
            "LEADERSHIP",
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "DEAN",
            "IT_ADMIN",
            "CENSOR",
            "BURSAR",
        ):
            urls = [
                base + "/api/dashboard/admin/",
                base + "/api/entities/students/",
                base + "/api/attendance/",
                base + "/api/entities/classrooms/",
                base + "/portal/calendar/",
            ]
        elif role == User.Role.PARENT:
            urls = [base + "/api/dashboard/parent/"]
        elif role == User.Role.STUDENT:
            urls = [base + "/api/dashboard/student/"]
        else:
            urls = []
        return Response({"urls": urls[:30]})


class QueueMetricsAPI(APIView):
    """
    GET: Returns last reported queue metrics (total, by_type) from clients.
    POST: Accepts { "total": N, "by_type": { "attendance": n, "grade": n, "api": n } } and stores for admin/analytics.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        offline_settings = _offline_runtime_settings(request)
        if not bool(offline_settings.get("enable_offline_mode", False)):
            return Response({"total": 0, "by_type": {}})
        key = tenant_cache_key(QUEUE_METRICS_CACHE_KEY, request)
        data = cache.get(key)
        if not data or not isinstance(data, dict):
            return Response({"total": 0, "by_type": {}})
        return Response(data)

    def post(self, request):
        offline_settings = _offline_runtime_settings(request)
        if not bool(offline_settings.get("enable_offline_mode", False)):
            return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)
        total = request.data.get("total")
        by_type = request.data.get("by_type")
        if total is not None and not isinstance(total, (int, float)):
            total = 0
        if by_type is not None and not isinstance(by_type, dict):
            by_type = {}
        payload = {
            "total": int(total) if total is not None else 0,
            "by_type": {
                k: int(v)
                for k, v in (by_type or {}).items()
                if isinstance(v, (int, float))
            },
        }
        key = tenant_cache_key(QUEUE_METRICS_CACHE_KEY, request)
        cache.set(key, payload, QUEUE_METRICS_CACHE_TIMEOUT)
        return Response({"ok": True})
