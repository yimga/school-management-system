"""Content-Security-Policy middleware.

**Posture — strict script-src, pragmatic style-src (the XSS-meaningful split).**
``script-src`` is ``'self'`` + a per-request ``'nonce-<n>'`` with NO
``'unsafe-inline'`` and NO ``'unsafe-eval'`` — this is the directive that
actually stops XSS, so it is kept tight. ``style-src`` carries ``'unsafe-inline'``
because the platform ships ~2,300 inline ``style="…"`` attributes across 400+
templates and a nonce cannot authorize a style ATTRIBUTE (only ``<style>`` /
``<script>`` ELEMENTS), so eliminating them is a multi-wave sweep with little
security payoff — ``apps/security/csp_readiness.py`` documents why style-CSP buys
far less defense than script-CSP. A correction of the record: an earlier docstring
claimed the inline-style backlog was "at zero"; it was not (``scan_inline_style_off_token``
only measures OFF-TOKEN inline styles, never their existence), which is why
``style-src`` retains ``'unsafe-inline'`` here.

⚠️ Because ``style-src`` uses ``'unsafe-inline'``, the per-request nonce is added
to ``script-src`` ONLY. Per the CSP3 spec, a directive that carries BOTH a nonce
and ``'unsafe-inline'`` makes browsers IGNORE ``'unsafe-inline'`` — which would
re-break every inline style attribute. Do not add the nonce to ``style-src``.

Enforcing strict ``script-src`` still requires retiring the inline event handlers
(``onclick=`` …) that a nonce cannot cover; until that burndown lands, prod pins
``CSP_ENFORCE=0`` (Report-Only) in ``render.yaml``. Operators roll back to
Report-Only by setting ``CSP_ENFORCE=0``.

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

import secrets

from django.conf import settings


_DEFAULT_DIRECTIVES: dict[str, tuple[str, ...]] = {
    "default-src": ("'self'",),
    "script-src": ("'self'",),  # + per-request nonce; NO 'unsafe-inline'/'unsafe-eval' (the XSS-critical directive)
    "style-src": ("'self'", "'unsafe-inline'"),  # inline style ATTRIBUTES can't be nonced; ~2,300 across 400+ templates — style-CSP buys little (see csp_readiness.py)
    "img-src": ("'self'", "data:", "https:"),
    "font-src": ("'self'", "data:", "https:"),
    "connect-src": ("'self'",),
    "frame-ancestors": ("'self'",),
    "base-uri": ("'self'",),
    "form-action": ("'self'",),
    "object-src": ("'none'",),
}


def _build_policy(nonce: str = "") -> str:
    """Compose the CSP header value from settings overrides.

    When ``nonce`` is supplied it is added to ``script-src`` ONLY, as
    ``'nonce-<n>'``, so inline ``<script nonce>`` blocks are allowed WITHOUT
    weakening ``script-src`` with ``'unsafe-inline'``. ``'self'`` is preserved,
    so same-origin external assets keep working — the nonce is strictly additive.

    The nonce is deliberately NOT added to ``style-src``: that directive carries
    ``'unsafe-inline'`` (inline style ATTRIBUTES cannot be nonced), and per the
    CSP3 spec a directive with BOTH a nonce and ``'unsafe-inline'`` makes browsers
    ignore ``'unsafe-inline'`` — which would block every inline ``style="…"``
    attribute. ``<style nonce>`` blocks still render: ``'unsafe-inline'`` allows
    all inline style, so the (now-redundant) nonce attribute on them is harmless.
    """
    directives = {k: list(v) for k, v in _DEFAULT_DIRECTIVES.items()}
    if nonce:
        directives["script-src"].append(f"'nonce-{nonce}'")

    # Cloudflare Turnstile (login bot-challenge) loads an external script AND
    # renders inside an iframe — allow its origin in script-src + frame-src,
    # but ONLY when a site key is configured so the default policy stays tight.
    if (getattr(settings, "TURNSTILE_SITE_KEY", "") or "").strip():
        for _directive in ("script-src", "frame-src"):
            directives.setdefault(_directive, ["'self'"])
            if "https://challenges.cloudflare.com" not in directives[_directive]:
                directives[_directive].append("https://challenges.cloudflare.com")

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

    Enforce mode is default (``CSP_ENFORCE=True``). Set ``CSP_ENFORCE=0`` to
    emit ``Content-Security-Policy-Report-Only`` instead.
    """

    BYPASS_PREFIXES = ("/admin/", "/static/", "/media/")

    def __init__(self, get_response):
        self.get_response = get_response

    def _is_bypassed(self, path: str) -> bool:
        """True when ``path`` is under a bypass prefix.

        Matches the prefix root exactly AND any descendant — so the bare
        ``/admin/`` index is bypassed, not just ``/admin/<app>/...``. The
        previous ``path.rstrip('/').startswith('/admin/')`` form silently
        FAILED for the exact index (``/admin/`` → ``/admin`` which does not
        start with the trailing-slash prefix), leaking the strict CSP onto the
        admin home and breaking Unfold's Alpine.js (needs ``eval``).
        """
        for prefix in self.BYPASS_PREFIXES:
            root = prefix.rstrip("/")
            if path == root or path.startswith(root + "/"):
                return True
        return False

    def __call__(self, request):
        # Generate the per-request nonce BEFORE the view/template renders so the
        # ``csp_nonce`` context processor can expose it to inline <script nonce>
        # blocks. Must match the 'nonce-<n>' token added to the response header.
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce
        response = self.get_response(request)
        if self._is_bypassed(request.path or "/"):
            return response

        # Only apply CSP to HTML / XHTML — adding it to JSON responses is noise.
        ct = (response.get("Content-Type") or "").lower()
        if not (ct.startswith("text/html") or ct.startswith("application/xhtml")):
            return response

        policy = _build_policy(nonce=nonce)
        if getattr(settings, "CSP_ENFORCE", False):
            response["Content-Security-Policy"] = policy
        else:
            response["Content-Security-Policy-Report-Only"] = policy
        return response


def csp_nonce(request):
    """Context processor: expose the per-request CSP nonce to templates.

    Returns the nonce set by ``ContentSecurityPolicyMiddleware`` (empty string
    when the middleware did not run, e.g. in tests without it installed) so
    ``nonce="{{ csp_nonce }}"`` renders the value that the CSP header honors.
    """
    return {"csp_nonce": getattr(request, "csp_nonce", "")}


__all__ = ["ContentSecurityPolicyMiddleware", "_build_policy", "csp_nonce"]
