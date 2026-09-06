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

Admin-surface settings (separate policy — see ``_ADMIN_*`` below):

- ``CSP_ADMIN_ENABLED``            — bool, default True (emit a header on /admin/)
- ``CSP_ADMIN_ENFORCE``            — bool, default False (Report-Only; explicit opt-in)
- ``CSP_ADMIN_PATH_PREFIXES``      — tuple[str], default ("/admin/",)
- ``CSP_ADMIN_REPORT_URI``         — str, default "" (falls back to ``CSP_REPORT_URI``)
- ``CSP_ADMIN_EXTRA_SCRIPT_SRC``   — tuple[str], extra admin script-src origins
- ``CSP_ADMIN_EXTRA_STYLE_SRC``    — tuple[str], extra admin style-src origins
- ``CSP_ADMIN_EXTRA_IMG_SRC``      — tuple[str], extra admin img-src origins
- ``CSP_ADMIN_EXTRA_FONT_SRC``     — tuple[str], extra admin font-src origins
- ``CSP_ADMIN_EXTRA_CONNECT_SRC``  — tuple[str], extra admin connect-src origins
- ``CSP_ADMIN_EXTRA_FRAME_SRC``    — tuple[str], extra admin frame-src origins
- ``CSP_ADMIN_EXTRA_FRAME_ANCESTORS`` — tuple[str], extra admin frame-ancestors

Bypass: paths under ``/static/`` and ``/media/`` keep the default Django
behavior — they are asset bytes, not HTML documents, so a CSP header on them
governs nothing. ``/admin/`` is NO LONGER bypassed: it receives its own,
deliberately looser policy in Report-Only mode (see ``_build_admin_policy``).
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


# ---------------------------------------------------------------------------
# Admin-surface policy
# ---------------------------------------------------------------------------
# Until this change ``/admin/`` sat in ``BYPASS_PREFIXES`` and received NO CSP
# header at all — the highest-privilege surface on the platform was the only one
# with zero CSP telemetry, while the deployed Render services ran the main site
# in Report-Only. ``/admin/`` now gets its OWN policy, emitted Report-Only, so
# operators can LEARN the real violation set before any enforcement decision.
#
# The admin genuinely cannot run the main policy. Each addition below was
# verified against the shipped assets, not assumed:
#
# * ``'unsafe-eval'`` — Unfold bundles the STANDARD (non-CSP) Alpine.js build.
#   Its expression evaluator is literally
#   ``Object.getPrototypeOf(async function(){}).constructor`` — the
#   AsyncFunction constructor — in ``unfold/static/unfold/js/alpine/alpine.js``.
#   That is eval-equivalent and every Alpine directive dies without
#   ``'unsafe-eval'``. Alpine publishes a CSP-safe build that removes this need;
#   adopting it is the burndown this Report-Only rollout exists to justify.
# * ``'unsafe-inline'`` (script-src) — ``templates/admin/`` still carries inline
#   event-handler attributes (``onclick=`` …), which a nonce CANNOT authorize.
# * ``https://fonts.googleapis.com`` (style-src) —
#   ``templates/admin/base_site.html`` links a Google Fonts stylesheet, which the
#   main policy's ``style-src 'self' 'unsafe-inline'`` would block.
#
# ⚠️ The per-request nonce is deliberately NOT added to the admin ``script-src``.
# Per CSP3, a directive carrying BOTH a nonce and ``'unsafe-inline'`` makes
# browsers IGNORE ``'unsafe-inline'`` — which would re-block every inline handler
# above. A policy that only "passes" because nothing is enforced is exactly the
# policy that breaks the admin the moment an operator flips it, so the admin
# policy is written to be flip-safe as it stands. (The nonce is still set on the
# request, so ``nonce="{{ csp_nonce }}"`` keeps rendering; under
# ``'unsafe-inline'`` those attributes are inert but harmless.)
#
# The additions are expressed as DELTAS over ``_DEFAULT_DIRECTIVES`` rather than
# a parallel table, so any future hardening of the base policy is inherited by
# the admin policy automatically — the exact drift that once made
# ``csp_readiness.py`` report on a policy that never shipped.
_ADMIN_SCRIPT_SRC_ADDITIONS: tuple[str, ...] = ("'unsafe-inline'", "'unsafe-eval'")
_ADMIN_STYLE_SRC_ADDITIONS: tuple[str, ...] = ("https://fonts.googleapis.com",)

_ADMIN_EXTRA_SETTINGS: dict[str, str] = {
    "script-src": "CSP_ADMIN_EXTRA_SCRIPT_SRC",
    "style-src": "CSP_ADMIN_EXTRA_STYLE_SRC",
    "img-src": "CSP_ADMIN_EXTRA_IMG_SRC",
    "font-src": "CSP_ADMIN_EXTRA_FONT_SRC",
    "connect-src": "CSP_ADMIN_EXTRA_CONNECT_SRC",
    "frame-src": "CSP_ADMIN_EXTRA_FRAME_SRC",
    "frame-ancestors": "CSP_ADMIN_EXTRA_FRAME_ANCESTORS",
}


