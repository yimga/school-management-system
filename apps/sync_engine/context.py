"""Template chrome for live edge<->cloud sync (progress to 100%)."""

from __future__ import annotations


def edge_sync_chrome(request):
    from django.urls import NoReverseMatch, reverse

    from apps.sync_engine.edge_enabled import edge_sync_enabled

    enabled = edge_sync_enabled()
    empty = {
        "enabled": enabled,
        "status": None,
        "status_url": "",
        "sync_now_url": "",
        "percent_complete": "0.00",
        "phase": "idle",
        "headline": "",
    }
    if not enabled:
        return {"edge_sync_chrome": empty}
    try:
        empty["status_url"] = reverse("siteconfig:sync_center_status")
    except NoReverseMatch:
        empty["status_url"] = ""
    try:
        empty["sync_now_url"] = reverse("siteconfig:sync_center_sync_now")
    except NoReverseMatch:
        empty["sync_now_url"] = ""
    school = getattr(request, "school", None)
    if school is None:
        return {"edge_sync_chrome": empty}
    try:
        from apps.sync_engine.sync_status import serialize_live_status

        status = serialize_live_status(school)
    except Exception:  # noqa: BLE001 — chrome must never 500 a page
        status = None
    empty["status"] = status
    if status:
        empty["percent_complete"] = status.get("percent_complete") or "0.00"
        empty["phase"] = status.get("phase") or "idle"
        empty["headline"] = status.get("headline") or ""
    return {"edge_sync_chrome": empty}
