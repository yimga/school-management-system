"""
Phase 10 — 10.6: Live Previews.
Central preview service; side-by-side before/after; preview by role/device/tenant.
"""


def get_preview_url(*, role: str | None = None, device: str | None = None, tenant_id=None, path: str = "/") -> str | None:
    """
    Return URL for a live preview session (role/device/tenant scoped).
    Builds a preview path with query params; front-end or preview view can resolve session from them.
    """
    from urllib.parse import urlencode
    params = {}
    if role:
        params["role"] = role
    if device:
        params["device"] = device
    if tenant_id:
        params["tenant_id"] = str(tenant_id)
    if path and path != "/":
        params["path"] = path
    qs = urlencode(params)
    return f"/portal/preview?{qs}" if qs else "/portal/preview"