def admin_default_directives() -> dict[str, list[str]]:
    """Return the admin baseline: the main policy plus the verified admin deltas."""
    directives = {k: list(v) for k, v in _DEFAULT_DIRECTIVES.items()}
    for token in _ADMIN_SCRIPT_SRC_ADDITIONS:
        if token not in directives["script-src"]:
            directives["script-src"].append(token)
    for token in _ADMIN_STYLE_SRC_ADDITIONS:
        if token not in directives["style-src"]:
            directives["style-src"].append(token)
    return directives


def _build_admin_policy() -> str:
    """Compose the ``/admin/`` CSP header value.

    Same assembly as ``_build_policy`` (baseline + ``CSP_ADMIN_EXTRA_*``
    overrides + ``report-uri``) over the admin baseline. No nonce is applied —
    see the CSP3 nonce/'unsafe-inline' note above.

    ``report-uri`` falls back to the site-wide ``CSP_REPORT_URI`` when
    ``CSP_ADMIN_REPORT_URI`` is unset, so admin reports reach the existing sink
    (``apps/security/csp_report_view.py``) without extra configuration. The
    report's own ``document-uri`` is what distinguishes an admin violation from
    a site one.
    """
    directives = admin_default_directives()

    for directive, setting_name in _ADMIN_EXTRA_SETTINGS.items():
        for value in getattr(settings, setting_name, ()) or ():
            token = str(value).strip()
            if token and token not in directives.setdefault(directive, []):
                directives[directive].append(token)

    parts = [f"{d} {' '.join(s)}" for d, s in directives.items() if s]

    report_uri = (getattr(settings, "CSP_ADMIN_REPORT_URI", "") or "").strip()
    if not report_uri:
        report_uri = (getattr(settings, "CSP_REPORT_URI", "") or "").strip()
    if report_uri:
        parts.append(f"report-uri {report_uri}")

    return "; ".join(parts)


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

    Two surfaces, two policies:

    * **Site** — ``_build_policy`` with the per-request nonce. Enforce mode is
      default (``CSP_ENFORCE=True``); ``CSP_ENFORCE=0`` emits
      ``Content-Security-Policy-Report-Only`` instead. Unchanged by the admin
      rollout.
    * **Admin** (``CSP_ADMIN_PATH_PREFIXES``, default ``/admin/``) —
      ``_build_admin_policy``, emitted **Report-Only** unless the operator sets
      the separate ``CSP_ADMIN_ENFORCE=1`` opt-in. ``CSP_ENFORCE`` does NOT
      promote the admin policy to enforcing: the site switch must never flip the
      admin surface as a side effect.

    ``/static/`` and ``/media/`` stay bypassed — asset bytes, not HTML
    documents.
    """

    BYPASS_PREFIXES = ("/static/", "/media/")
    ADMIN_PREFIXES = ("/admin/",)

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _matches(path: str, prefixes) -> bool:
        """True when ``path`` is the exact root of a prefix, or a descendant.

        Matching the root exactly AND any descendant is load-bearing: an earlier
        ``path.rstrip('/').startswith('/admin/')`` form silently FAILED for the
        exact index (``/admin/`` → ``/admin``, which does not start with the
        trailing-slash prefix). A lookalike sibling such as ``/administrators/``
        must NOT match ``/admin/``, which is why the comparison is
        root-or-root-plus-slash rather than a bare ``startswith``.
        """
        for prefix in prefixes:
            root = str(prefix).rstrip("/")
            if not root:
                continue
            if path == root or path.startswith(root + "/"):
                return True
        return False

    def _is_bypassed(self, path: str) -> bool:
        """True for ``/static/`` and ``/media/`` — asset bytes, never HTML."""
        return self._matches(path, self.BYPASS_PREFIXES)

    def _admin_prefixes(self) -> tuple[str, ...]:
        """Admin path prefixes, operator-overridable via settings.

        An EMPTY override falls back to the class default rather than meaning
        "no admin surface". Honouring an empty list would drop ``/admin/``
        through to the site policy — which can be ENFORCING — and break the
        admin outright. Use ``CSP_ADMIN_ENABLED=0`` to opt the admin out of CSP;
        this knob only relocates the surface.
        """
        configured = getattr(settings, "CSP_ADMIN_PATH_PREFIXES", None) or ()
        cleaned = tuple(str(p).strip() for p in configured if str(p).strip())
        return cleaned or self.ADMIN_PREFIXES

    def _is_admin(self, path: str) -> bool:
        """True when ``path`` is on the admin surface (its own policy applies)."""
        return self._matches(path, self._admin_prefixes())

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

        if self._is_admin(request.path or "/"):
            # Admin surface: its own policy, Report-Only unless the operator
            # explicitly opts in via CSP_ADMIN_ENFORCE. Deliberately does NOT
            # consult CSP_ENFORCE — flipping the site to enforcing must not drag
            # the admin along with it.
            if not getattr(settings, "CSP_ADMIN_ENABLED", True):
                return response
            admin_policy = _build_admin_policy()
            if getattr(settings, "CSP_ADMIN_ENFORCE", False):
                response["Content-Security-Policy"] = admin_policy
            else:
                response["Content-Security-Policy-Report-Only"] = admin_policy
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


__all__ = [
    "ContentSecurityPolicyMiddleware",
    "_build_admin_policy",
    "_build_policy",
    "admin_default_directives",
    "csp_nonce",
]
