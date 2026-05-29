"""v4.00.36 — SAML 2.0 SP metadata endpoint.

Scope (v4.00.36):
* `GET /sso/saml/metadata/` returns spec-compliant XML metadata for the
  RunMyCampus service provider. ACS POST handler is honest-stub: it
  receives the SAMLResponse and logs the receipt for operator visibility
  but does NOT yet decode + validate the assertion (full validation
  requires a SAML library + per-IdP signing certs, which is deferred to
  v4.00.37+ pending integration partner confirmation).

The metadata XML carries:
* EntityDescriptor with the entity ID from settings
* SPSSODescriptor with WantAssertionsSigned=true
* AssertionConsumerService binding to HTTP-POST at /sso/saml/acs/
* SingleLogoutService at /sso/saml/sls/
* NameIDFormat = persistent + emailAddress
* KeyDescriptor with the public certificate from
  ``RMC_SAML_SP_CERT_PEM`` env (PEM body, base64-decoded into the XML;
  a clearly-marked dev placeholder is used when unset).

Honest deferred: full ACS validation w/ signature verification; IdP
metadata import; encrypted assertions; SLO request signing.
"""
from __future__ import annotations

import logging
import os
import re

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


# Dev placeholder so the metadata response is parseable; production MUST
# set RMC_SAML_SP_CERT_PEM. The cert body is the b64 chunk between the
# PEM header / footer.
_DEV_PLACEHOLDER_CERT_B64 = (
    "MIIDazCCAlOgAwIBAgIUDevPlaceholderCertificateForRMCSAMLDevModeOnly1234"
    "RNRMC0xMTAvBgNVBAoMKERldmVsb3BtZW50UnVuTXlDYW1wdXNQbGFjZWhvbGRlckNl"
    "cnQwHhcNMjYwNTI5MDAwMDAwWhcNMzYwNTI5MDAwMDAwWjBmMQswCQYDVQQGEwJVUzEL"
    "PLACEHOLDER-CERT-CONTENT-NOT-FOR-PRODUCTION-USE-RMCSAMLDEV-V40036-"
    "AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKKLLLLMMMMNNNNOOOOPPPPQQQQRRRRSSSS"
)


def _cert_body_b64() -> str:
    """Return the PEM cert body (no header / footer) for X509Certificate."""
    pem = (
        getattr(settings, "RMC_SAML_SP_CERT_PEM", "")
        or os.environ.get("RMC_SAML_SP_CERT_PEM", "")
        or ""
    )
    if not pem.strip():
        return _DEV_PLACEHOLDER_CERT_B64
    # Strip PEM markers + whitespace.
    cleaned = re.sub(r"-----[A-Z ]+-----", "", pem)
    return re.sub(r"\s+", "", cleaned)


def _entity_id() -> str:
    return str(
        getattr(settings, "RMC_SAML_SP_ENTITY_ID", "")
        or os.environ.get("RMC_SAML_SP_ENTITY_ID", "")
        or "https://runmycampus.com/sso/saml"
    )


def _base_url(request: HttpRequest) -> str:
    explicit = (
        getattr(settings, "RMC_SAML_SP_BASE_URL", "")
        or os.environ.get("RMC_SAML_SP_BASE_URL", "")
        or ""
    ).rstrip("/")
    if explicit:
        return explicit
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{request.get_host()}".rstrip("/")


@require_http_methods(["GET"])
def metadata(request):
    """Serve XML metadata at ``/sso/saml/metadata/``."""
    entity_id = _entity_id()
    base = _base_url(request)
    cert_b64 = _cert_body_b64()
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"'
        f' entityID="{entity_id}">\n'
        '  <md:SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true"'
        '   protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">\n'
        '    <md:KeyDescriptor use="signing">\n'
        '      <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">\n'
        '        <ds:X509Data>\n'
        f'          <ds:X509Certificate>{cert_b64}</ds:X509Certificate>\n'
        '        </ds:X509Data>\n'
        '      </ds:KeyInfo>\n'
        '    </md:KeyDescriptor>\n'
        '    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"'
        f'     Location="{base}/sso/saml/sls/"/>\n'
        '    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>\n'
        '    <md:NameIDFormat>urn:oasis:names:tc:SAML:2.0:nameid-format:persistent</md:NameIDFormat>\n'
        '    <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"'
        f'     Location="{base}/sso/saml/acs/" index="0" isDefault="true"/>\n'
        '  </md:SPSSODescriptor>\n'
        '</md:EntityDescriptor>\n'
    )
    return HttpResponse(xml, content_type="application/samlmetadata+xml; charset=utf-8")


@csrf_exempt
@require_http_methods(["POST"])
def acs(request):
    """ACS endpoint — accepts the SAMLResponse and logs receipt.

    Full assertion validation is deferred. We surface receipt of the
    POST so operators can confirm the round-trip without writing any
    session yet — production sign-in needs the validator wave.
    """
    raw = request.POST.get("SAMLResponse") or ""
    relay = request.POST.get("RelayState") or ""
    if not raw:
        return JsonResponse({"success": False, "error": "missing_saml_response"}, status=400)
    logger.info("saml acs: received SAMLResponse (len=%s, relay_len=%s)", len(raw), len(relay))
    return JsonResponse({
        "success": True,
        "stage": "received",
        "validation": "deferred-v4.00.37",
        "response_length": len(raw),
        "relay_state_length": len(relay),
    })


@require_http_methods(["GET", "POST"])
def sls(request):
    """SLO endpoint stub — logs + acks; full SLO flow deferred."""
    logger.info("saml sls: logout request received (method=%s)", request.method)
    return JsonResponse({"success": True, "stage": "logout-acknowledged"})
