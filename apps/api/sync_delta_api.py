"""
Phase 2 + Phase G: Delta sync API – apply only changed fields with updated_at conflict check.
Accepts POST { "items": [ { "entity_type", "id", "changes": {...}, "updated_at" } ] }.
On conflict: do not overwrite; persist SyncConflict and return conflicts for Sync Center.
Frontend MUST use tenant-scoped IndexedDB key (e.g. sync_queue_${school_id}) for offline queue.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.sync_services import apply_changes
from apps.platform_runtime.helpers import get_effective_offline_runtime_settings


class DeltaSyncAPI(APIView):
    """
    POST body: { "items": [ { "entity_type": "student", "id": 1, "changes": { "first_name": "X" },
      "updated_at": "2025-01-01T12:00:00Z", "client_item_id": "optional-uuid" } ] }
    Returns: { "results", "removed_ids", "failed_count", "failed_items", "conflicts" }.
    When a conflict is detected (server newer than client), a SyncConflict is created and
    the item is included in "conflicts" for Sync Center resolution.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        offline_settings = get_effective_offline_runtime_settings(request=request)
        if not bool(offline_settings.get("enable_offline_mode", False)):
            return Response({"error": "Offline sync is disabled."}, status=status.HTTP_403_FORBIDDEN)
        items = request.data.get("items") or []
        if not isinstance(items, list):
            return Response({"error": "items must be a list"}, status=status.HTTP_400_BAD_REQUEST)
        if len(items) > 50:
            return Response({"error": "Maximum 50 items per delta batch"}, status=status.HTTP_400_BAD_REQUEST)

        school = getattr(request, "school", None)
        school_id = str(school.id) if school else None
        out = apply_changes(school_id, request.user, items, persist_conflicts=True)

        results = out["results"]
        conflicts = out["conflicts"]
        removed_ids = []
        failed_items = []
        for idx, item in enumerate(items):
            item_id = item.get("client_item_id")
            if item_id is None:
                continue
            res = next((r for r in results if r.get("index") == idx), None)
            if res and res.get("status") == 200:
                removed_ids.append(item_id)
            elif res and res.get("status") >= 400:
                data = res.get("data") or {}
                msg = data.get("error") or data.get("message") or f"HTTP {res.get('status')}"
                entity_type = (item.get("entity_type") or "").strip().lower()
                pk = item.get("id")
                failed_items.append({"url": f"{entity_type}/{pk}", "status": res.get("status"), "message": str(msg)})

        return Response({
            "results": results,
            "removed_ids": removed_ids,
            "failed_count": len(failed_items),
            "failed_items": failed_items,
            "conflicts": conflicts,
            "success_count": out["success_count"],
        })
