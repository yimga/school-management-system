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
import ipaddress
import os

from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.http.request import split_domain_port
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

#: A 1x1 transparent PNG. Its only job is to be fetched over https from this box and
#: either load or fail: a device that trusts the box CA completes the handshake and
#: decodes it, a device that does not never gets that far. Inline bytes rather than a
#: static asset because the static pipeline is one more thing that can be down at the
#: exact moment this page matters, and because a 404 and a TLS failure are
#: indistinguishable from the browser side -- so the file has to be certain to exist.
PROBE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


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


#: Substrings that identify a device family well enough to REORDER two links.
#: Checked in this order because the strings overlap: an Android user agent also
#: says Linux, and Safari on iPadOS has claimed to be a Macintosh since iPadOS 13 --
#: which is correct here, because a Mac installs the same profile the same way.
_DEVICE_TOKENS = (
    ("apple", ("iphone", "ipad", "ipod", "macintosh", "mac os x")),
    ("android", ("android",)),
    ("chromeos", ("cros",)),
    ("windows", ("windows",)),
)


def _device_hint(request: HttpRequest) -> str:
    """Which family is asking, or "" -- used ONLY to order equivalent choices.

    Never used to withhold anything. Every platform's steps stay on the page and both
    downloads stay one click apart, so a wrong guess costs a click. Sniffing that
    decides what a person is ALLOWED to see would be a different and much worse idea.
    """
    agent = (request.META.get("HTTP_USER_AGENT") or "").lower()
    if not agent:
        return ""
    for family, tokens in _DEVICE_TOKENS:
        if any(token in agent for token in tokens):
            return family
    return ""


#: Device family -> the desktop platform whose paste-in command applies. Only two
#: entries, because only two of the families HAVE a shell a person can paste into:
#: Android and ChromeOS deliberately map to nothing rather than to a guess.
_HINT_TO_DESKTOP = {"windows": "windows", "apple": "macos"}


def _install_platform(hint: str) -> str:
    """Which install command to open by default, or "" to open none.

    Known and accepted imprecision: since iPadOS 13, Safari on an iPad presents
    itself as a Macintosh with no iPad token in it at all, so an iPad lands on
    "macos" here and is offered a Terminal command it has no Terminal for. That
    costs a closed disclosure triangle and nothing else -- the profile is already
    the primary button on an Apple device, which is the route an iPad actually
    takes. Guessing WRONG about which of several visible options to open is the
    only kind of mistake a user-agent string is allowed to make on this page.
    """
    return _HINT_TO_DESKTOP.get(hint, "")


def _install_facts(request: HttpRequest, fingerprint: str) -> dict:
    """The paste-in commands, ordered so this device's own comes first.

    Absent entirely when there is no fingerprint to pin them to -- see
    ``edge_tls.install_commands``. The page then falls back to the per-OS prose,
    which is the same instruction with more steps in it, not a worse one.
    """
    commands = edge_tls.install_commands(
        request.build_absolute_uri(reverse("edge_trust_ca")), fingerprint
    )
    here = _install_platform(_device_hint(request))
    if here:
        commands = tuple(
            sorted(commands, key=lambda entry: 0 if entry.platform == here else 1)
        )
    return {"install_commands": commands, "install_platform": here}


