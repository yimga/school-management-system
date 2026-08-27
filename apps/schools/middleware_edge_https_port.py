"""Send the web port's HTTPS redirect somewhere that actually answers.

``SECURE_SSL_REDIRECT`` makes Django bounce plain HTTP to https, and it builds the
target from ``request.get_host()`` -- which carries the PORT. On a box published on
``WEB_PORT`` (10000 by default) that yields ``https://<host>:10000/``, and nothing
speaks TLS there: the terminator listens on ``EDGE_TLS_HTTPS_PORT``. The browser
opens a TLS connection to a plain-HTTP socket and waits until it gives up, so the
person sees ERR_TIMED_OUT with nothing on screen to explain it.

Measured on a live box, not reasoned about. Same host, same path, two ports::

    http://<box>:<web-port>/authentication/login/
      -> 301 https://<box>:<web-port>/authentication/login/   (hangs)
    http://<box>/authentication/login/
      -> 302 https://<box>/authentication/login/              (200)

Port 80 was right the whole time because Caddy, not Django, writes that one. And
``:10000`` is not a stray address a box could simply stop publishing: it is the
trust-enrolment URL printed by four separate surfaces, so a device meets the box
there before it trusts anything.

``SECURE_SSL_HOST`` cannot fix this. It replaces the whole host, so a box answering
at an IP and three names would send every visitor to whichever single name was
pinned -- and on a LAN the IP visitors are the majority.

So this corrects only WHERE, never WHETHER. SecurityMiddleware keeps ownership of
the redirect decision, which matters because ``^edge/trust/`` sits in
``SECURE_REDIRECT_EXEMPT`` for a load-bearing reason: a device reaches that page
BECAUSE it does not trust the box yet.

Ordering: this must be listed BEFORE SecurityMiddleware. Django runs the response
phase in reverse, so the earlier entry is the one that sees the redirect the later
one produced.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from apps.schools import edge_tls


def retarget_location(location: str) -> str:
    """Return `location` with the dead web port swapped for the terminator's.

    Anything that is not "https, on exactly the published web port" is returned
    untouched -- including a plain-HTTP redirect, a bare path, and a port this box
    knows nothing about. Narrow on purpose: the failure this fixes is specific, and
    a middleware that rewrites other people's Location headers is a worse bug than
    the one it came to fix.
    """
    if not location.startswith("https://"):
        return location
    parsed = urlsplit(location)
    try:
        port = parsed.port
    except ValueError:
        # A malformed authority. Not ours to interpret, and not ours to break.
        return location
    if port is None or str(port) != str(edge_tls.web_port()):
        return location
    host = parsed.hostname or ""
    if not host:
        return location
    if ":" in host:
        # urlsplit strips the brackets an IPv6 literal must carry in a URL.
        host = "[%s]" % host
    tls = str(edge_tls.tls_port())
    netloc = host if tls == "443" else "%s:%s" % (host, tls)
    return urlunsplit(("https", netloc, parsed.path, parsed.query, parsed.fragment))


class EdgeHttpsPortRedirectMiddleware:
    """Rewrite an https redirect that points at the plain-HTTP web port."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if response.status_code in (301, 302, 307, 308):
                location = response.headers.get("Location") or ""
                fixed = retarget_location(location)
                if fixed != location:
                    response["Location"] = fixed
        except Exception:  # noqa: BLE001
            # Never turn a working page into a 500 over a redirect target. A box in
            # a school office has no one to read the traceback.
            return response
        return response
