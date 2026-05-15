"""Content-Security-Policy middleware.

**Enforce mode by default since v2.57.** The inline-style backlog reached
zero (enforced by ``scan_inline_style_off_token`` zero-tolerance gate
post-v2.27), so ``style-src`` no longer needs ``'unsafe-inline'`` and
``CSP_ENFORCE`` defaults to ``True``.

Policy is intentionally conservative — `'self'`-only for scripts, styles,
and connect. Operators can roll back to Report-Only by setting
``CSP_ENFORCE=0`` in env if a regression surfaces.

Settings (declared in ``config/settings_registry.py``):

- ``CSP_ENFORCE``                  — bool, default True (enforce)
- ``CSP_REPORT_URI``               — str, default "/security/csp-report/"
- ``CSP_EXTRA_SCRIPT_SRC``         — tuple[str], extra script-src origins
- ``CSP_EXTRA_STYLE_SRC``          — tuple[str], extra style-src origins
- ``CSP_EXTRA_IMG_SRC``            — tuple[str], extra img-src origins
- ``CSP_EXTRA_CONNECT_SRC``        — tuple[str], extra connect-src origins
- ``CSP_EXTRA_FRAME_ANCESTORS``    — tuple[str], extra frame-ancestors

Bypass: paths under ``/admin/`` and ``/static/`` keep the default Django
behavior to avoid breaking the admin or static asset delivery.
"""

from __future__ import annotations

from django.conf import settings


_DEFAULT_DIRECTIVES: dict[str, tuple[str, ...]] = {
    "default-src": ("'self'",),
    "script-src": ("'self'",),
    "style-src": ("'self'",),  # 'unsafe-inline' removed v2.57 — inline-style backlog at 0
    "img-src": ("'self'", "data:", "https:"),
    "font-src": ("'self'", "data:", "https:"),
    "connect-src": ("'self'",),
    "frame-ancestors": ("'self'",),
    "base-uri": ("'self'",),
    "form-action": ("'self'",),
    "object-src": ("'none'",),
}


def _build_policy() -> str:
    """Compose the CSP header value from settings overrides."""
    directives = {k: list(v) for k, v in _DEFAULT_DIRECTIVES.items()}

    extras = {
        "script-src": getattr(settings, "CSP_EXTRA_SCRIPT_SRC", ()) or (),
        "style-src": getattr(settings, "CSP_EXTRA_STYLE_SRC", ()) or (),
        "img-src": getattr(settings, "CSP_EXTRA_IMG_SRC", ()) or (),
        "connect-src": getattr(settings, "CSP_EXTRA_CONNECT_SRC", ()) or (),
        "frame-ancestors": getattr(settings, "CSP_EXTRA_FRAME_ANCESTORS", ()) or (),
    }
    for directive, extra in extras.items():
        for v in extra:
            if v and v not in directives[directive]:
                directives[directive].append(v)

    parts = []
    for directive, sources in directives.items():
        parts.append(f"{directive} {' '.join(sources)}")

    report_uri = (getattr(settings, "CSP_REPORT_URI", "") or "").strip()
    if report_uri:
        parts.append(f"report-uri {report_uri}")

    return "; ".join(parts)


class ContentSecurityPolicyMiddleware:
    """Adds the CSP header to every HTML response.

    In Report-Only mode (default) browsers send violation reports but do not
    block. Flip ``CSP_ENFORCE=True`` once the high-traffic surfaces show zero
    new violations.
    """

    BYPASS_PREFIXES = ("/admin/", "/static/", "/media/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = (request.path or "").rstrip("/") or "/"
        if any(path.startswith(p) for p in self.BYPASS_PREFIXES):
            return response

        # Only apply CSP to HTML / XHTML — adding it to JSON responses is noise.
        ct = (response.get("Content-Type") or "").lower()
        if not (ct.startswith("text/html") or ct.startswith("application/xhtml")):
            return response

        policy = _build_policy()
        if getattr(settings, "CSP_ENFORCE", False):
            response["Content-Security-Policy"] = policy
        else:
            response["Content-Security-Policy-Report-Only"] = policy
        return response


__all__ = ["ContentSecurityPolicyMiddleware", "_build_policy"]
