"""
Generic offline replay batch endpoint.
Accepts a list of { method, path, body } and replays each as the current user.
Used when the service worker or client wants to sync many queued writes in one round-trip.
"""

import json
from django.test import Client
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.siteconfig.models import SiteSettings


# Paths allowed for batch replay (prefixes). Restrict to avoid abuse.
ALLOWED_PATH_PREFIXES = ("/api/attendance/", "/api/entities/", "/api/entity/", "/api/finance/", "/api/requests/")


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
        site = SiteSettings.get_solo()
        if not getattr(site, "enable_offline_mode", False):
            return Response(
                {"error": "Offline sync is disabled by system configuration."},
                status=status.HTTP_403_FORBIDDEN,
            )

        items = request.data.get("items") or []
        if not isinstance(items, list):
            return Response({"error": "items must be a list"}, status=status.HTTP_400_BAD_REQUEST)
        if len(items) > 100:
            return Response({"error": "Maximum 100 items per batch"}, status=status.HTTP_400_BAD_REQUEST)

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
                results.append({"index": idx, "status": 403, "data": {"error": "path not allowed for batch replay"}})
                if item_id is not None:
                    failed_items.append({"url": path, "status": 403, "message": "path not allowed"})
                continue

            if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                results.append({"index": idx, "status": 400, "data": {"error": "invalid method"}})
                if item_id is not None:
                    failed_items.append({"url": path, "status": 400, "message": "invalid method"})
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
            except Exception as e:
                results.append({"index": idx, "status": 500, "data": {"error": str(e)}})
                if item_id is not None:
                    failed_items.append({"url": path, "status": 500, "message": str(e)})
                continue

            try:
                resp_data = resp.json() if resp.get("Content-Type", "").startswith("application/json") else {"_raw": resp.content.decode("utf-8", errors="replace")[:500]}
            except Exception:
                resp_data = {"_status": resp.status_code}

            results.append({"index": idx, "status": resp.status_code, "data": resp_data})

            if 200 <= resp.status_code < 300 and item_id is not None:
                removed_ids.append(item_id)
            elif resp.status_code >= 400 and item_id is not None:
                msg = (resp_data.get("error") or resp_data.get("message") or resp_data.get("detail") or f"HTTP {resp.status_code}")
                if isinstance(msg, list):
                    msg = " ".join(str(m) for m in msg)
                failed_items.append({"url": path, "status": resp.status_code, "message": str(msg)})

        return Response({
            "results": results,
            "removed_ids": removed_ids,
            "failed_count": len(failed_items),
            "failed_items": failed_items,
        })
