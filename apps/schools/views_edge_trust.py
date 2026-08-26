"""The box publishes its own certificate authority, so nobody carries a file around.

WHY THIS EXISTS. Installing a box CA used to mean: copy ``box-ca-bundle.p12`` and
``box-ca.crt`` off the box by hand -- VS Code over SSH, or a USB stick -- then get the
``.crt`` onto every phone, tablet and laptop in the building. Thirty devices, one
file, passed around. Every step of that is a place to get it wrong, and one of the
ways to get it wrong is to hand somebody the ``.p12`` (which carries the CA PRIVATE
KEY) instead of the ``.crt``.

A certificate authority's certificate is PUBLIC. Publishing it is what a certificate
authority is for -- every public CA on the internet does exactly this. So the box
serves its own, at a URL a person can walk to, with a QR code so a phone does not
have to type an IP address.

THREE THINGS THIS FILE IS CAREFUL ABOUT.

1. IT MUST WORK OVER PLAIN HTTP. You are installing the CA precisely BECAUSE https
   warns; redirect this page to https and it is a chicken-and-egg that leaves people
   clicking through the warning they were meant to be fixing. ``SECURE_REDIRECT_EXEMPT``
   in config/settings.py carries ``^edge/trust/`` for this reason and no other.

2. THE PRIVATE KEY IS NOT REACHABLE. The download reads ONE path, taken from
   ``edge_tls.certificate_paths()``, never from the request. There is no parameter to
   traverse and no branch that could reach ``ca.key`` or the ``.p12`` bundle.

3. PLAIN HTTP MEANS THE PAGE ITSELF COULD BE SUBSTITUTED. Someone on the LAN could
   answer in the box's place and offer their own CA -- and a CA you install is a CA
   that can impersonate anything. That risk is not closed by code; it is closed by a
   person comparing the fingerprint shown here against the one the box prints on its
   own console (``manage.py edge_tls``). So the fingerprint is the loudest thing on
   the page, and the page says what it is for.

Box-only. A hosted deployment has no box CA, and a control-plane host publishing
something called a certificate authority is a phishing surface, so this 404s
anywhere ``is_sovereign_single_tenant_box()`` is false.
"""

from __future__ import annotations

import base64
import io
import os

from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.schools import edge_tls
from apps.schools.middleware import is_sovereign_single_tenant_box

#: What a phone needs to see to open its certificate installer rather than a text
#: viewer. ``application/x-x509-ca-cert`` is the long-standing spelling every mobile
#: OS still recognises; serving ``text/plain`` here is why a downloaded CA sometimes
#: just opens as gibberish.
CA_CONTENT_TYPE = "application/x-x509-ca-cert"

#: The filename the device is offered. Deliberately names the box, not "ca.crt", so a
#: person with three of these in a downloads folder can tell them apart.
CA_DOWNLOAD_NAME = "box-ca.crt"


def _require_box() -> None:
    if not is_sovereign_single_tenant_box():
        raise Http404("trust enrolment is a sovereign-box surface")


def _ca_path() -> str:
    """The CA certificate path, or "" when this box has not minted one yet."""
    _cert, _key, ca = edge_tls.certificate_paths()
    return ca if ca and os.path.isfile(ca) else ""


def _qr_data_uri(text: str) -> str:
    """A QR PNG as a data: URI, or "" if it cannot be made.

    Inlined rather than served as a second URL so the page is one request and works
    with no cache, no static pipeline and no network -- which is the situation a
    school is in when they are doing this.

    Never fatal: a page without a QR is a page you can still type the URL into, and a
    school locked out of trust enrolment because an image failed to render would be a
    poor trade.
    """
    try:
        import qrcode

        buffer = io.BytesIO()
        qrcode.make(text).save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except (ImportError, OSError, ValueError):
        return ""


def _usable(facts) -> bool:
    """A CA is only usable here if its FINGERPRINT can be shown.

    Not "does the file exist". A truncated or corrupt ca.crt exists happily, and
    rendering it as a normal CA puts an empty fingerprint box next to a live
    Download button. Comparing that fingerprint against the box console is the whole
    of the security on this page -- an empty box reads as "just click Download",
    which is the exact behaviour the page exists to prevent.
    """
    return bool(facts is not None and facts.readable and facts.fingerprint)


@require_GET
@never_cache
def edge_trust_page(request: HttpRequest) -> HttpResponse:
    """Instructions, fingerprint and QR for installing this box's CA."""
    _require_box()
    ca_path = _ca_path()
    facts = edge_tls.inspect_certificate(ca_path) if ca_path else None
    # The QR points at THIS page, not straight at the download. A phone that lands
    # here gets the platform-specific step it is about to need -- Android's "CA
    # certificate" entry, iOS's second Trust Settings screen -- and those are the
    # steps people skip, not the download.
    page_url = request.build_absolute_uri(reverse("edge_trust"))
    # Rendered WITHOUT a RequestContext, deliberately. `render()` would run every
    # context processor -- brand payload, tenant runtime, theme, feature flags --
    # each of which queries the database. This page has no chrome and reads none of
    # them, and the moment it is most needed is the moment those are least reliable:
    # a box that has just booted, is still migrating, and is being reached by a
    # device that cannot use https until this page works. One template, one dict, no
    # database.
    context = {
        "has_ca": _usable(facts),
        # Present but unparseable is its OWN state: "run the bootstrap" is wrong
        # advice for a file that is already there, and would send someone looking in
        # the wrong place.
        "ca_unreadable": bool(ca_path) and not _usable(facts),
        "ca_error": getattr(facts, "error", ""),
        "facts": facts,
        "fingerprint": getattr(facts, "fingerprint", ""),
        "not_after": getattr(facts, "not_after", ""),
        "page_url": page_url,
        "qr_data_uri": _qr_data_uri(page_url),
        "download_url": reverse("edge_trust_ca"),
        "is_secure": request.is_secure(),
    }
    return HttpResponse(render_to_string("schools/edge_trust.html", context))


@require_GET
@never_cache
def edge_trust_ca(request: HttpRequest) -> FileResponse:
    """Serve the CA certificate itself. Public by design; the key is not here."""
    _require_box()
    ca_path = _ca_path()
    if not ca_path:
        raise Http404("this box has not minted a certificate authority yet")
    # Refuse rather than hand over bytes no device can install. A person who
    # downloads a broken CA does not find out here -- they find out on the fourth
    # device, and they blame the phone. This CA was minted by this same code, so
    # "cannot parse" means broken, not exotic.
    if not _usable(edge_tls.inspect_certificate(ca_path)):
        raise Http404("this box's certificate authority cannot be read")
    response = FileResponse(
        open(ca_path, "rb"),
        content_type=CA_CONTENT_TYPE,
        as_attachment=True,
        filename=CA_DOWNLOAD_NAME,
    )
    return response