def _verify_facts(request: HttpRequest) -> dict:
    """Can this device be TOLD whether the install worked, and at what address?

    Every branch that returns ``verify_available: False`` is a case where offering
    the check would produce a WRONG answer, not merely an unavailable one -- a failed
    probe reads as "the CA is not installed", so a probe that was never going to
    succeed is worse than no probe. Hence the box refuses to offer one when it can
    already see why it would fail.

    Deliberately reads the certificate on disk and the environment, never the
    database: this runs inside the one page on the box that guarantees it renders
    while the database is still migrating.
    """
    blank = {
        "verify_available": False,
        "verify_blocked": "",
        "probe_url": "",
        "probe_origin": "",
        "probe_address": "",
        "covered_addresses": "",
    }
    # No https at all: there is no second address to check, and telling somebody
    # their install "failed" because this box only ever serves plain http would send
    # them to re-install a CA that is already fine.
    if not edge_tls.resolve_mode().serves_https:
        return dict(blank, verify_blocked="tls_off")

    leaf_path, _key, _ca = edge_tls.certificate_paths()
    leaf = (
        edge_tls.inspect_certificate(leaf_path)
        if leaf_path and os.path.isfile(leaf_path)
        else None
    )
    if leaf is None or not leaf.readable:
        return dict(blank, verify_blocked="no_leaf")

    domain, _port = split_domain_port(request.get_host())
    bare = edge_tls.normalize_hostname(domain)
    if not bare:
        return dict(blank, verify_blocked="no_host")

    covered = ", ".join([*leaf.dns_names, *leaf.ip_addresses])
    try:
        ipaddress.ip_address(bare)
    except ValueError:
        missing = leaf.covers([bare], [])
    else:
        missing = leaf.covers([], [bare])
    if missing:
        # The box KNOWS this one. Saying "not covered" is a different instruction
        # from "install the CA" -- the CA is fine and the certificate needs
        # reissuing -- and a probe here would have failed and blamed the device.
        return dict(
            blank,
            verify_blocked="not_covered",
            probe_address=bare,
            covered_addresses=covered,
        )

    port = edge_tls.tls_port()
    origin = "https://" + edge_tls.host_header_form(bare)
    if port != edge_tls.DEFAULT_TLS_PORT:
        origin = f"{origin}:{port}"
    return {
        "verify_available": True,
        "verify_blocked": "",
        "probe_url": f"{origin}{reverse('edge_trust_probe')}",
        "probe_origin": origin,
        "probe_address": bare,
        "covered_addresses": covered,
    }


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
        "profile_url": reverse("edge_trust_profile"),
        "platform": _device_hint(request),
        "is_secure": request.is_secure(),
        # Passed EXPLICITLY. The nonce normally arrives via the `csp_nonce` context
        # processor, and this page renders with a plain dict precisely so that no
        # context processor runs -- so `{{ csp_nonce }}` would be empty here and
        # `script-src 'self'` (CSP_ENFORCE defaults to 1) would block the verify
        # script with nothing in the page to say why. Reading the attribute the
        # middleware already set costs no query and keeps that guarantee.
        "csp_nonce": getattr(request, "csp_nonce", ""),
    }
    context.update(_install_facts(request, context["fingerprint"]))
    context.update(_verify_facts(request))
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


@require_GET
@never_cache
def edge_trust_profile(request: HttpRequest) -> HttpResponse:
    """This box's CA as an Apple configuration profile.

    Same public certificate as the .crt, in the container Apple's tooling consumes.
    The media type matters as much as the bytes: served as anything else, Safari
    downloads it to a folder no profile installer looks in, and the file quietly does
    nothing rather than visibly failing.
    """
    _require_box()
    ca_path = _ca_path()
    if not ca_path:
        raise Http404("this box has not minted a certificate authority yet")
    payload = edge_tls.mobileconfig(ca_path)
    if not payload:
        # Same refusal as the .crt download and for the same reason: a profile built
        # from an unreadable CA installs on nothing, and the person finds out one
        # device at a time.
        raise Http404("this box's certificate authority cannot be read")
    response = HttpResponse(payload, content_type=edge_tls.MOBILECONFIG_CONTENT_TYPE)
    response["Content-Disposition"] = (
        f'attachment; filename="{edge_tls.MOBILECONFIG_NAME}"'
    )
    return response


@require_GET
@never_cache
def edge_trust_probe(request: HttpRequest) -> HttpResponse:
    """A 1x1 PNG that exists to be fetched over https and either load or not.

    Carries nothing and reveals nothing -- the answer is entirely in whether the
    device's TLS stack was willing to complete the handshake, which is precisely the
    question "did the CA install work" asks. Public for the same reason the CA is:
    there is nothing here to protect.
    """
    _require_box()
    return HttpResponse(PROBE_PNG, content_type="image/png")
