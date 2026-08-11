"""
Phase 10 — 10.6: Live Previews.
Central preview service; side-by-side before/after; preview by role/device/tenant.
"""


def get_preview_url(
    *,
    role: str | None = None,
    device: str | None = None,
    tenant_id=None,
    path: str = "/",
    origin_host: str | None = None,
) -> str | None:
    """
    Return URL for a live preview session (role/device/tenant scoped).
    Builds a preview path with query params; front-end or preview view can resolve session from them.
    """
    from urllib.parse import urlencode

    from urllib.parse import parse_qsl, urlsplit, urlunsplit

    raw_path = (path or "/").strip()
    parsed = urlsplit(raw_path)
    # Setup Studio can supply an absolute canonical tenant URL for the admin
    # role. Convert it back to a path only when its hostname exactly matches
    # the current request host. External/protocol-relative destinations remain
    # blocked so this service cannot become an open redirect.
    if parsed.scheme or parsed.netloc:
        allowed_hostname = urlsplit(f"//{origin_host or ''}").hostname
        if (
            parsed.scheme not in {"http", "https"}
            or not allowed_hostname
            or parsed.hostname != allowed_hostname
        ):
            return None
    if not parsed.path.startswith("/"):
        return None
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params["rmc_embed"] = "1"
    if role:
        params["role"] = role
    if device:
        params["device"] = device
    if tenant_id:
        params["tenant_id"] = str(tenant_id)
    if path and path != "/":
        params["rmc_preview_path"] = parsed.path
    qs = urlencode(params)
    return urlunsplit(("", "", parsed.path or "/", qs, ""))
