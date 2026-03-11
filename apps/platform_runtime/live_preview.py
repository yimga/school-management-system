"""
Phase 10 — 10.6: Live Previews stub.
Central preview service; side-by-side before/after; preview by role/device/tenant.
When implemented: get_preview_url will resolve to a preview session URL.
"""


def get_preview_url(*, role: str | None = None, device: str | None = None, tenant_id=None, path: str = "/") -> str | None:
    """
    Return URL for a live preview session (role/device/tenant scoped).
    Phase 10 stub: returns None; full implementation will create preview sessions and return signed URLs.
    """
    return None
