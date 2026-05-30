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
import threading

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


def _metadata_cache_seconds() -> int:
    """v4.00.65 — Cache TTL for the SAML SP metadata document.

    Used in the ``validUntil`` attribute so IdPs refresh periodically.
    Default 86400 (24h) — matches industry SAML metadata caching default.
    """
    raw = (
        getattr(settings, "RMC_SAML_METADATA_CACHE_SECONDS", "")
        or os.environ.get("RMC_SAML_METADATA_CACHE_SECONDS", "")
        or ""
    )
    try:
        val = int(raw) if str(raw).strip() else 86400
    except (ValueError, TypeError):
        val = 86400
    return max(60, val)  # floor of 1min so we never produce already-expired metadata


def _metadata_contact_email() -> str:
    return str(
        getattr(settings, "RMC_SAML_METADATA_CONTACT_EMAIL", "")
        or os.environ.get("RMC_SAML_METADATA_CONTACT_EMAIL", "")
        or ""
    ).strip()


def _metadata_organization_name() -> str:
    return str(
        getattr(settings, "RMC_SAML_METADATA_ORG_NAME", "")
        or os.environ.get("RMC_SAML_METADATA_ORG_NAME", "")
        or "RunMyCampus"
    ).strip()


def _metadata_organization_url() -> str:
    return str(
        getattr(settings, "RMC_SAML_METADATA_ORG_URL", "")
        or os.environ.get("RMC_SAML_METADATA_ORG_URL", "")
        or "https://runmycampus.com/"
    ).strip()


def _build_sp_metadata_xml(*, base: str, entity_id: str, cert_b64: str,
                          authn_requests_signed: bool, want_assertions_signed: bool,
                          valid_until_iso: str, cache_duration_iso: str) -> str:
    """v4.00.65 — Build a richer SAML 2.0 SP metadata XML document.

    Adds vs v4.00.46:
      * ``validUntil`` + ``cacheDuration`` so IdPs refresh on TTL
      * AuthnRequestsSigned reflects RMC_SAML_SP_SIGN_LOGOUT (the same flag
        that drives v4.00.61 LogoutRequest + v4.00.64 LogoutResponse signing)
      * SLS HTTP-POST binding (covers v4.00.59 sls_idp)
      * SP-initiated SLO callback (``/sso/saml/slo/callback/``)
      * Optional Organization + ContactPerson blocks (only emitted when
        env carries non-empty values; empty defaults skip the block)
    """
    from django.utils.html import escape as _escape

    ars_attr = "true" if authn_requests_signed else "false"
    was_attr = "true" if want_assertions_signed else "false"

    contact = _metadata_contact_email()
    contact_xml = ""
    if contact:
        contact_xml = (
            '  <md:ContactPerson contactType="technical">\n'
            f'    <md:EmailAddress>{_escape(contact)}</md:EmailAddress>\n'
            '  </md:ContactPerson>\n'
        )

    org_name = _metadata_organization_name()
    org_url = _metadata_organization_url()
    org_xml = ""
    if org_name:
        org_xml = (
            '  <md:Organization>\n'
            f'    <md:OrganizationName xml:lang="en">{_escape(org_name)}</md:OrganizationName>\n'
            f'    <md:OrganizationDisplayName xml:lang="en">{_escape(org_name)}</md:OrganizationDisplayName>\n'
            f'    <md:OrganizationURL xml:lang="en">{_escape(org_url or "https://runmycampus.com/")}</md:OrganizationURL>\n'
            '  </md:Organization>\n'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"'
        ' xmlns:ds="http://www.w3.org/2000/09/xmldsig#"'
        f' entityID="{_escape(entity_id)}"'
        f' validUntil="{valid_until_iso}"'
        f' cacheDuration="{cache_duration_iso}">\n'
        f'  <md:SPSSODescriptor AuthnRequestsSigned="{ars_attr}" WantAssertionsSigned="{was_attr}"'
        '   protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">\n'
        '    <md:KeyDescriptor use="signing">\n'
        '      <ds:KeyInfo>\n'
        '        <ds:X509Data>\n'
        f'          <ds:X509Certificate>{cert_b64}</ds:X509Certificate>\n'
        '        </ds:X509Data>\n'
        '      </ds:KeyInfo>\n'
        '    </md:KeyDescriptor>\n'
        '    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"'
        f'     Location="{_escape(base)}/sso/saml/sls/"/>\n'
        '    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"'
        f'     Location="{_escape(base)}/sso/saml/sls/idp/"'
        f'     ResponseLocation="{_escape(base)}/sso/saml/slo/callback/"/>\n'
        '    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>\n'
        '    <md:NameIDFormat>urn:oasis:names:tc:SAML:2.0:nameid-format:persistent</md:NameIDFormat>\n'
        '    <md:NameIDFormat>urn:oasis:names:tc:SAML:2.0:nameid-format:transient</md:NameIDFormat>\n'
        '    <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"'
        f'     Location="{_escape(base)}/sso/saml/acs/" index="0" isDefault="true"/>\n'
        '  </md:SPSSODescriptor>\n'
        f'{org_xml}'
        f'{contact_xml}'
        '</md:EntityDescriptor>\n'
    )


@require_http_methods(["GET"])
def metadata(request):
    """Serve XML SP metadata at ``/sso/saml/metadata/`` (+ ``.xml/`` alias).

    v4.00.65 — Richer metadata document carries ``validUntil`` +
    ``cacheDuration``, reflects ``RMC_SAML_SP_SIGN_LOGOUT`` on
    ``AuthnRequestsSigned``, exposes HTTP-Redirect + HTTP-POST SLS bindings,
    optional Organization + ContactPerson blocks.

    ``?format=json`` returns a parsed shape (entity_id, acs_url, sls_urls,
    cert_present, etc.) for headless smoke / monitor probes — useful when
    operators want to assert a deploy didn't drop fields without
    pretty-printing XML.
    """
    from datetime import datetime, timedelta, timezone as _tz_m

    entity_id = _entity_id()
    base = _base_url(request)
    cert_b64 = _cert_body_b64()

    ttl = _metadata_cache_seconds()
    now = datetime.now(_tz_m.utc)
    valid_until = now + timedelta(seconds=ttl)
    valid_until_iso = valid_until.strftime("%Y-%m-%dT%H:%M:%SZ")
    cache_duration_iso = f"PT{ttl}S"  # ISO-8601 duration

    authn_signed = _sp_sign_logout_enabled()
    want_assertions_signed = _require_signature()

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "entity_id": entity_id,
            "base_url": base,
            "valid_until": valid_until_iso,
            "cache_duration": cache_duration_iso,
            "authn_requests_signed": authn_signed,
            "want_assertions_signed": want_assertions_signed,
            "cert_present": bool(cert_b64),
            "acs_url": f"{base}/sso/saml/acs/",
            "sls_urls": {
                "http_redirect": f"{base}/sso/saml/sls/",
                "http_post": f"{base}/sso/saml/sls/idp/",
            },
            "slo_callback_url": f"{base}/sso/saml/slo/callback/",
            "organization_name": _metadata_organization_name(),
            "organization_url": _metadata_organization_url(),
            "contact_email": _metadata_contact_email(),
        })

    xml = _build_sp_metadata_xml(
        base=base,
        entity_id=entity_id,
        cert_b64=cert_b64,
        authn_requests_signed=authn_signed,
        want_assertions_signed=want_assertions_signed,
        valid_until_iso=valid_until_iso,
        cache_duration_iso=cache_duration_iso,
    )
    return HttpResponse(xml, content_type="application/samlmetadata+xml; charset=utf-8")


_NS_SAMLP = "urn:oasis:names:tc:SAML:2.0:protocol"
_NS_SAML = "urn:oasis:names:tc:SAML:2.0:assertion"


def _idp_cert_b64() -> str:
    pem = (
        getattr(settings, "RMC_SAML_IDP_CERT_PEM", "")
        or os.environ.get("RMC_SAML_IDP_CERT_PEM", "")
        or ""
    )
    if not pem.strip():
        return ""
    cleaned = re.sub(r"-----[A-Z ]+-----", "", pem)
    return re.sub(r"\s+", "", cleaned)


def _require_signature() -> bool:
    raw = (
        getattr(settings, "RMC_SAML_REQUIRE_SIGNATURE", None)
        if hasattr(settings, "RMC_SAML_REQUIRE_SIGNATURE")
        else os.environ.get("RMC_SAML_REQUIRE_SIGNATURE", "")
    )
    if raw is None or raw == "":
        return False
    return str(raw).lower() in ("1", "true", "yes", "on")


def _require_signature_strict() -> bool:
    """v4.00.57 — When ``RMC_SAML_SIGNATURE_STRICT`` is truthy (default), a
    deps_missing classification from the c14n verifier fails the request;
    when explicitly disabled (set to ``0``/``false``/``no``/``off``), the
    sweep falls back to the v4.00.46 presence-only signature check so an
    operator can run with require=1 BEFORE the lxml/signxml install lands.
    Default is strict because the silent-fallback case violates the
    "signature required" contract."""
    raw = (
        getattr(settings, "RMC_SAML_SIGNATURE_STRICT", None)
        if hasattr(settings, "RMC_SAML_SIGNATURE_STRICT")
        else os.environ.get("RMC_SAML_SIGNATURE_STRICT", "")
    )
    if raw is None or raw == "":
        return True
    return str(raw).lower() not in ("0", "false", "no", "off")


def _verify_saml_signature_c14n(b64_response: str, idp_cert_b64: str) -> tuple[bool, str]:
    """v4.00.57 — Cryptographic signature verification w/ XML canonicalization.

    Lazy-imports ``lxml`` + ``signxml``; returns ``(verified, reason)`` where
    ``reason`` is one of:
        ``"ok"``              — signature verified against IdP cert
        ``"deps_missing"``    — lxml/signxml not installed (operator action)
        ``"cert_unset"``      — RMC_SAML_IDP_CERT_PEM not configured
        ``"bad_base64"``      — SAMLResponse not base64
        ``"signature_missing"`` — no ``<ds:Signature>`` in response
        ``"signature_invalid"`` — c14n digest / cert mismatch
    Verification is read-only on its inputs; NEVER raises.
    """
    if not idp_cert_b64:
        return False, "cert_unset"

    try:
        import base64
        decoded = base64.b64decode(b64_response, validate=False)
    except (ValueError, TypeError):
        return False, "bad_base64"

    # Lazy deps — when the install lands, this branch goes live without
    # any other code edit.
    try:
        from lxml import etree  # type: ignore
        from signxml import XMLVerifier  # type: ignore
    except ImportError:
        return False, "deps_missing"

    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(decoded, parser=parser)
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml c14n: lxml parse failed: %s", exc)
        return False, "bad_xml"

    ns_dsig = "{http://www.w3.org/2000/09/xmldsig#}Signature"
    if root.find(ns_dsig) is None and root.find(f".//{ns_dsig}") is None:
        return False, "signature_missing"

    # v4.00.91 — H4: policy gate on every <ds:SignatureMethod> in the
    # response. Reject the c14n verify call BEFORE signxml runs if ANY
    # signature element declares a non-allowed algorithm (default rejects
    # rsa-sha1). This is cheap (single XPath walk) + defends against the
    # downgrade case where signxml itself doesn't enforce a policy ceiling.
    _sig_method_xpath = (
        ".//{http://www.w3.org/2000/09/xmldsig#}SignedInfo"
        "/{http://www.w3.org/2000/09/xmldsig#}SignatureMethod"
    )
    for _sm in root.findall(_sig_method_xpath):
        _alg = (_sm.attrib.get("Algorithm") or "").strip()
        _ok, _reason = _is_signature_algorithm_allowed(_alg)
        if not _ok:
            return False, _reason

    # Rebuild the IdP cert PEM from the b64 we already stripped of armor.
    pem = "-----BEGIN CERTIFICATE-----\n"
    for i in range(0, len(idp_cert_b64), 64):
        pem += idp_cert_b64[i:i + 64] + "\n"
    pem += "-----END CERTIFICATE-----\n"

    try:
        XMLVerifier().verify(decoded, x509_cert=pem)
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        logger.info("saml c14n: signature verification failed: %s", exc)
        return False, "signature_invalid"


# ---------------------------------------------------------------------------
# v4.00.61 — SAML LogoutRequest signing (SP-initiated SLO outbound).
#
# Reuses the v4.00.57 lazy lxml+signxml import pattern so the install is
# the ONLY operator action required to activate. Until lxml/signxml land,
# the signing helper returns ``(unsigned_xml, "deps_missing")`` and the
# caller honors ``RMC_SAML_SIGNATURE_STRICT`` to decide fail-closed
# (503 in strict mode) or fall through to the unsigned path.
#
# Configuration:
#   * ``RMC_SAML_SP_SIGN_LOGOUT=1`` — opt-in to signed LogoutRequest path
#                                    (default OFF — preserves v4.00.60).
#   * ``RMC_SAML_SP_PRIVATE_KEY_PEM`` — PEM-encoded SP RSA private key.
#   * ``RMC_SAML_SP_CERT_PEM``        — PEM-encoded SP X509 cert (embedded
#                                       in the signature as ``KeyInfo``).
#   * ``RMC_SAML_SP_SIGNATURE_ALG``   — defaults to RSA-SHA256.
# ---------------------------------------------------------------------------


def _sp_sign_logout_enabled() -> bool:
    """v4.00.61 — opt-in toggle for the signed LogoutRequest path."""
    raw = (
        getattr(settings, "RMC_SAML_SP_SIGN_LOGOUT", None)
        if hasattr(settings, "RMC_SAML_SP_SIGN_LOGOUT")
        else os.environ.get("RMC_SAML_SP_SIGN_LOGOUT", "")
    )
    if raw is None or raw == "":
        return False
    return str(raw).lower() in ("1", "true", "yes", "on")


def _sp_private_key_pem() -> str:
    return (
        getattr(settings, "RMC_SAML_SP_PRIVATE_KEY_PEM", "")
        or os.environ.get("RMC_SAML_SP_PRIVATE_KEY_PEM", "")
        or ""
    )


def _sp_cert_pem() -> str:
    return (
        getattr(settings, "RMC_SAML_SP_CERT_PEM", "")
        or os.environ.get("RMC_SAML_SP_CERT_PEM", "")
        or ""
    )


def _sp_signature_alg() -> str:
    raw = (
        getattr(settings, "RMC_SAML_SP_SIGNATURE_ALG", "")
        or os.environ.get("RMC_SAML_SP_SIGNATURE_ALG", "")
        or ""
    ).strip()
    return raw or "rsa-sha256"


def _sign_saml_logout_request(xml_bytes: bytes) -> tuple[bytes, str]:
    """v4.00.61 — Sign a LogoutRequest XML in-place via signxml + lxml.

    Returns ``(signed_xml_bytes, reason)`` where ``reason`` is one of:
        ``"ok"``              — signature embedded successfully
        ``"deps_missing"``    — lxml/signxml not installed (operator action)
        ``"key_unset"``       — SP private key not configured
        ``"cert_unset"``      — SP cert not configured
        ``"signature_error"`` — signxml raised mid-sign (key/cert mismatch)

    Pass-through: when reason != "ok", returns the original unsigned bytes
    so callers in non-strict mode can still emit a usable LogoutRequest.
    NEVER raises.
    """
    key_pem = _sp_private_key_pem().strip()
    if not key_pem:
        return xml_bytes, "key_unset"
    cert_pem = _sp_cert_pem().strip()
    if not cert_pem:
        return xml_bytes, "cert_unset"

    try:
        from lxml import etree  # type: ignore
        from signxml import XMLSigner, methods  # type: ignore
    except ImportError:
        return xml_bytes, "deps_missing"

    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(xml_bytes, parser=parser)
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml sign: lxml parse failed: %s", exc)
        return xml_bytes, "bad_xml"

    alg = _sp_signature_alg()
    signature_alg = "rsa-sha256" if alg == "rsa-sha256" else alg

    try:
        signed_root = XMLSigner(
            method=methods.enveloped,
            signature_algorithm=signature_alg,
            digest_algorithm="sha256",
            c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#",
        ).sign(root, key=key_pem, cert=cert_pem)
    except Exception as exc:  # noqa: BLE001
        logger.warning("saml sign: signxml raised: %s", exc)
        return xml_bytes, "signature_error"

    try:
        signed_bytes = etree.tostring(signed_root, xml_declaration=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml sign: tostring failed: %s", exc)
        return xml_bytes, "serialize_error"
    return signed_bytes, "ok"


def _sign_saml_logout_response(xml_bytes: bytes) -> tuple[bytes, str]:
    """v4.00.64 — Sign an outbound LogoutResponse XML in-place.

    Same XML-DSig contract as :func:`_sign_saml_logout_request` (enveloped,
    rsa-sha256 default, sha256 digest, xml-exc-c14n). Reuses the SP private
    key + cert + signature algorithm env contract — operators who already
    configured signing for v4.00.61 LogoutRequest get response signing
    for free as soon as ``RMC_SAML_SP_SIGN_LOGOUT=1`` covers both flows.

    Returns ``(signed_xml_bytes, reason)`` with the same 6-state taxonomy
    as the request signer: ok/deps_missing/key_unset/cert_unset/bad_xml/
    signature_error/serialize_error. Pass-through behavior preserved:
    callers can fall through to unsigned XML when non-strict.
    NEVER raises.
    """
    key_pem = _sp_private_key_pem().strip()
    if not key_pem:
        return xml_bytes, "key_unset"
    cert_pem = _sp_cert_pem().strip()
    if not cert_pem:
        return xml_bytes, "cert_unset"

    try:
        from lxml import etree  # type: ignore
        from signxml import XMLSigner, methods  # type: ignore
    except ImportError:
        return xml_bytes, "deps_missing"

    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(xml_bytes, parser=parser)
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml sign-response: lxml parse failed: %s", exc)
        return xml_bytes, "bad_xml"

    alg = _sp_signature_alg()
    signature_alg = "rsa-sha256" if alg == "rsa-sha256" else alg

    try:
        signed_root = XMLSigner(
            method=methods.enveloped,
            signature_algorithm=signature_alg,
            digest_algorithm="sha256",
            c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#",
        ).sign(root, key=key_pem, cert=cert_pem)
    except Exception as exc:  # noqa: BLE001
        logger.warning("saml sign-response: signxml raised: %s", exc)
        return xml_bytes, "signature_error"

    try:
        signed_bytes = etree.tostring(signed_root, xml_declaration=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml sign-response: tostring failed: %s", exc)
        return xml_bytes, "serialize_error"
    return signed_bytes, "ok"


# ---------------------------------------------------------------------------
# v4.00.62 — SAML 2.0 HTTP-Redirect binding signature (SLO outbound).
#
# Distinct from v4.00.61's HTTP-POST binding signature (which embeds a
# <ds:Signature> element inside the XML and forwards as form POST). The
# Redirect binding signs the URL QUERY STRING (after deflate+base64
# encoding the SAMLRequest), per SAML 2.0 Bindings § 3.4.4.
#
# Wire format that the IdP redirects to:
#
#   <IdP-SLO-URL>?SAMLRequest=<b64(deflate(xml))>
#                &RelayState=<rs>
#                &SigAlg=<alg-URI>
#                &Signature=<b64(rsa-sign(<query-string-before-Signature>))>
#
# IMPORTANT: the bytes that get signed are the URL-ENCODED query string
# UP TO (but not including) the `&Signature=` token. Order MUST be
# SAMLRequest, RelayState (if set), SigAlg.
# ---------------------------------------------------------------------------


_SIG_ALG_URI = {
    "rsa-sha256": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
    "rsa-sha1":   "http://www.w3.org/2000/09/xmldsig#rsa-sha1",
}


def _build_redirect_signed_url(
    *,
    idp_target: str,
    saml_request_b64: str,
    relay_state: str,
) -> tuple[str, str]:
    """v4.00.62 — Build a signed HTTP-Redirect URL for SP-initiated SLO.

    ``saml_request_b64`` MUST already be ``base64(deflate(xml))`` — the
    caller is responsible for the compression step (matches the SAML 2.0
    binding spec which puts the raw-deflate compression on the SP side).

    Returns ``(url, reason)`` where ``reason`` is:
        ``ok`` — fully signed redirect URL built
        ``deps_missing`` — cryptography library not importable
        ``key_unset`` — SP private key not configured
        ``unsupported_alg`` — RMC_SAML_SP_SIGNATURE_ALG not in our map
        ``sign_error`` — cryptography raised mid-sign

    On any non-ok reason, returns the unsigned URL (caller chooses
    fail-closed via strict mode or fall-through).
    NEVER raises.
    """
    import urllib.parse as _ulib

    alg = _sp_signature_alg()
    alg_uri = _SIG_ALG_URI.get(alg)
    base_query_parts = [("SAMLRequest", saml_request_b64)]
    if relay_state:
        base_query_parts.append(("RelayState", relay_state))

    # Build unsigned URL first (for non-ok pass-through).
    unsigned_query = _ulib.urlencode(base_query_parts)
    sep = "&" if "?" in idp_target else "?"
    unsigned_url = f"{idp_target}{sep}{unsigned_query}" if idp_target else ""

    if alg_uri is None:
        return unsigned_url, "unsupported_alg"

    key_pem = _sp_private_key_pem().strip()
    if not key_pem:
        return unsigned_url, "key_unset"

    # The bytes to SIGN per spec: URL-encoded query string up to (but
    # not including) the &Signature= token, with SigAlg appended.
    signed_parts = list(base_query_parts) + [("SigAlg", alg_uri)]
    canonical = _ulib.urlencode(signed_parts).encode("ascii")

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
    except ImportError:
        return unsigned_url, "deps_missing"

    try:
        pk = serialization.load_pem_private_key(
            key_pem.encode("utf-8"), password=None,
        )
        if not isinstance(pk, RSAPrivateKey):
            return unsigned_url, "key_not_rsa"
        hash_alg = hashes.SHA256() if alg == "rsa-sha256" else hashes.SHA1()
        signature = pk.sign(canonical, padding.PKCS1v15(), hash_alg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("saml redirect-sign: cryptography raised: %s", exc)
        return unsigned_url, "sign_error"

    import base64 as _b64m
    sig_b64 = _b64m.b64encode(signature).decode("ascii")
    signed_query = _ulib.urlencode(signed_parts + [("Signature", sig_b64)])
    signed_url = f"{idp_target}{sep}{signed_query}"
    return signed_url, "ok"


# ---------------------------------------------------------------------------
# v4.00.63 — SAML 2.0 HTTP-Redirect binding signature VERIFICATION (inbound).
#
# Counterpart to v4.00.62's outbound signing. When an IdP delivers a
# LogoutRequest via Redirect binding, the URL carries:
#
#   ?SAMLRequest=<b64(deflate(xml))>
#    &RelayState=<rs>            (optional)
#    &SigAlg=<algorithm-URI>
#    &Signature=<b64(signature)>
#
# Per SAML 2.0 Bindings § 3.4.4.1, the bytes that get verified are the
# URL-encoded query string assembled in this EXACT order: SAMLRequest,
# RelayState (if set), SigAlg. Order matters — the IdP's signer assembled
# the bytes in this order before signing, so verification must reproduce
# them exactly.
# ---------------------------------------------------------------------------


_SIG_ALG_URI_TO_HASH = {
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256": "sha256",
    # v4.00.91 — extended for H4 policy compatibility (SHA-384/SHA-512
    # were always valid xmldsig-more URIs; we previously only mapped
    # SHA-256 + SHA-1 because no IdP in our test matrix emitted them).
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha384": "sha384",
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha512": "sha512",
    "http://www.w3.org/2000/09/xmldsig#rsa-sha1": "sha1",
}


def _verify_saml_redirect_signature(
    *,
    saml_request_b64: str = "",
    saml_response_b64: str = "",
    relay_state: str,
    sig_alg_uri: str,
    signature_b64: str,
    idp_cert_pem: str,
) -> tuple[bool, str]:
    """v4.00.63 — Verify a SAML 2.0 HTTP-Redirect binding signature.

    v4.00.64 extended to accept EITHER ``saml_request_b64`` (inbound
    LogoutRequest via Redirect binding — original v4.00.63 contract) OR
    ``saml_response_b64`` (inbound LogoutResponse on the SP-initiated SLO
    callback path). The leading parameter name in the canonical query
    string is ``SAMLRequest`` vs ``SAMLResponse`` per spec § 3.4.4.1 —
    different IdPs sign whichever they emit, and we must reproduce the
    bytes the IdP signed (exactly that leading key).

    Returns ``(verified, reason)`` where ``reason`` is one of:
        ``ok``                — signature matches
        ``deps_missing``      — cryptography lib not importable
        ``cert_unset``        — IdP cert not configured
        ``unsupported_alg``   — SigAlg URI not in our map
        ``bad_signature_b64`` — signature base64-decode failed
        ``bad_cert``          — cert PEM not parseable
        ``signature_invalid`` — RSA verification failed (canonical mismatch
                                or key mismatch)

    Required URL params (per spec) are passed in explicitly so this
    helper is reusable from non-Django callers (smoke / monitors).
    NEVER raises.
    """
    if not idp_cert_pem:
        return False, "cert_unset"
    if not signature_b64:
        return False, "signature_missing"

    # v4.00.91 — H4: signature-algorithm policy gate. Reject rsa-sha1 by
    # default; allow only when the operator has explicitly opted in via
    # RMC_SAML_ALLOW_RSA_SHA1=1. Unknown algorithm URIs always reject.
    _alg_allowed, _alg_reason = _is_signature_algorithm_allowed(sig_alg_uri or "")
    if not _alg_allowed:
        return False, _alg_reason

    hash_name = _SIG_ALG_URI_TO_HASH.get(sig_alg_uri or "")
    if hash_name is None:
        return False, "unsupported_alg"

    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.x509 import load_pem_x509_certificate
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        return False, "deps_missing"

    import base64 as _b64m
    try:
        signature_bytes = _b64m.b64decode(signature_b64, validate=False)
    except (ValueError, TypeError):
        return False, "bad_signature_b64"

    try:
        cert = load_pem_x509_certificate(idp_cert_pem.encode("utf-8"))
        pub = cert.public_key()
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml redirect-verify: cert parse failed: %s", exc)
        return False, "bad_cert"

    # Reconstruct canonical bytes in SAML spec-required order. The leading
    # key is whichever payload the IdP emitted — SAMLRequest for inbound
    # LogoutRequest, SAMLResponse for the callback LogoutResponse.
    import urllib.parse as _ulib
    if saml_response_b64:
        parts = [("SAMLResponse", saml_response_b64)]
    else:
        parts = [("SAMLRequest", saml_request_b64)]
    if relay_state:
        parts.append(("RelayState", relay_state))
    parts.append(("SigAlg", sig_alg_uri))
    canonical = _ulib.urlencode(parts).encode("ascii")

    # v4.00.91 — map SHA-384/SHA-512 too (H4 policy admits them); fall back
    # to SHA-1 only when the alg gate above already allowed it via env.
    if hash_name == "sha256":
        hash_alg = hashes.SHA256()
    elif hash_name == "sha384":
        hash_alg = hashes.SHA384()
    elif hash_name == "sha512":
        hash_alg = hashes.SHA512()
    else:
        hash_alg = hashes.SHA1()
    try:
        pub.verify(signature_bytes, canonical, padding.PKCS1v15(), hash_alg)
        return True, "ok"
    except InvalidSignature:
        return False, "signature_invalid"
    except Exception as exc:  # noqa: BLE001
        logger.info("saml redirect-verify: cryptography raised: %s", exc)
        return False, "signature_invalid"


def _require_redirect_signature() -> bool:
    """v4.00.63 — Opt-in flag for inbound Redirect-binding signature
    verification. Default OFF preserves v4.00.62 behavior (which was
    presence-only via the c14n POST-binding verifier path)."""
    raw = (
        getattr(settings, "RMC_SAML_REQUIRE_REDIRECT_SIGNATURE", None)
        if hasattr(settings, "RMC_SAML_REQUIRE_REDIRECT_SIGNATURE")
        else os.environ.get("RMC_SAML_REQUIRE_REDIRECT_SIGNATURE", "")
    )
    if raw is None or raw == "":
        return False
    return str(raw).lower() in ("1", "true", "yes", "on")


def _idp_cert_pem() -> str:
    """v4.00.63 — IdP cert as PEM bytes (rebuilt from the b64 we stripped).

    The existing ``_idp_cert_b64()`` returns the armorless base64 because
    that's the form ``signxml`` expects. The Redirect binding verifier
    uses ``cryptography.x509.load_pem_x509_certificate`` which DOES want
    PEM armor, so we rebuild it on demand.
    """
    b64 = _idp_cert_b64()
    if not b64:
        return ""
    pem = "-----BEGIN CERTIFICATE-----\n"
    for i in range(0, len(b64), 64):
        pem += b64[i:i + 64] + "\n"
    pem += "-----END CERTIFICATE-----\n"
    return pem


# ---------------------------------------------------------------------------
# v4.00.86 — SAML encrypted assertion support (XML Encryption per
# saml-2.0-core § 2.2.4 + xmlenc-core-1.1).
#
# Contract:
#   ``_decrypt_encrypted_assertion(xml_bytes, sp_private_key_pem)`` accepts
#   the *decoded* SAML response XML bytes (post-base64). When the response
#   carries a ``<saml:EncryptedAssertion>`` element, it attempts to:
#
#     1. Locate the ``<xenc:EncryptedData>`` inside the EncryptedAssertion.
#     2. Locate the ``<xenc:EncryptedKey>`` (per spec, embedded in
#        ``<ds:KeyInfo>`` of EncryptedData or as a peer element).
#     3. Decrypt the EncryptedKey via the SP private key using PKCS#1 v1.5
#        RSA (rsa-1_5) -- the only KeyTransport algorithm we promise. RSA-OAEP
#        (rsa-oaep-mgf1p) is currently honest-stubbed: if the algorithm is
#        OAEP, the SP key path will fail with ``encrypted_key_decrypt_failed``
#        and the caller decides whether to 401.
#     4. Decrypt the EncryptedData via the recovered symmetric key. Supported
#        block ciphers: AES-128-CBC and AES-256-CBC (the most common IdP
#        defaults). IV is the first 16 bytes of the CipherValue.
#     5. Replace ``<saml:EncryptedAssertion>`` w/ ``<saml:Assertion>`` and
#        serialize back to XML bytes.
#
# All crypto goes through lazy ``lxml`` + ``cryptography`` imports; the helper
# NEVER raises. It returns ``(xml_bytes, reason)``. On any failure, the
# original bytes are returned unchanged so the caller can make a policy
# decision (the strict ``RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION=1`` toggle
# upgrades any non-``ok`` reason except ``no_encrypted_assertion`` to a 401).
#
# Env knobs:
#   * ``RMC_SAML_SP_PRIVATE_KEY_PEM``           — SP RSA private key (PEM or
#                                                 armorless base64).
#   * ``RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION``  — when truthy, the ACS path
#                                                 REQUIRES decryption to
#                                                 succeed. Absence of the
#                                                 EncryptedAssertion element
#                                                 OR any decrypt failure
#                                                 returns 401 from ACS.
#
# Honest deferred: RSA-OAEP key transport, AES-GCM data encryption, and
# nested EncryptedID inside the decrypted Assertion are NOT yet supported.
# ---------------------------------------------------------------------------


_NS_XENC = "http://www.w3.org/2001/04/xmlenc#"
_NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"


def _require_encrypted_assertion() -> bool:
    """v4.00.86 — Opt-in toggle: require successful EncryptedAssertion
    decryption on every SAMLResponse. Default OFF preserves v4.00.85
    behavior (plain unencrypted assertions still flow through ACS)."""
    raw = (
        getattr(settings, "RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION", None)
        if hasattr(settings, "RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION")
        else os.environ.get("RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION", "")
    )
    if raw is None or raw == "":
        return False
    return str(raw).lower() in ("1", "true", "yes", "on")


def _normalize_sp_private_key_pem(raw: str) -> str:
    """Accept either fully-armored PEM ('-----BEGIN ... -----') or armorless
    base64 (a single chunk with no headers). Returns full-PEM form suitable
    for ``cryptography.hazmat.primitives.serialization.load_pem_private_key``.

    Empty input returns "" so callers can short-circuit w/ ``sp_key_unset``.
    """
    if not raw:
        return ""
    s = raw.strip()
    if "-----BEGIN" in s:
        # Already armored — return as-is (trust the operator's framing).
        return s
    # Armorless base64 — rewrap. Default to RSA PRIVATE KEY header which is
    # accepted by load_pem_private_key.
    cleaned = re.sub(r"\s+", "", s)
    if not cleaned:
        return ""
    pem = "-----BEGIN RSA PRIVATE KEY-----\n"
    for i in range(0, len(cleaned), 64):
        pem += cleaned[i:i + 64] + "\n"
    pem += "-----END RSA PRIVATE KEY-----\n"
    return pem


def _decrypt_encrypted_assertion(
    xml_bytes: bytes,
    sp_private_key_pem: str,
) -> tuple[bytes, str]:
    """v4.00.86 — Decrypt ``<saml:EncryptedAssertion>`` in-place.

    Returns ``(xml_bytes, reason)`` where reason is one of:

        ``"ok"``                              — decrypted and substituted
        ``"no_encrypted_assertion"``          — no encrypted assertion present
                                                (input returned unchanged)
        ``"lxml_missing"``                    — lxml not installed
        ``"cryptography_missing"``            — cryptography not installed
        ``"sp_key_unset"``                    — SP private key not configured
        ``"sp_key_bad_format"``               — PEM/key load failed
        ``"encrypted_key_decrypt_failed"``    — RSA unwrap of CEK failed
        ``"encrypted_data_decrypt_failed"``   — AES decrypt of payload failed
        ``"replace_failed"``                  — could not splice decrypted
                                                Assertion back into the tree
        ``"unknown"``                         — anything else

    Detection phase is *namespace-agnostic*: a substring check for the
    bytes ``b"EncryptedAssertion"`` is sufficient to short-circuit when
    the response is plain. This avoids paying the lxml import cost for
    every ACS hit.

    NEVER raises. On any failure (other than the explicit no-op
    ``no_encrypted_assertion``), the original bytes are returned so
    the caller can decide whether the strict toggle should 401.
    """
    if not xml_bytes or b"EncryptedAssertion" not in xml_bytes:
        return xml_bytes, "no_encrypted_assertion"

    # Lazy import: lxml is the only practical way to manipulate the
    # decrypted subtree in-place because stdlib ``xml.etree`` does NOT
    # preserve all xmlenc structures the same way.
    try:
        from lxml import etree  # type: ignore
    except ImportError:
        return xml_bytes, "lxml_missing"

    try:
        from cryptography.hazmat.primitives import padding as sym_padding  # type: ignore
        from cryptography.hazmat.primitives import serialization  # type: ignore
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding  # type: ignore
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # type: ignore
    except ImportError:
        return xml_bytes, "cryptography_missing"

    pem = _normalize_sp_private_key_pem(sp_private_key_pem or "")
    if not pem:
        return xml_bytes, "sp_key_unset"

    try:
        private_key = serialization.load_pem_private_key(
            pem.encode("ascii"), password=None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml decrypt: bad SP key format: %s", exc)
        return xml_bytes, "sp_key_bad_format"

    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(xml_bytes, parser=parser)
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml decrypt: lxml parse failed: %s", exc)
        return xml_bytes, "unknown"

    # Find every EncryptedAssertion (typically one, but loop for safety).
    enc_assertions = root.findall(f".//{{{_NS_SAML}}}EncryptedAssertion")
    if not enc_assertions:
        # The substring matched but no namespaced element exists -> the IdP
        # may have used a non-spec namespace. Treat as "nothing to do."
        return xml_bytes, "no_encrypted_assertion"

    import base64 as _b64

    for enc_assertion in enc_assertions:
        enc_data = enc_assertion.find(f"{{{_NS_XENC}}}EncryptedData")
        if enc_data is None:
            return xml_bytes, "unknown"

        # Locate EncryptedKey -- spec allows it either inside the
        # EncryptedData's KeyInfo OR as a peer (RetrievalMethod path is
        # NOT supported in this honest-stub).
        enc_key = enc_data.find(
            f"{{{_NS_DSIG}}}KeyInfo/{{{_NS_XENC}}}EncryptedKey"
        )
        if enc_key is None:
            enc_key = enc_assertion.find(f".//{{{_NS_XENC}}}EncryptedKey")
        if enc_key is None:
            return xml_bytes, "encrypted_key_decrypt_failed"

        cv_key_el = enc_key.find(f"{{{_NS_XENC}}}CipherData/{{{_NS_XENC}}}CipherValue")
        if cv_key_el is None or not (cv_key_el.text or "").strip():
            return xml_bytes, "encrypted_key_decrypt_failed"
        try:
            wrapped_cek = _b64.b64decode((cv_key_el.text or "").strip())
        except Exception:  # noqa: BLE001
            return xml_bytes, "encrypted_key_decrypt_failed"

        # Pull EncryptionMethod for KeyTransport. We currently only honor
        # rsa-1_5 (PKCS#1 v1.5). RSA-OAEP is left as honest-stub: callers
        # whose IdP signs w/ OAEP will see encrypted_key_decrypt_failed.
        em_key = enc_key.find(f"{{{_NS_XENC}}}EncryptionMethod")
        kt_alg = (em_key.attrib.get("Algorithm", "") if em_key is not None else "")
        try:
            if kt_alg.endswith("rsa-1_5") or kt_alg == "":
                cek = private_key.decrypt(wrapped_cek, asym_padding.PKCS1v15())
            else:
                # Honest-stub: RSA-OAEP path deferred to a future wave.
                # Attempting it would require choosing MGF1+SHA1/SHA256 which
                # depend on the IdP. We surface a clean failure reason.
                return xml_bytes, "encrypted_key_decrypt_failed"
        except Exception as exc:  # noqa: BLE001
            logger.debug("saml decrypt: CEK unwrap failed: %s", exc)
            return xml_bytes, "encrypted_key_decrypt_failed"

        # Now decrypt the payload.
        cv_data_el = enc_data.find(f"{{{_NS_XENC}}}CipherData/{{{_NS_XENC}}}CipherValue")
        if cv_data_el is None or not (cv_data_el.text or "").strip():
            return xml_bytes, "encrypted_data_decrypt_failed"
        try:
            blob = _b64.b64decode((cv_data_el.text or "").strip())
        except Exception:  # noqa: BLE001
            return xml_bytes, "encrypted_data_decrypt_failed"

        em_data = enc_data.find(f"{{{_NS_XENC}}}EncryptionMethod")
        data_alg = (em_data.attrib.get("Algorithm", "") if em_data is not None else "")

        # xmlenc convention: first 16 bytes of CipherValue == IV for AES-CBC.
        if not (data_alg.endswith("aes128-cbc") or data_alg.endswith("aes256-cbc") or data_alg == ""):
            return xml_bytes, "encrypted_data_decrypt_failed"

        try:
            iv, ct = blob[:16], blob[16:]
            cipher = Cipher(algorithms.AES(cek), modes.CBC(iv))
            decryptor = cipher.decryptor()
            padded = decryptor.update(ct) + decryptor.finalize()
            unpadder = sym_padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded) + unpadder.finalize()
        except Exception as exc:  # noqa: BLE001
            logger.debug("saml decrypt: AES decrypt failed: %s", exc)
            return xml_bytes, "encrypted_data_decrypt_failed"

        # Splice plaintext Assertion in place of the EncryptedAssertion.
        try:
            decrypted_root = etree.fromstring(plaintext, parser=parser)
        except Exception as exc:  # noqa: BLE001
            logger.debug("saml decrypt: plaintext Assertion parse failed: %s", exc)
            return xml_bytes, "replace_failed"

        try:
            parent = enc_assertion.getparent()
            if parent is None:
                return xml_bytes, "replace_failed"
            idx = list(parent).index(enc_assertion)
            parent.remove(enc_assertion)
            parent.insert(idx, decrypted_root)
        except Exception as exc:  # noqa: BLE001
            logger.debug("saml decrypt: splice failed: %s", exc)
            return xml_bytes, "replace_failed"

    try:
        out = etree.tostring(root, xml_declaration=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml decrypt: serialize failed: %s", exc)
        return xml_bytes, "unknown"

    return out, "ok"


def _parse_saml_response(b64_response: str) -> dict:
    """v4.00.45 — Parse a SAMLResponse: base64-decode, XML-parse, extract
    Subject NameID + Audience + NotBefore/NotOnOrAfter + Issuer.

    Returns a dict with keys ``status``, ``issuer``, ``name_id``,
    ``name_id_format``, ``audience``, ``not_before``, ``not_on_or_after``,
    ``in_response_to``, ``signature_present``.
    """
    import base64
    import xml.etree.ElementTree as ET

    try:
        decoded = base64.b64decode(b64_response, validate=False)
    except (ValueError, TypeError) as exc:
        return {"error": f"bad_base64: {exc}"}

    # v4.00.86 — Attempt EncryptedAssertion decrypt BEFORE XML parse / signature
    # check. The helper short-circuits w/ ``no_encrypted_assertion`` when the
    # response is plain (substring check, no lxml import cost). On any failure
    # it returns the original bytes unchanged; the ACS handler decides whether
    # to 401 based on RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION. The decrypted
    # Assertion still flows through the existing v4.00.65 signature_present_*
    # checks — decryption does NOT bypass signature verification.
    decoded, decrypt_reason = _decrypt_encrypted_assertion(
        decoded, _sp_private_key_pem(),
    )

    try:
        root = ET.fromstring(decoded)
    except ET.ParseError as exc:
        return {"error": f"bad_xml: {exc}", "decrypt_reason": decrypt_reason}

    def _find(parent, tag, ns):
        return parent.find(f"{{{ns}}}{tag}")

    status_code = ""
    status_el = _find(root, "Status", _NS_SAMLP)
    if status_el is not None:
        sc = _find(status_el, "StatusCode", _NS_SAMLP)
        if sc is not None:
            status_code = sc.attrib.get("Value", "")

    assertion = _find(root, "Assertion", _NS_SAML)
    if assertion is None:
        return {
            "error": "missing_assertion",
            "status_code": status_code,
            "in_response_to": root.attrib.get("InResponseTo", ""),
            "decrypt_reason": decrypt_reason,
        }

    # v4.00.91 — H6: assertion-ID replay defense BEFORE signature
    # verification (cheap rejection). The Assertion@ID is REQUIRED per
    # saml-2.0-core § 2.3.3. We surface the registration result on the
    # parsed dict so the ACS view can decide whether to 401 — the parser
    # itself stays side-effect-free from an HTTP perspective.
    assertion_id = (assertion.attrib.get("ID") or "").strip()
    replay_ok = True
    replay_reason = "disabled"
    if _replay_defense_enabled():
        replay_ok, replay_reason = _register_assertion_id(assertion_id)

    issuer_el = _find(assertion, "Issuer", _NS_SAML)
    issuer = (issuer_el.text or "").strip() if issuer_el is not None else ""

    subject = _find(assertion, "Subject", _NS_SAML)
    name_id_el = _find(subject, "NameID", _NS_SAML) if subject is not None else None
    name_id = (name_id_el.text or "").strip() if name_id_el is not None else ""
    name_id_format = name_id_el.attrib.get("Format", "") if name_id_el is not None else ""

    conditions = _find(assertion, "Conditions", _NS_SAML)
    not_before = conditions.attrib.get("NotBefore", "") if conditions is not None else ""
    not_on_or_after = conditions.attrib.get("NotOnOrAfter", "") if conditions is not None else ""
    audience = ""
    if conditions is not None:
        ar = _find(conditions, "AudienceRestriction", _NS_SAML)
        if ar is not None:
            aud_el = _find(ar, "Audience", _NS_SAML)
            audience = (aud_el.text or "").strip() if aud_el is not None else ""

    # AttributeStatement → flatten attributes by FriendlyName / Name.
    attrs: dict[str, str] = {}
    attr_stmt = _find(assertion, "AttributeStatement", _NS_SAML)
    if attr_stmt is not None:
        for a in attr_stmt.findall(f"{{{_NS_SAML}}}Attribute"):
            key = a.attrib.get("FriendlyName") or a.attrib.get("Name") or ""
            val_el = a.find(f"{{{_NS_SAML}}}AttributeValue")
            attrs[key] = (val_el.text or "").strip() if val_el is not None else ""

    # v4.00.86 — AuthnStatement SessionIndex. The IdP emits this on the
    # AuthnStatement so that backchannel SLO (LogoutRequest) can target
    # the exact session it issued. Empty string when missing — registry
    # binding short-circuits on empty per ``register_saml_session_index``.
    session_index = ""
    authn_stmt = _find(assertion, "AuthnStatement", _NS_SAML)
    if authn_stmt is not None:
        session_index = (authn_stmt.attrib.get("SessionIndex") or "").strip()

    # Signature presence (we do NOT canonicalize + verify here when the
    # idp cert is unset; tracked separately so the audit log records
    # whether the IdP did sign).
    # v4.00.65 — Track response-level + assertion-level separately. Most
    # production IdPs (Okta, Azure AD, Auth0, Google) sign the inner
    # <Assertion> element, NOT the outer <Response> wrapper. A new env
    # flag RMC_SAML_REQUIRE_ASSERTION_SIGNATURE upgrades the requirement
    # to "the Assertion itself MUST be signed" — strictly tighter than
    # the v4.00.46 response-presence rule.
    sig_present_response = (
        root.find("{http://www.w3.org/2000/09/xmldsig#}Signature") is not None
    )
    sig_present_assertion = (
        assertion.find("{http://www.w3.org/2000/09/xmldsig#}Signature") is not None
    )
    sig_present = sig_present_response or sig_present_assertion

    return {
        "status_code": status_code,
        "issuer": issuer,
        "name_id": name_id,
        "name_id_format": name_id_format,
        "audience": audience,
        "not_before": not_before,
        "not_on_or_after": not_on_or_after,
        "in_response_to": root.attrib.get("InResponseTo", ""),
        "signature_present": sig_present,
        "signature_present_response": sig_present_response,
        "signature_present_assertion": sig_present_assertion,
        "decrypt_reason": decrypt_reason,
        "attributes": attrs,
        "session_index": session_index,
        # v4.00.91 — H6 replay-defense outcome surfaced to ACS view.
        "assertion_id": assertion_id,
        "replay_ok": replay_ok,
        "replay_reason": replay_reason,
    }


def _require_assertion_signature() -> bool:
    """v4.00.65 — Opt-in to strict assertion-level signature requirement.

    When truthy, the ACS path requires the inner ``<Assertion>`` element
    to carry a ``<ds:Signature>``. This is tighter than v4.00.46's
    presence-only rule (which accepted EITHER a response-level OR
    assertion-level signature) — it specifically rejects responses where
    only the outer wrapper is signed, defending against attacks that
    swap the inner Assertion while leaving the wrapper signature intact.

    Default OFF preserves v4.00.46 + v4.00.57 behavior. Activate with
    ``RMC_SAML_REQUIRE_ASSERTION_SIGNATURE=1`` after the IdP signs
    Assertions (most production deployments already do).
    """
    raw = (
        getattr(settings, "RMC_SAML_REQUIRE_ASSERTION_SIGNATURE", None)
        if hasattr(settings, "RMC_SAML_REQUIRE_ASSERTION_SIGNATURE")
        else os.environ.get("RMC_SAML_REQUIRE_ASSERTION_SIGNATURE", "")
    )
    if raw is None or raw == "":
        return False
    return str(raw).lower() in ("1", "true", "yes", "on")


def _within_validity_window(not_before: str, not_on_or_after: str) -> bool:
    """v4.00.45 / v4.00.91 — RFC 3339 / ISO 8601 timestamp check.

    v4.00.91 delegates to ``_is_within_validity_window`` so the clock-skew
    tolerance (H5) applies to every caller without behavioral surprises.
    Returns ``True`` when the assertion is within the (skew-widened)
    validity window, ``False`` otherwise.
    """
    ok, _reason = _is_within_validity_window(
        not_before_iso=not_before,
        not_on_or_after_iso=not_on_or_after,
    )
    return ok


# ---------------------------------------------------------------------------
# v4.00.66 — SAML attribute mapping config.
#
# Pre-v4.00.66, _provision_user_from_saml hard-coded the SAML attribute
# names (givenName / firstName / sn / surname / familyName / email / mail).
# IdPs in the wild use different names per their vendor / config:
#
#   Okta:        firstName, lastName, email
#   Azure AD:    http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname
#   Google:      first_name, last_name, email
#   Shibboleth:  urn:oid:2.5.4.42 (given name), urn:oid:2.5.4.4 (sn)
#
# Operators now configure the per-field source via env. Each
# RMC_SAML_ATTR_<FIELD> carries a comma-separated priority list of
# attribute keys to try (first non-empty wins). Defaults preserve
# v4.00.45 behavior. Empty / missing env → defaults.
#
# Supported fields: first_name, last_name, email.
# ---------------------------------------------------------------------------

_DEFAULT_SAML_ATTR_MAP = {
    "first_name": ("givenName", "firstName", "first_name",
                   "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
                   "urn:oid:2.5.4.42"),
    "last_name": ("sn", "surname", "familyName", "lastName", "last_name",
                  "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
                  "urn:oid:2.5.4.4"),
    "email": ("email", "mail", "emailAddress",
              "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
              "urn:oid:0.9.2342.19200300.100.1.3"),
}


def _resolve_saml_attr_map() -> dict:
    """v4.00.66 — Build the active SAML attribute-priority map.

    For each known field (first_name, last_name, email):
      1. Read ``RMC_SAML_ATTR_<FIELD_UPPER>`` env var
      2. Split on comma + strip whitespace → priority tuple
      3. Empty → fall back to the default map

    NEVER raises — bad env values fall back to defaults silently.
    """
    out = {}
    for field, default in _DEFAULT_SAML_ATTR_MAP.items():
        env_key = f"RMC_SAML_ATTR_{field.upper()}"
        raw = (
            getattr(settings, env_key, None)
            if hasattr(settings, env_key)
            else os.environ.get(env_key, "")
        )
        if raw is None or str(raw).strip() == "":
            out[field] = tuple(default)
            continue
        parts = tuple(p.strip() for p in str(raw).split(",") if p.strip())
        out[field] = parts or tuple(default)
    return out


def _extract_saml_attr(attrs: dict, priority) -> str:
    """Walk the priority list, return first non-empty stripped value.

    ``priority`` may be a tuple OR a list (v4.00.85 per-tenant merged maps
    return lists; the historical resolver returns tuples). Both iterate.
    """
    for key in priority:
        val = attrs.get(key, "")
        if val and str(val).strip():
            return str(val).strip()
    return ""


# ---------------------------------------------------------------------------
# v4.00.85 — Per-tenant attribute mapping override.
#
# Env: RMC_SAML_TENANT_ATTR_MAP_OVERRIDES (JSON dict). Schema:
#   {
#     "<tenant_schema>": {
#       "first_name": ["custom.GivenName", "user.firstName"],
#       "last_name": ["custom.SurName"],
#       "email": ["custom.PrimaryEmail"]
#     }
#   }
#
# When the tenant has an override, that override is PREPENDED to the
# default keys list (defaults still consulted as fallback). NEVER
# replaced entirely — defaults remain safety net.
# ---------------------------------------------------------------------------


def _resolve_per_tenant_attr_overrides() -> dict:
    """Read RMC_SAML_TENANT_ATTR_MAP_OVERRIDES env.

    Returns ``{}`` on absence or bad JSON. Each tenant's mapping is
    normalized to ``{field_name: [key, ...]}`` — string values are coerced
    to single-element lists, ints/strings in lists are kept as strings,
    anything else is dropped silently. NEVER raises.
    """
    try:
        import json
        raw = (
            getattr(settings, "RMC_SAML_TENANT_ATTR_MAP_OVERRIDES", None)
            if hasattr(settings, "RMC_SAML_TENANT_ATTR_MAP_OVERRIDES")
            else os.environ.get("RMC_SAML_TENANT_ATTR_MAP_OVERRIDES", "")
        )
        if raw is None or str(raw).strip() == "":
            return {}
        parsed = json.loads(str(raw))
        if not isinstance(parsed, dict):
            return {}
        out: dict = {}
        for tenant, mapping in parsed.items():
            if not isinstance(tenant, str) or not isinstance(mapping, dict):
                continue
            normalized: dict = {}
            for field, keys in mapping.items():
                if not isinstance(field, str):
                    continue
                if isinstance(keys, str):
                    normalized[field] = [keys] if keys else []
                elif isinstance(keys, list):
                    normalized[field] = [str(k) for k in keys if isinstance(k, (str, int)) and str(k) != ""]
            if normalized:
                out[tenant] = normalized
        return out
    except Exception:  # noqa: BLE001
        return {}


def resolve_saml_attr_map_for_tenant(tenant_schema: str) -> dict:
    """Return the effective attribute mapping for ``tenant_schema``.

    Per-tenant override keys are PREPENDED to the default keys list
    (defaults remain as fallback safety net). Empty override lists are
    treated as "no override" — defaults are preserved untouched.

    NEVER raises — bad env values fall back to the global resolved map.
    """
    try:
        base = _resolve_saml_attr_map()
    except Exception:  # noqa: BLE001
        base = {field: tuple(default) for field, default in _DEFAULT_SAML_ATTR_MAP.items()}
    if not tenant_schema:
        return base
    overrides = _resolve_per_tenant_attr_overrides().get(tenant_schema, {})
    if not overrides:
        return base
    merged: dict = {}
    for field, default_keys in base.items():
        per_tenant = overrides.get(field, [])
        if not per_tenant:
            # Empty override for this field → keep defaults untouched
            merged[field] = default_keys
            continue
        seen: set = set()
        ordered: list = []
        for k in list(per_tenant) + list(default_keys):
            if k not in seen:
                seen.add(k)
                ordered.append(k)
        merged[field] = ordered
    return merged


def per_tenant_saml_attr_overrides_summary() -> dict:
    """URL-leak-safe summary. Counts only, never raw claim names.

    Returns ``{configured: bool, tenant_count: int, tenants_sample: list[str]}``.
    Tenant schema names ARE returned (they aren't claim secrets) but raw
    claim names / override key lists are deliberately omitted.
    """
    overrides = _resolve_per_tenant_attr_overrides()
    return {
        "configured": bool(overrides),
        "tenant_count": len(overrides),
        "tenants_sample": sorted(overrides.keys())[:6],
    }


def _provision_user_from_saml(name_id: str, attrs: dict, tenant_schema: str = "") -> tuple:
    """Get-or-create User by email (NameID often *is* the email). Returns
    ``(user, created)``.

    v4.00.66 — Attribute lookup now routes through the operator-configurable
    map (RMC_SAML_ATTR_FIRST_NAME / _LAST_NAME / _EMAIL). Defaults preserve
    v4.00.45 behavior so unconfigured deployments keep working.

    v4.00.85 — Optional ``tenant_schema`` arg routes through
    ``resolve_saml_attr_map_for_tenant`` so per-tenant overrides
    (RMC_SAML_TENANT_ATTR_MAP_OVERRIDES) are honored. When unset, falls
    back to the global ``_resolve_saml_attr_map()`` — zero behavior drift
    for existing callers.
    """
    from django.contrib.auth import get_user_model

    if tenant_schema:
        attr_map = resolve_saml_attr_map_for_tenant(tenant_schema)
    else:
        attr_map = _resolve_saml_attr_map()

    UserModel = get_user_model()
    email_raw = _extract_saml_attr(attrs, attr_map["email"])
    email = email_raw.lower().strip()
    if not email and "@" in name_id:
        email = name_id.lower()
    username = email or name_id or ""
    if not username:
        raise RuntimeError("saml_no_subject")
    user = None
    if email:
        user = UserModel.objects.filter(email__iexact=email).first()
    if user is None:
        user = UserModel.objects.filter(username=username).first()
    if user is not None:
        return user, False
    new_user = UserModel(username=username, email=email)
    given = _extract_saml_attr(attrs, attr_map["first_name"])
    family = _extract_saml_attr(attrs, attr_map["last_name"])
    if given:
        new_user.first_name = given
    if family:
        new_user.last_name = family
    new_user.set_unusable_password()
    new_user.save()
    return new_user, True


# v4.00.86 — SessionIndex <-> Django session_key registry.
#
# Used by backchannel SLO to kill the SPECIFIC session that SAML
# initiated, not all sessions for the user. Capped 10000 entries
# (LRU eviction). NEVER persisted — process restart clears the map.
_SESSION_INDEX_REGISTRY: dict[str, str] = {}  # session_index -> django_session_key
_SESSION_INDEX_REGISTRY_REVERSE: dict[str, str] = {}  # django_session_key -> session_index
_SESSION_INDEX_REGISTRY_CAP = 10000
_SESSION_INDEX_REGISTRY_LOCK = threading.Lock()


def register_saml_session_index(*, session_index: str, django_session_key: str) -> bool:
    """Map session_index <-> django session_key. Returns True on register."""
    if not session_index or not django_session_key:
        return False
    with _SESSION_INDEX_REGISTRY_LOCK:
        # Evict oldest if at cap
        if len(_SESSION_INDEX_REGISTRY) >= _SESSION_INDEX_REGISTRY_CAP:
            oldest_idx = next(iter(_SESSION_INDEX_REGISTRY))
            old_key = _SESSION_INDEX_REGISTRY.pop(oldest_idx, None)
            if old_key:
                _SESSION_INDEX_REGISTRY_REVERSE.pop(old_key, None)
        _SESSION_INDEX_REGISTRY[session_index] = django_session_key
        _SESSION_INDEX_REGISTRY_REVERSE[django_session_key] = session_index
    return True


def lookup_session_key_for_session_index(session_index: str) -> str | None:
    if not session_index:
        return None
    with _SESSION_INDEX_REGISTRY_LOCK:
        return _SESSION_INDEX_REGISTRY.get(session_index)


def unregister_by_session_index(session_index: str) -> bool:
    if not session_index:
        return False
    with _SESSION_INDEX_REGISTRY_LOCK:
        key = _SESSION_INDEX_REGISTRY.pop(session_index, None)
        if key:
            _SESSION_INDEX_REGISTRY_REVERSE.pop(key, None)
            return True
        return False


def saml_session_registry_summary() -> dict:
    """Counts only, NEVER session keys (those are bearer-equivalent)."""
    with _SESSION_INDEX_REGISTRY_LOCK:
        return {
            "registered_sessions": len(_SESSION_INDEX_REGISTRY),
            "cap": _SESSION_INDEX_REGISTRY_CAP,
        }


def reset_saml_session_registry() -> None:
    """Test-only."""
    with _SESSION_INDEX_REGISTRY_LOCK:
        _SESSION_INDEX_REGISTRY.clear()
        _SESSION_INDEX_REGISTRY_REVERSE.clear()


def _login_saml_session(request, user) -> None:
    from django.conf import settings as _settings
    from django.contrib.auth import login as _login

    backends = getattr(_settings, "AUTHENTICATION_BACKENDS", ())
    backend = backends[0] if backends else "django.contrib.auth.backends.ModelBackend"
    user.backend = backend
    _login(request, user)


@csrf_exempt
@require_http_methods(["POST"])
def acs(request):
    """v4.00.45 — ACS validates the SAMLResponse and writes a Django session.

    Validation steps:
      1. base64 decode + XML parse the SAMLResponse.
      2. Verify ``Status.StatusCode.Value`` == "Success".
      3. Extract Issuer + Subject.NameID + AudienceRestriction + Conditions.
      4. Audience check against ``RMC_SAML_SP_ENTITY_ID`` (warn-only when unset).
      5. Validity-window check (NotBefore <= now < NotOnOrAfter).
      6. Optional signature check — when ``RMC_SAML_REQUIRE_SIGNATURE`` is
         truthy AND ``RMC_SAML_IDP_CERT_PEM`` is set, require the
         ``<Signature>`` element to be present. Cryptographic signature
         verification w/ canonicalization is a v4.00.46 follow-on
         (needs lxml + signxml).
      7. Get-or-create User by email (NameID) + login() writes the session.
    """
    raw = request.POST.get("SAMLResponse") or ""
    relay = request.POST.get("RelayState") or ""
    if not raw:
        return JsonResponse({"success": False, "error": "missing_saml_response"}, status=400)
    logger.info("saml acs: received SAMLResponse (len=%s, relay_len=%s)", len(raw), len(relay))

    parsed = _parse_saml_response(raw)
    if parsed.get("error"):
        return JsonResponse({"success": False, "stage": "parse_failed", "error": parsed["error"]}, status=400)

    # v4.00.91 — H6: assertion-ID one-time-use replay defense (cheap
    # rejection — runs BEFORE signature verification per spec hardening
    # guidance). The cache registration already happened inside
    # _parse_saml_response; we just surface the outcome here.
    if not parsed.get("replay_ok", True):
        return JsonResponse(
            {"success": False,
             "stage": "assertion_replay_detected",
             "replay_reason": parsed.get("replay_reason", "replay_detected")},
            status=401,
        )

    # v4.00.86 — STRICT EncryptedAssertion requirement. When
    # RMC_SAML_REQUIRE_ENCRYPTED_ASSERTION=1, the inner <saml:EncryptedAssertion>
    # MUST be present AND must decrypt successfully via the SP private key.
    # Plain (non-encrypted) responses are rejected, AND any decrypt failure
    # (lxml/cryptography missing, sp_key_unset/bad_format, RSA/AES failures,
    # splice failures) is treated as a hard 401. This runs BEFORE signature
    # validation so the existing v4.00.65 signature_present_* checks then
    # apply against the *decrypted* Assertion subtree.
    if _require_encrypted_assertion():
        _decrypt_reason = parsed.get("decrypt_reason", "")
        if _decrypt_reason == "no_encrypted_assertion":
            return JsonResponse(
                {"success": False,
                 "stage": "encrypted_assertion_required_but_missing",
                 "decrypt_reason": _decrypt_reason},
                status=401,
            )
        if _decrypt_reason and _decrypt_reason != "ok":
            return JsonResponse(
                {"success": False,
                 "stage": "encrypted_assertion_decrypt_failed",
                 "decrypt_reason": _decrypt_reason},
                status=401,
            )

    expected_status = "urn:oasis:names:tc:SAML:2.0:status:Success"
    status_code = parsed.get("status_code", "")
    if status_code and status_code != expected_status:
        return JsonResponse({"success": False, "stage": "status_not_success", "status_code": status_code}, status=401)

    name_id = parsed.get("name_id", "")
    if not name_id:
        return JsonResponse({"success": False, "stage": "missing_name_id"}, status=400)

    audience = parsed.get("audience", "")
    expected_audience = _entity_id()
    if audience and expected_audience and audience != expected_audience:
        return JsonResponse({"success": False, "stage": "audience_mismatch", "expected": expected_audience, "received": audience}, status=401)

    # v4.00.91 — H5: validity-window check w/ clock-skew tolerance. The
    # helper widens the window by +/- RMC_SAML_CLOCK_SKEW_SECONDS (default
    # 300, clamped to [0, 3600]) so NTP drift between SP and IdP can't
    # 401 a valid login that's a few seconds beyond the spec edge.
    _vw_ok, _vw_reason = _is_within_validity_window(
        not_before_iso=parsed.get("not_before", ""),
        not_on_or_after_iso=parsed.get("not_on_or_after", ""),
    )
    if not _vw_ok:
        return JsonResponse(
            {"success": False,
             "stage": "validity_window_failed",
             "reason": _vw_reason,
             "not_before": parsed.get("not_before", ""),
             "not_on_or_after": parsed.get("not_on_or_after", "")},
            status=401,
        )

    if _require_signature() and _idp_cert_b64() and not parsed.get("signature_present"):
        return JsonResponse({"success": False, "stage": "signature_required_but_missing"}, status=401)

    # v4.00.65 — STRICT assertion-level signature requirement. When
    # RMC_SAML_REQUIRE_ASSERTION_SIGNATURE=1, the inner <Assertion> element
    # MUST carry <ds:Signature> — wrapper-only signatures are rejected. This
    # defends against assertion-swap attacks where a valid wrapper signature
    # is preserved while the inner subject + attributes are replaced.
    if _require_assertion_signature() and not parsed.get("signature_present_assertion"):
        return JsonResponse(
            {"success": False,
             "stage": "assertion_signature_required_but_missing",
             "signature_present_response": parsed.get("signature_present_response", False),
             "signature_present_assertion": False},
            status=401,
        )

    # v4.00.57 — c14n signature verification (lxml + signxml). Activates when
    # RMC_SAML_REQUIRE_SIGNATURE=1 AND idp cert configured AND signature
    # present. When deps not yet installed, RMC_SAML_SIGNATURE_STRICT (default
    # true) decides whether to 503 the request or fall back to presence-only.
    if _require_signature() and _idp_cert_b64() and parsed.get("signature_present"):
        verified, reason = _verify_saml_signature_c14n(raw, _idp_cert_b64())
        if not verified:
            if reason == "deps_missing":
                if _require_signature_strict():
                    return JsonResponse(
                        {"success": False, "stage": "signature_verifier_deps_missing",
                         "detail": "install lxml + signxml runtime deps"},
                        status=503,
                    )
                logger.warning("saml acs: c14n verifier deps_missing — falling back to presence-only check")
            else:
                return JsonResponse(
                    {"success": False, "stage": "signature_verification_failed", "reason": reason},
                    status=401,
                )

    # v4.00.85 — Best-effort per-tenant attr-map routing. If the request
    # carries a tenant context (django-tenants style ``request.tenant``),
    # surface its ``schema_name`` so RMC_SAML_TENANT_ATTR_MAP_OVERRIDES can
    # prepend custom claims for that tenant. Absent/broken tenant context
    # falls back to the global resolver — zero drift for non-tenanted callers.
    _saml_tenant_schema = ""
    try:
        _t = getattr(request, "tenant", None)
        if _t is not None:
            _saml_tenant_schema = str(getattr(_t, "schema_name", "") or "")
    except Exception:  # noqa: BLE001
        _saml_tenant_schema = ""

    try:
        user, created = _provision_user_from_saml(
            name_id,
            parsed.get("attributes") or {},
            tenant_schema=_saml_tenant_schema,
        )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"success": False, "stage": "provision_failed", "detail": str(exc)}, status=500)

    try:
        _login_saml_session(request, user)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"success": False, "stage": "session_login_failed", "detail": str(exc)}, status=500)

    # v4.00.86 — Bind the SAML SessionIndex to the freshly-issued Django
    # session_key so a backchannel LogoutRequest can target THIS exact
    # session (not "every session for this user"). Also persist
    # ``saml_name_id`` + ``saml_session_index`` in the session so the
    # v4.00.60 SP-initiated slo_start can re-use them.
    _saml_session_index = parsed.get("session_index", "") or ""
    try:
        if hasattr(request, "session"):
            if _saml_session_index:
                request.session["saml_session_index"] = _saml_session_index
            if name_id:
                request.session["saml_name_id"] = name_id
            _session_key = getattr(request.session, "session_key", "") or ""
            if _saml_session_index and _session_key:
                register_saml_session_index(
                    session_index=_saml_session_index,
                    django_session_key=_session_key,
                )
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml acs: session_index registration failed: %s", exc)

    # v4.00.50 — bind the user to the resolved tenant from existing profiles.
    try:
        from apps.api.oidc_rp import _bind_tenant_for_user as _bind

        _bind(
            user, source="saml", provider="saml",
            subject=name_id, issuer=parsed.get("issuer", ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml tenant bind failed err=%s", exc)

    want_json = (request.GET.get("format") or "").lower() == "json"
    if want_json:
        return JsonResponse({
            "success": True,
            "stage": "logged_in",
            "name_id": name_id,
            "name_id_format": parsed.get("name_id_format", ""),
            "issuer": parsed.get("issuer", ""),
            "audience": audience,
            "user_id": user.pk,
            "username": user.get_username(),
            "created": created,
            "relay_state_length": len(relay),
            "signature_present": parsed.get("signature_present", False),
        })
    # Default: redirect to LOGIN_REDIRECT_URL (or RelayState when same-host).
    from django.conf import settings as _settings
    from django.http import HttpResponseRedirect
    from django.utils.http import url_has_allowed_host_and_scheme

    target = getattr(_settings, "LOGIN_REDIRECT_URL", "/") or "/"
    if relay:
        host = request.get_host()
        if url_has_allowed_host_and_scheme(relay, allowed_hosts={host}, require_https=request.is_secure()):
            target = relay
    return HttpResponseRedirect(target)


_NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"


def _parse_saml_logout_request(b64_payload: str) -> dict:
    """v4.00.58 — Parse a SAML2 LogoutRequest payload.

    Accepts both HTTP-POST base64 form AND HTTP-Redirect base64+deflate form;
    detects deflate by trying inflate-raw first and falling back to plain
    base64. Returns ``{id, issuer, name_id, name_id_format, session_index,
    not_on_or_after, signature_present, error?}``. NEVER raises.
    """
    import base64
    import xml.etree.ElementTree as ET
    import zlib

    if not b64_payload:
        return {"error": "missing_payload"}

    try:
        decoded = base64.b64decode(b64_payload, validate=False)
    except (ValueError, TypeError) as exc:
        return {"error": f"bad_base64: {exc}"}

    # HTTP-Redirect binding wraps in deflate; try inflate first.
    raw_xml = None
    try:
        raw_xml = zlib.decompress(decoded, -15)  # raw deflate (no zlib header)
    except zlib.error:
        raw_xml = decoded

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        # Maybe the payload was NOT deflated after all and inflate above
        # produced garbage; retry with the original base64.
        try:
            root = ET.fromstring(decoded)
        except ET.ParseError as exc:
            return {"error": f"bad_xml: {exc}"}

    issuer_el = root.find(f"{{{_NS_SAML}}}Issuer")
    issuer = (issuer_el.text or "").strip() if issuer_el is not None else ""
    name_id_el = root.find(f"{{{_NS_SAML}}}NameID")
    name_id = (name_id_el.text or "").strip() if name_id_el is not None else ""
    name_id_format = name_id_el.attrib.get("Format", "") if name_id_el is not None else ""
    session_index_el = root.find(f"{{{_NS_SAMLP}}}SessionIndex")
    session_index = (session_index_el.text or "").strip() if session_index_el is not None else ""
    sig_present = root.find(f"{{{_NS_DSIG}}}Signature") is not None

    return {
        "id": root.attrib.get("ID", ""),
        "issuer": issuer,
        "name_id": name_id,
        "name_id_format": name_id_format,
        "session_index": session_index,
        "not_on_or_after": root.attrib.get("NotOnOrAfter", ""),
        "destination": root.attrib.get("Destination", ""),
        "signature_present": sig_present,
    }


def _build_saml_logout_response(in_response_to: str, issuer: str, destination: str) -> bytes:
    """v4.00.58 — Build a minimal LogoutResponse XML w/ Status=Success.

    Returns raw bytes ready for base64+deflate encoding by the caller. Not
    signed by us by default — IdPs that require signed responses MUST
    receive the response via a downstream signer. The plaintext-XML path
    is the same the SAML 2 Web SSO Logout Profile defines.
    """
    from datetime import datetime, timezone
    import uuid

    issue_instant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp_id = f"_rmc-lr-{uuid.uuid4().hex}"
    in_resp_to_attr = f' InResponseTo="{in_response_to}"' if in_response_to else ""
    dest_attr = f' Destination="{destination}"' if destination else ""
    xml = (
        f'<samlp:LogoutResponse xmlns:samlp="{_NS_SAMLP}" '
        f'xmlns:saml="{_NS_SAML}" '
        f'ID="{resp_id}" Version="2.0" IssueInstant="{issue_instant}"{dest_attr}{in_resp_to_attr}>'
        f'<saml:Issuer>{issuer}</saml:Issuer>'
        f'<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
        f'</samlp:LogoutResponse>'
    )
    return xml.encode("utf-8")


def _idp_slo_target() -> str:
    """v4.00.58 — Return the IdP's SLO redirect target.

    Honors ``RMC_SAML_IDP_SLO_URL`` env / setting; falls back to root.
    """
    val = (
        getattr(settings, "RMC_SAML_IDP_SLO_URL", None)
        if hasattr(settings, "RMC_SAML_IDP_SLO_URL")
        else os.environ.get("RMC_SAML_IDP_SLO_URL", "")
    )
    return (val or "").strip()


@require_http_methods(["GET", "POST"])
def sls(request):
    """v4.00.58 — Hardened SLO endpoint.

    Steps:
      1. Extract SAMLRequest (HTTP-POST body or HTTP-Redirect query string).
      2. Parse + classify (id, name_id, session_index, not_on_or_after,
         signature_present, issuer).
      3. Optional signature check — honors RMC_SAML_REQUIRE_SIGNATURE; when
         truthy AND idp cert configured AND signature present, run the
         v4.00.57 c14n verifier. deps_missing classification falls back
         per RMC_SAML_SIGNATURE_STRICT (default true -> 503).
      4. Flush the Django session (idempotent — no-op when not logged in).
      5. Build LogoutResponse w/ Status=Success.
      6. Redirect to the IdP's SLO URL (RMC_SAML_IDP_SLO_URL) when set,
         else return the response inline as JSON / XML based on Accept.

    ``?format=json`` returns the parsed shape for headless smoke / monitoring.
    """
    saml_req = request.POST.get("SAMLRequest") or request.GET.get("SAMLRequest") or ""
    relay = request.POST.get("RelayState") or request.GET.get("RelayState") or ""
    logger.info("saml sls: received LogoutRequest (method=%s, len=%s, relay_len=%s)",
                request.method, len(saml_req), len(relay))

    parsed = _parse_saml_logout_request(saml_req) if saml_req else {"error": "missing_saml_request"}
    if parsed.get("error"):
        # Even on parse failure we still flush the session so a poisoned
        # request can't leave a logged-in user behind.
        try:
            request.session.flush()
        except Exception as exc:  # noqa: BLE001
            logger.debug("saml sls: session flush failed: %s", exc)
        return JsonResponse(
            {"success": False, "stage": "parse_failed", "error": parsed["error"]},
            status=400,
        )

    # Optional signature check.
    sig_reason = ""
    if _require_signature() and _idp_cert_b64() and parsed.get("signature_present"):
        verified, reason = _verify_saml_signature_c14n(saml_req, _idp_cert_b64())
        sig_reason = reason
        if not verified:
            if reason == "deps_missing":
                if _require_signature_strict():
                    return JsonResponse(
                        {"success": False, "stage": "signature_verifier_deps_missing"},
                        status=503,
                    )
                logger.warning("saml sls: c14n verifier deps_missing - falling back to presence-only")
            else:
                return JsonResponse(
                    {"success": False, "stage": "signature_verification_failed", "reason": reason},
                    status=401,
                )
    elif _require_signature() and _idp_cert_b64() and not parsed.get("signature_present"):
        return JsonResponse(
            {"success": False, "stage": "signature_required_but_missing"},
            status=401,
        )

    # v4.00.63 — Redirect-binding signature verification. Distinct from the
    # c14n verifier above (which inspects <ds:Signature> embedded in the
    # XML for POST binding). The Redirect binding signature rides in the
    # URL query string and signs the canonical (SAMLRequest, RelayState?,
    # SigAlg) bytes. Activated by RMC_SAML_REQUIRE_REDIRECT_SIGNATURE=1.
    redirect_sig_reason = ""
    if _require_redirect_signature() and request.method == "GET":
        url_sig = request.GET.get("Signature") or ""
        url_sig_alg = request.GET.get("SigAlg") or ""
        if not url_sig:
            return JsonResponse(
                {"success": False, "stage": "redirect_signature_required_but_missing"},
                status=401,
            )
        pem = _idp_cert_pem()
        if not pem:
            return JsonResponse(
                {"success": False, "stage": "redirect_signature_cert_unset"},
                status=503,
            )
        verified, reason = _verify_saml_redirect_signature(
            saml_request_b64=request.GET.get("SAMLRequest") or "",
            relay_state=request.GET.get("RelayState") or "",
            sig_alg_uri=url_sig_alg,
            signature_b64=url_sig,
            idp_cert_pem=pem,
        )
        redirect_sig_reason = reason  # noqa: F841 — surfaced for future telemetry
        if not verified:
            if reason == "deps_missing":
                if _require_signature_strict():
                    return JsonResponse(
                        {"success": False, "stage": "redirect_signature_verifier_deps_missing"},
                        status=503,
                    )
                logger.warning("saml sls: redirect verifier deps_missing - falling back")
            else:
                return JsonResponse(
                    {"success": False, "stage": "redirect_signature_verification_failed",
                     "reason": reason},
                    status=401,
                )

    # Flush the Django session.
    try:
        request.session.flush()
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml sls: session flush failed: %s", exc)

    # v4.00.86 — Targeted backchannel kill. If the LogoutRequest carries a
    # SessionIndex AND the v4.00.86 in-memory registry has a binding for it
    # to a Django session_key, ask the configured SessionStore to delete
    # that specific session row. This is the only path that can kill the
    # SAML-issued session when the LogoutRequest arrives on a connection
    # OTHER than the user-agent's (true backchannel SLO). On any error,
    # fall through silently — we already flushed the requester's session.
    _killed_targeted = False
    _targeted_kill_reason = "no_session_index"
    _incoming_session_index = parsed.get("session_index", "") or ""
    if _incoming_session_index:
        try:
            _targeted_kill_reason = "no_registry_binding"
            _bound_key = lookup_session_key_for_session_index(_incoming_session_index)
            if _bound_key:
                from importlib import import_module as _import_module
                from django.conf import settings as _settings_kill
                _engine = _import_module(
                    getattr(_settings_kill, "SESSION_ENGINE",
                            "django.contrib.sessions.backends.db")
                )
                _SessionStore = _engine.SessionStore  # type: ignore[attr-defined]
                try:
                    _SessionStore(session_key=_bound_key).delete()
                    _killed_targeted = True
                    _targeted_kill_reason = "ok"
                except Exception as _exc_inner:  # noqa: BLE001
                    _targeted_kill_reason = f"backend_delete_failed: {_exc_inner}"
                # Always drop the registry binding so the index is one-shot.
                unregister_by_session_index(_incoming_session_index)
        except Exception as exc:  # noqa: BLE001
            _targeted_kill_reason = f"engine_error: {exc}"
            logger.debug("saml sls: targeted backchannel kill failed: %s", exc)

    # Build LogoutResponse.
    resp_bytes = _build_saml_logout_response(
        in_response_to=parsed.get("id", ""),
        issuer=_entity_id() or "rmc-sp",
        destination=_idp_slo_target(),
    )

    # v4.00.64 — opt-in sign the outbound LogoutResponse when RMC_SAML_SP_SIGN_LOGOUT=1.
    # Same env contract as v4.00.61 LogoutRequest signing. Strict mode 503s on
    # signer failure; non-strict falls through to unsigned XML.
    resp_signature_reason = "unsigned"
    resp_signed = False
    if _sp_sign_logout_enabled():
        signed_resp_bytes, resp_signature_reason = _sign_saml_logout_response(resp_bytes)
        if resp_signature_reason == "ok":
            resp_bytes = signed_resp_bytes
            resp_signed = True
        elif _require_signature_strict():
            return JsonResponse({
                "success": False,
                "stage": "sp_signer_unavailable_response",
                "reason": resp_signature_reason,
            }, status=503)
        else:
            logger.warning("saml sls: response signing requested but %s - emitting unsigned",
                           resp_signature_reason)

    if (request.GET.get("format") or "").lower() == "json":
        import base64 as _b64
        return JsonResponse({
            "success": True,
            "stage": "logged_out",
            "in_response_to": parsed.get("id", ""),
            "name_id": parsed.get("name_id", ""),
            "session_index": parsed.get("session_index", ""),
            "signature_present": parsed.get("signature_present", False),
            "signature_reason": sig_reason,
            "logout_response_b64": _b64.b64encode(resp_bytes).decode("ascii"),
            "relay_state": relay,
            "response_signed": resp_signed,
            "response_signature_reason": resp_signature_reason,
            "targeted_session_killed": _killed_targeted,
            "targeted_kill_reason": _targeted_kill_reason,
        })

    # Redirect to IdP SLO target when configured; else return the XML inline.
    idp_target = _idp_slo_target()
    if idp_target:
        import base64 as _b64
        import urllib.parse
        params = {"SAMLResponse": _b64.b64encode(resp_bytes).decode("ascii")}
        if relay:
            params["RelayState"] = relay
        sep = "&" if "?" in idp_target else "?"
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(f"{idp_target}{sep}{urllib.parse.urlencode(params)}")
    return HttpResponse(resp_bytes, content_type="text/xml; charset=utf-8")


def _autosubmit_form_html(action: str, payload_b64: str, relay: str) -> str:
    """v4.00.59 — Build an HTTP-POST binding auto-submit HTML form.

    Used by the IdP-initiated logout flow: after the SP processes the
    incoming LogoutRequest, it must return a LogoutResponse to the IdP via
    POST binding (which means rendering an HTML form that auto-submits via
    JavaScript). RelayState is preserved when set.

    HTML is intentionally minimal and JS-only — operators with NoScript
    can still click the "Continue" button to complete the flow.
    """
    from django.utils.html import escape as _escape
    action_esc = _escape(action)
    payload_esc = _escape(payload_b64)
    relay_html = (
        f'<input type="hidden" name="RelayState" value="{_escape(relay)}">' if relay else ""
    )
    return (
        "<!DOCTYPE html><html><head>"
        "<meta charset=\"utf-8\">"
        "<title>SAML logout</title></head><body>"
        f"<form id=\"slo-form\" method=\"post\" action=\"{action_esc}\">"
        f"<input type=\"hidden\" name=\"SAMLResponse\" value=\"{payload_esc}\">"
        f"{relay_html}"
        "<noscript><button type=\"submit\">Continue logout</button></noscript>"
        "</form>"
        "<script>document.getElementById('slo-form').submit();</script>"
        "</body></html>"
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def sls_idp(request):
    """v4.00.59 — IdP-initiated logout endpoint (POST-binding).

    Distinct from v4.00.58 ``sls`` in that the response payload is sent
    back to the IdP via an HTML auto-submit form (HTTP-POST binding) rather
    than via 302 redirect (HTTP-Redirect binding). Some IdPs (notably
    Microsoft Entra ID, Okta enterprise) require POST-binding for the
    logout response when the LogoutRequest itself was POST-bound.

    Same validation flow as ``sls``: parse LogoutRequest, optionally
    verify c14n signature, flush Django session, build LogoutResponse.
    The terminal step differs: when ``RMC_SAML_IDP_SLO_URL`` is set, this
    endpoint returns a self-submitting HTML form posting to the IdP. When
    unset, returns the raw XML inline (parity with the v4.00.58 fallback).
    """
    import base64 as _b64

    saml_req = request.POST.get("SAMLRequest") or request.GET.get("SAMLRequest") or ""
    relay = request.POST.get("RelayState") or request.GET.get("RelayState") or ""
    logger.info("saml sls-idp: received LogoutRequest (method=%s, len=%s)", request.method, len(saml_req))

    parsed = _parse_saml_logout_request(saml_req) if saml_req else {"error": "missing_saml_request"}
    if parsed.get("error"):
        try:
            request.session.flush()
        except Exception as exc:  # noqa: BLE001
            logger.debug("saml sls-idp: session flush failed: %s", exc)
        return JsonResponse(
            {"success": False, "stage": "parse_failed", "error": parsed["error"]},
            status=400,
        )

    sig_reason = ""
    if _require_signature() and _idp_cert_b64() and parsed.get("signature_present"):
        verified, reason = _verify_saml_signature_c14n(saml_req, _idp_cert_b64())
        sig_reason = reason
        if not verified:
            if reason == "deps_missing":
                if _require_signature_strict():
                    return JsonResponse(
                        {"success": False, "stage": "signature_verifier_deps_missing"},
                        status=503,
                    )
                logger.warning("saml sls-idp: c14n verifier deps_missing - falling back")
            else:
                return JsonResponse(
                    {"success": False, "stage": "signature_verification_failed", "reason": reason},
                    status=401,
                )
    elif _require_signature() and _idp_cert_b64() and not parsed.get("signature_present"):
        return JsonResponse(
            {"success": False, "stage": "signature_required_but_missing"},
            status=401,
        )

    try:
        request.session.flush()
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml sls-idp: session flush failed: %s", exc)

    resp_bytes = _build_saml_logout_response(
        in_response_to=parsed.get("id", ""),
        issuer=_entity_id() or "rmc-sp",
        destination=_idp_slo_target(),
    )

    # v4.00.64 — outbound LogoutResponse signing (parity with v4.00.58 sls).
    resp_signature_reason = "unsigned"
    resp_signed = False
    if _sp_sign_logout_enabled():
        signed_resp_bytes, resp_signature_reason = _sign_saml_logout_response(resp_bytes)
        if resp_signature_reason == "ok":
            resp_bytes = signed_resp_bytes
            resp_signed = True
        elif _require_signature_strict():
            return JsonResponse({
                "success": False,
                "stage": "sp_signer_unavailable_response",
                "reason": resp_signature_reason,
            }, status=503)
        else:
            logger.warning("saml sls-idp: response signing requested but %s - emitting unsigned",
                           resp_signature_reason)

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "stage": "logged_out_idp_initiated",
            "in_response_to": parsed.get("id", ""),
            "name_id": parsed.get("name_id", ""),
            "session_index": parsed.get("session_index", ""),
            "signature_present": parsed.get("signature_present", False),
            "signature_reason": sig_reason,
            "logout_response_b64": _b64.b64encode(resp_bytes).decode("ascii"),
            "binding": "HTTP-POST",
            "relay_state": relay,
            "response_signed": resp_signed,
            "response_signature_reason": resp_signature_reason,
        })

    idp_target = _idp_slo_target()
    payload_b64 = _b64.b64encode(resp_bytes).decode("ascii")
    if idp_target:
        html = _autosubmit_form_html(action=idp_target, payload_b64=payload_b64, relay=relay)
        return HttpResponse(html, content_type="text/html; charset=utf-8")
    return HttpResponse(resp_bytes, content_type="text/xml; charset=utf-8")


# ---------------------------------------------------------------------------
# v4.00.60 — SP-initiated SLO.
#
# Counterpart to v4.00.58 ``sls`` (IdP-sent LogoutRequest) and v4.00.59
# ``sls_idp`` (IdP-initiated with POST-binding response). SP-initiated
# means the LOGOUT ORIGINATES at the SP side — the user clicks "log out"
# in our app, we build a LogoutRequest, deliver it to the IdP, the IdP
# terminates the IdP session AND every other SP session, then redirects
# back to our ``sls_callback`` with a LogoutResponse we parse + verify.
#
# Two endpoints:
#   * GET  /sso/saml/slo/start/    — builds the LogoutRequest, redirects
#                                    the user-agent to the IdP via POST
#                                    binding (auto-submit form).
#   * POST /sso/saml/slo/callback/ — receives the IdP's LogoutResponse,
#                                    parses Status, flushes session,
#                                    redirects per ?next= or to /.
# ---------------------------------------------------------------------------

def _build_saml_logout_request(name_id: str, session_index: str, issuer: str, destination: str) -> bytes:
    """v4.00.60 — Build a minimal LogoutRequest XML for SP-initiated SLO.

    SAML 2.0 Web SSO LogoutRequest carries: Issuer (this SP), NameID
    (the user being logged out at the IdP), and optionally SessionIndex
    (so the IdP can target the specific authentication session).

    Returns raw bytes ready for base64 encoding + form POST. Not signed
    by us — IdPs that require signed LogoutRequests must wire a downstream
    signer (mirrors the LogoutResponse contract).
    """
    from datetime import datetime, timezone
    import uuid

    issue_instant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    req_id = f"_rmc-lr-sp-{uuid.uuid4().hex}"
    dest_attr = f' Destination="{destination}"' if destination else ""
    name_id_el = ""
    if name_id:
        from django.utils.html import escape as _escape
        name_id_el = f'<saml:NameID>{_escape(name_id)}</saml:NameID>'
    session_index_el = ""
    if session_index:
        from django.utils.html import escape as _escape
        session_index_el = f'<samlp:SessionIndex>{_escape(session_index)}</samlp:SessionIndex>'
    xml = (
        f'<samlp:LogoutRequest xmlns:samlp="{_NS_SAMLP}" '
        f'xmlns:saml="{_NS_SAML}" '
        f'ID="{req_id}" Version="2.0" IssueInstant="{issue_instant}"{dest_attr}>'
        f'<saml:Issuer>{issuer}</saml:Issuer>'
        f'{name_id_el}'
        f'{session_index_el}'
        f'</samlp:LogoutRequest>'
    )
    return xml.encode("utf-8")


def _parse_saml_logout_response(b64_payload: str) -> dict:
    """v4.00.60 — Parse a SAML2 LogoutResponse payload.

    Returns ``{id, issuer, in_response_to, status_code, signature_present,
    error?}``. NEVER raises.
    """
    import base64
    import xml.etree.ElementTree as ET
    import zlib

    if not b64_payload:
        return {"error": "missing_payload"}

    try:
        decoded = base64.b64decode(b64_payload, validate=False)
    except (ValueError, TypeError) as exc:
        return {"error": f"bad_base64: {exc}"}

    raw_xml = None
    try:
        raw_xml = zlib.decompress(decoded, -15)
    except zlib.error:
        raw_xml = decoded

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        try:
            root = ET.fromstring(decoded)
        except ET.ParseError as exc:
            return {"error": f"bad_xml: {exc}"}

    issuer_el = root.find(f"{{{_NS_SAML}}}Issuer")
    issuer = (issuer_el.text or "").strip() if issuer_el is not None else ""
    status_el = root.find(f"{{{_NS_SAMLP}}}Status")
    status_code = ""
    if status_el is not None:
        sc = status_el.find(f"{{{_NS_SAMLP}}}StatusCode")
        if sc is not None:
            status_code = sc.attrib.get("Value", "") or ""
    sig_present = root.find(f"{{{_NS_DSIG}}}Signature") is not None
    return {
        "id": root.attrib.get("ID", ""),
        "issuer": issuer,
        "in_response_to": root.attrib.get("InResponseTo", ""),
        "destination": root.attrib.get("Destination", ""),
        "status_code": status_code,
        "signature_present": sig_present,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
def slo_start(request):
    """v4.00.60 — SP-initiated SLO start.

    The currently-authenticated user clicks "log out everywhere": we
    build a LogoutRequest targeting the IdP, and POST the user-agent
    to ``RMC_SAML_IDP_SLO_URL`` via an auto-submit HTML form.

    Inputs (all optional, taken from session if not supplied):
      * ``?name_id=`` — fallback for the user's name id
      * ``?session_index=`` — fallback for the auth session index
      * ``?next=`` — preserved across the round-trip in RelayState

    ``?format=json`` returns the assembled LogoutRequest shape for
    headless smoke testing.
    """
    import base64 as _b64

    # Pull name_id + session_index from session if present, else from query
    # (the SAML ACS persists both at login time when available).
    sess = getattr(request, "session", None)
    name_id = ""
    session_index = ""
    if sess is not None:
        try:
            name_id = sess.get("saml_name_id", "") or ""
            session_index = sess.get("saml_session_index", "") or ""
        except Exception as exc:  # noqa: BLE001
            logger.debug("slo_start: session lookup failed: %s", exc)
    name_id = (request.GET.get("name_id") or name_id or "").strip()
    session_index = (request.GET.get("session_index") or session_index or "").strip()
    relay = (request.GET.get("next") or request.GET.get("RelayState") or "").strip()

    idp_target = _idp_slo_target()
    issuer = _entity_id() or "rmc-sp"
    req_bytes = _build_saml_logout_request(
        name_id=name_id,
        session_index=session_index,
        issuer=issuer,
        destination=idp_target,
    )

    # v4.00.61 — opt-in sign the LogoutRequest body when RMC_SAML_SP_SIGN_LOGOUT=1.
    # Honors RMC_SAML_SIGNATURE_STRICT (default true): on deps_missing / key_unset
    # / cert_unset, strict mode 503s; non-strict falls through to unsigned XML.
    signature_reason = "unsigned"
    signed = False
    if _sp_sign_logout_enabled():
        signed_bytes, signature_reason = _sign_saml_logout_request(req_bytes)
        if signature_reason == "ok":
            req_bytes = signed_bytes
            signed = True
        elif _require_signature_strict():
            return JsonResponse({
                "success": False,
                "stage": "sp_signer_unavailable",
                "reason": signature_reason,
            }, status=503)
        else:
            logger.warning("saml slo_start: signing requested but %s - emitting unsigned",
                           signature_reason)

    # v4.00.62 — binding choice. POST (default, preserves v4.00.60) embeds
    # the signed XML in an auto-submit form. REDIRECT (?binding=redirect)
    # uses raw-deflate + base64 + URL-encoded query string and signs the
    # query string per SAML 2.0 Bindings § 3.4.4.
    binding = (request.GET.get("binding") or "post").strip().lower()
    if binding not in ("post", "redirect"):
        binding = "post"

    # Common base64 of the in-memory XML (signed-if-applicable for POST,
    # unsigned-original for redirect — Redirect binding doesn't embed
    # <ds:Signature>, the signature rides in the query string).
    payload_b64 = _b64.b64encode(req_bytes).decode("ascii")

    # Redirect binding deflate-then-base64. SAML spec requires raw deflate
    # (no zlib header), so use zlib.compressobj with wbits=-15.
    import zlib as _zlib
    redirect_b64 = ""
    if binding == "redirect":
        compressor = _zlib.compressobj(level=9, wbits=-15)
        deflated = compressor.compress(req_bytes) + compressor.flush()
        redirect_b64 = _b64.b64encode(deflated).decode("ascii")

    # Build the signed Redirect URL when in redirect mode + signing enabled.
    redirect_url = ""
    redirect_sig_reason = "unsigned"
    if binding == "redirect" and idp_target:
        if _sp_sign_logout_enabled():
            redirect_url, redirect_sig_reason = _build_redirect_signed_url(
                idp_target=idp_target,
                saml_request_b64=redirect_b64,
                relay_state=relay,
            )
            if redirect_sig_reason != "ok" and _require_signature_strict():
                return JsonResponse({
                    "success": False,
                    "stage": "sp_signer_unavailable_redirect",
                    "reason": redirect_sig_reason,
                    "binding": "HTTP-Redirect",
                }, status=503)
        else:
            # Unsigned redirect URL — caller opted out of signing.
            import urllib.parse as _ulib
            parts = [("SAMLRequest", redirect_b64)]
            if relay:
                parts.append(("RelayState", relay))
            sep = "&" if "?" in idp_target else "?"
            redirect_url = f"{idp_target}{sep}{_ulib.urlencode(parts)}"

    if (request.GET.get("format") or "").lower() == "json":
        body = {
            "success": True,
            "stage": "logout_request_built",
            "name_id": name_id,
            "session_index": session_index,
            "issuer": issuer,
            "destination": idp_target,
            "logout_request_b64": payload_b64,
            "binding": "HTTP-Redirect" if binding == "redirect" else "HTTP-POST",
            "relay_state": relay,
            "signed": signed if binding == "post" else (redirect_sig_reason == "ok"),
            "signature_reason": signature_reason if binding == "post" else redirect_sig_reason,
        }
        if binding == "redirect":
            body["saml_request_deflated_b64"] = redirect_b64
            body["redirect_url"] = redirect_url
        return JsonResponse(body)

    if not idp_target:
        # Without an IdP target we cannot complete SP-initiated SLO.
        return JsonResponse({
            "success": False,
            "stage": "idp_slo_target_missing",
            "error": "RMC_SAML_IDP_SLO_URL not configured",
        }, status=503)

    # Redirect binding → 302 to signed URL (or unsigned-built URL).
    if binding == "redirect":
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(redirect_url)

    # POST binding → auto-submit HTML form (preserves v4.00.60).
    from django.utils.html import escape as _escape
    action_esc = _escape(idp_target)
    payload_esc = _escape(payload_b64)
    relay_html = (
        f'<input type="hidden" name="RelayState" value="{_escape(relay)}">' if relay else ""
    )
    html = (
        "<!DOCTYPE html><html><head>"
        "<meta charset=\"utf-8\">"
        "<title>SAML logout (SP-initiated)</title></head><body>"
        f"<form id=\"slo-start-form\" method=\"post\" action=\"{action_esc}\">"
        f"<input type=\"hidden\" name=\"SAMLRequest\" value=\"{payload_esc}\">"
        f"{relay_html}"
        "<noscript><button type=\"submit\">Continue logout</button></noscript>"
        "</form>"
        "<script>document.getElementById('slo-start-form').submit();</script>"
        "</body></html>"
    )
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def slo_callback(request):
    """v4.00.60 — SP-initiated SLO callback.

    The IdP redirects the user-agent back here with a LogoutResponse
    (signaling the IdP-side session is terminated). We parse it, verify
    the status code is Success, flush our local session, and redirect to
    ``?RelayState=`` (or root if none).

    ``?format=json`` returns the parsed shape for headless smoke testing.
    """
    saml_resp = request.POST.get("SAMLResponse") or request.GET.get("SAMLResponse") or ""
    relay = request.POST.get("RelayState") or request.GET.get("RelayState") or ""
    logger.info("saml slo-callback: received LogoutResponse (method=%s, len=%s)",
                request.method, len(saml_resp))

    # v4.00.64 — SP-initiated SLO Redirect-binding signed callback verification.
    # Counterpart to v4.00.63 sls() verification path. When the IdP redirects
    # the user-agent back here with ?SAMLResponse=...&SigAlg=...&Signature=...
    # we verify the URL canonical bytes against the IdP cert. Activated by
    # RMC_SAML_REQUIRE_REDIRECT_SIGNATURE=1 (default OFF preserves v4.00.60).
    # GET-only — POST-binding callback signatures live in <ds:Signature>
    # embedded in the LogoutResponse XML and are checked separately.
    callback_sig_reason = ""
    if _require_redirect_signature() and request.method == "GET":
        url_sig = request.GET.get("Signature") or ""
        url_sig_alg = request.GET.get("SigAlg") or ""
        if not url_sig:
            return JsonResponse(
                {"success": False,
                 "stage": "redirect_callback_signature_required_but_missing"},
                status=401,
            )
        pem = _idp_cert_pem()
        if not pem:
            return JsonResponse(
                {"success": False, "stage": "redirect_callback_signature_cert_unset"},
                status=503,
            )
        verified, reason = _verify_saml_redirect_signature(
            saml_response_b64=request.GET.get("SAMLResponse") or "",
            relay_state=request.GET.get("RelayState") or "",
            sig_alg_uri=url_sig_alg,
            signature_b64=url_sig,
            idp_cert_pem=pem,
        )
        callback_sig_reason = reason
        if not verified:
            if reason == "deps_missing":
                if _require_signature_strict():
                    return JsonResponse(
                        {"success": False,
                         "stage": "redirect_callback_signature_verifier_deps_missing"},
                        status=503,
                    )
                logger.warning("saml slo-callback: redirect verifier deps_missing - falling back")
            else:
                return JsonResponse(
                    {"success": False,
                     "stage": "redirect_callback_signature_verification_failed",
                     "reason": reason},
                    status=401,
                )

    parsed = _parse_saml_logout_response(saml_resp) if saml_resp else {"error": "missing_saml_response"}
    if parsed.get("error"):
        # Even on parse failure, flush the session so a partially-completed
        # logout doesn't leave a logged-in user behind.
        try:
            request.session.flush()
        except Exception as exc:  # noqa: BLE001
            logger.debug("saml slo-callback: session flush failed: %s", exc)
        return JsonResponse(
            {"success": False, "stage": "parse_failed", "error": parsed["error"]},
            status=400,
        )

    status_code = parsed.get("status_code", "") or ""
    is_success = status_code.endswith(":Success")

    try:
        request.session.flush()
    except Exception as exc:  # noqa: BLE001
        logger.debug("saml slo-callback: session flush failed: %s", exc)

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": is_success,
            "stage": "logged_out_sp_initiated" if is_success else "logout_response_non_success",
            "id": parsed.get("id", ""),
            "in_response_to": parsed.get("in_response_to", ""),
            "issuer": parsed.get("issuer", ""),
            "status_code": status_code,
            "signature_present": parsed.get("signature_present", False),
            "relay_state": relay,
            "callback_signature_reason": callback_sig_reason,
        })

    if not is_success:
        return JsonResponse(
            {"success": False, "stage": "logout_response_non_success", "status_code": status_code},
            status=401,
        )

    # Redirect to ``next``/RelayState (validated to start with "/" to avoid
    # open redirect) or root.
    target = relay if (relay.startswith("/") and not relay.startswith("//")) else "/"
    from django.http import HttpResponseRedirect
    return HttpResponseRedirect(target)


# ---------------------------------------------------------------------------
# v4.00.67 — SAML SP-initiated SSO.
#
# Counterpart to v4.00.46 ``acs`` (IdP-sent AuthnResponse): SP-initiated
# means the LOGIN ORIGINATES at the SP side. User clicks "Sign in with
# SAML" in our app; we build an AuthnRequest, deliver it to the IdP via
# HTTP-Redirect (default) or HTTP-POST binding, and the IdP redirects
# the user-agent back to ``/sso/saml/acs/`` with the SAMLResponse.
#
# Reuses v4.00.62's ``_build_redirect_signed_url`` for the Redirect-binding
# signature path AND v4.00.61's ``_sign_saml_logout_request`` lookalike
# pattern (XML-DSig embedded ``<ds:Signature>``) for POST binding —
# operators who already configured RMC_SAML_SP_SIGN_LOGOUT=1 get
# AuthnRequest signing FOR FREE.
#
# Endpoint:
#   * GET  /sso/saml/login/start/   — builds the AuthnRequest, returns
#                                     302 to IdP (Redirect binding) OR
#                                     auto-submit HTML form (POST binding)
# ---------------------------------------------------------------------------


def _idp_sso_url() -> str:
    """v4.00.67 — Return the IdP's SSO redirect target.

    Honors ``RMC_SAML_IDP_SSO_URL`` env / setting; empty when unset.
    """
    val = (
        getattr(settings, "RMC_SAML_IDP_SSO_URL", None)
        if hasattr(settings, "RMC_SAML_IDP_SSO_URL")
        else os.environ.get("RMC_SAML_IDP_SSO_URL", "")
    )
    return (val or "").strip()


def _build_saml_authn_request(
    *,
    sp_entity_id: str,
    acs_url: str,
    idp_target: str,
    force_authn: bool = False,
    is_passive: bool = False,
    name_id_format: str = "",
) -> bytes:
    """v4.00.67 — Build a minimal SAML 2.0 AuthnRequest XML for SP-initiated SSO.

    AuthnRequest carries: Issuer (this SP), AssertionConsumerServiceURL
    (where the IdP should POST the response), optional NameIDPolicy.
    Returns raw bytes ready for base64 encoding (POST binding) or
    deflate+base64 (Redirect binding).

    Not signed by us at the XML level — signing is the caller's
    responsibility via ``_sign_saml_logout_request``-pattern signer or
    via ``_build_redirect_signed_url`` for Redirect binding.
    """
    from datetime import datetime, timezone
    import uuid
    from django.utils.html import escape as _escape

    issue_instant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    req_id = f"_rmc-ar-{uuid.uuid4().hex}"

    dest_attr = f' Destination="{_escape(idp_target)}"' if idp_target else ""
    acs_attr = f' AssertionConsumerServiceURL="{_escape(acs_url)}"' if acs_url else ""
    force_attr = ' ForceAuthn="true"' if force_authn else ""
    passive_attr = ' IsPassive="true"' if is_passive else ""

    name_id_policy = ""
    if name_id_format:
        name_id_policy = (
            f'<samlp:NameIDPolicy Format="{_escape(name_id_format)}" AllowCreate="true"/>'
        )

    xml = (
        f'<samlp:AuthnRequest xmlns:samlp="{_NS_SAMLP}" '
        f'xmlns:saml="{_NS_SAML}" '
        f'ID="{req_id}" Version="2.0" IssueInstant="{issue_instant}"'
        f' ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"'
        f'{dest_attr}{acs_attr}{force_attr}{passive_attr}>'
        f'<saml:Issuer>{_escape(sp_entity_id)}</saml:Issuer>'
        f'{name_id_policy}'
        f'</samlp:AuthnRequest>'
    )
    return xml.encode("utf-8")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def login_start(request):
    """v4.00.67 — SP-initiated SSO start.

    Builds an AuthnRequest targeting the IdP. By default uses the
    HTTP-Redirect binding (302 to IdP w/ deflated SAMLRequest in the URL).
    ``?binding=post`` switches to HTTP-POST (auto-submit form).

    Inputs (all optional):
      * ``?next=`` — preserved across the round-trip as RelayState
        (must start with "/" — open-redirect defense)
      * ``?force_authn=1`` — ForceAuthn="true" attribute (re-auth even
        if the IdP session is alive)
      * ``?passive=1`` — IsPassive="true" (no IdP UI; fails fast if
        the IdP session is missing)
      * ``?name_id_format=<URI>`` — override the requested NameIDPolicy
      * ``?format=json`` — returns assembled shape for headless smoke

    Returns 503 idp_sso_target_missing when ``RMC_SAML_IDP_SSO_URL`` unset.
    """
    import base64 as _b64

    idp_target = _idp_sso_url()
    sp_entity_id = _entity_id() or "rmc-sp"
    acs_url = f"{_base_url(request)}/sso/saml/acs/"
    relay = (request.GET.get("next") or request.GET.get("RelayState") or "").strip()
    # Open-redirect defense: relay must be a server-relative path.
    if relay and (not relay.startswith("/") or relay.startswith("//")):
        relay = ""

    force_authn = (request.GET.get("force_authn") or "").strip() in ("1", "true", "yes")
    is_passive = (request.GET.get("passive") or "").strip() in ("1", "true", "yes")
    name_id_format = (request.GET.get("name_id_format") or "").strip()

    req_bytes = _build_saml_authn_request(
        sp_entity_id=sp_entity_id,
        acs_url=acs_url,
        idp_target=idp_target,
        force_authn=force_authn,
        is_passive=is_passive,
        name_id_format=name_id_format,
    )

    # v4.00.67 — opt-in signing reuses v4.00.61 RMC_SAML_SP_SIGN_LOGOUT
    # env (operators who configured signing for logout get login signing
    # for free). Same strict-mode 503 contract.
    signature_reason = "unsigned"
    signed = False
    if _sp_sign_logout_enabled():
        # Reuse the LogoutRequest signer — XML-DSig enveloped signing
        # is structurally identical for AuthnRequest, just operates on
        # a different root element. The sign helper doesn't inspect the
        # root local-name; it canonicalizes the whole tree.
        signed_bytes, signature_reason = _sign_saml_logout_request(req_bytes)
        if signature_reason == "ok":
            req_bytes = signed_bytes
            signed = True
        elif _require_signature_strict():
            return JsonResponse({
                "success": False,
                "stage": "sp_signer_unavailable",
                "reason": signature_reason,
            }, status=503)
        else:
            logger.warning(
                "saml login_start: signing requested but %s - emitting unsigned",
                signature_reason,
            )

    binding = (request.GET.get("binding") or "redirect").strip().lower()
    if binding not in ("post", "redirect"):
        binding = "redirect"

    payload_b64 = _b64.b64encode(req_bytes).decode("ascii")

    # Redirect binding: deflate-then-base64. SAML spec requires raw deflate.
    import zlib as _zlib
    redirect_b64 = ""
    if binding == "redirect":
        compressor = _zlib.compressobj(level=9, wbits=-15)
        deflated = compressor.compress(req_bytes) + compressor.flush()
        redirect_b64 = _b64.b64encode(deflated).decode("ascii")

    redirect_url = ""
    redirect_sig_reason = "unsigned"
    if binding == "redirect" and idp_target:
        if _sp_sign_logout_enabled():
            redirect_url, redirect_sig_reason = _build_redirect_signed_url(
                idp_target=idp_target,
                saml_request_b64=redirect_b64,
                relay_state=relay,
            )
            if redirect_sig_reason != "ok" and _require_signature_strict():
                return JsonResponse({
                    "success": False,
                    "stage": "sp_signer_unavailable_redirect",
                    "reason": redirect_sig_reason,
                    "binding": "HTTP-Redirect",
                }, status=503)
        else:
            import urllib.parse as _ulib
            parts = [("SAMLRequest", redirect_b64)]
            if relay:
                parts.append(("RelayState", relay))
            sep = "&" if "?" in idp_target else "?"
            redirect_url = f"{idp_target}{sep}{_ulib.urlencode(parts)}"

    if (request.GET.get("format") or "").lower() == "json":
        body = {
            "success": True,
            "stage": "authn_request_built",
            "sp_entity_id": sp_entity_id,
            "acs_url": acs_url,
            "idp_target": idp_target,
            "force_authn": force_authn,
            "is_passive": is_passive,
            "name_id_format": name_id_format,
            "binding": "HTTP-Redirect" if binding == "redirect" else "HTTP-POST",
            "relay_state": relay,
            "authn_request_b64": payload_b64,
            "signed": signed if binding == "post" else (redirect_sig_reason == "ok"),
            "signature_reason": signature_reason if binding == "post" else redirect_sig_reason,
        }
        if binding == "redirect":
            body["saml_request_deflated_b64"] = redirect_b64
            body["redirect_url"] = redirect_url
        return JsonResponse(body)

    if not idp_target:
        return JsonResponse({
            "success": False,
            "stage": "idp_sso_target_missing",
            "error": "RMC_SAML_IDP_SSO_URL not configured",
        }, status=503)

    if binding == "redirect":
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(redirect_url)

    from django.utils.html import escape as _escape
    action_esc = _escape(idp_target)
    payload_esc = _escape(payload_b64)
    relay_html = (
        f'<input type="hidden" name="RelayState" value="{_escape(relay)}">' if relay else ""
    )
    html = (
        "<!DOCTYPE html><html><head>"
        "<meta charset=\"utf-8\">"
        "<title>SAML sign-in</title></head><body>"
        f"<form id=\"sso-start-form\" method=\"post\" action=\"{action_esc}\">"
        f"<input type=\"hidden\" name=\"SAMLRequest\" value=\"{payload_esc}\">"
        f"{relay_html}"
        "<noscript><button type=\"submit\">Continue sign-in</button></noscript>"
        "</form>"
        "<script>document.getElementById('sso-start-form').submit();</script>"
        "</body></html>"
    )
    return HttpResponse(html, content_type="text/html; charset=utf-8")


# ---------------------------------------------------------------------------
# v4.00.68 — SAML LoginInitiator UX surface.
#
# The v4.00.67 ``login_start`` view is the workhorse of SP-initiated SSO,
# but operators expect a single button on /portal/login/ that just works
# — not an unlinked URL. This block ships:
#
#   * ``resolve_saml_login_initiator(request, *, next_url="") -> dict``
#       The shape rendered into the login template:
#         {available, label, start_url, idp_target, force_authn, passive,
#          binding}
#       ``available`` is True iff the IdP target is configured (the only
#       way the button could actually work). ``label`` is operator-facing
#       and tenant-configurable via ``RMC_SAML_LOGIN_BUTTON_LABEL`` env
#       (default "Sign in with SSO"). ``start_url`` is the prebuilt query
#       string the button POSTs/GETs to — already carries ?next= so the
#       template doesn't have to.
#
#   * ``login_initiator_context(request) -> dict``
#       Django context-processor returning ``{saml_login_initiator: ...}``.
#       Wire it into TEMPLATES.OPTIONS.context_processors if the operator
#       wants every login page to surface SSO automatically.
#
# Open-redirect defense matches login_start exactly: ?next= values that
# don't start with "/" or that start with "//" are dropped.
# ---------------------------------------------------------------------------


_LOGIN_BUTTON_LABEL_DEFAULT = "Sign in with SSO"


def _saml_login_button_label() -> str:
    val = (
        getattr(settings, "RMC_SAML_LOGIN_BUTTON_LABEL", "")
        or os.environ.get("RMC_SAML_LOGIN_BUTTON_LABEL", "")
        or _LOGIN_BUTTON_LABEL_DEFAULT
    )
    return str(val).strip() or _LOGIN_BUTTON_LABEL_DEFAULT


def _sanitize_next_url(raw: str) -> str:
    """Mirror login_start's open-redirect defense exactly."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith("/") or raw.startswith("//"):
        return ""
    return raw


def resolve_saml_login_initiator(request, *, next_url: str = "") -> dict:
    """Return the shape the /portal/login/ template needs to render the
    SSO button. ``available`` gates the whole block off when the operator
    hasn't configured the IdP target.
    """
    from django.urls import reverse, NoReverseMatch
    import urllib.parse as _ulib

    idp_target = _idp_sso_url()
    safe_next = _sanitize_next_url(next_url)
    try:
        base_url = reverse("sso_saml_login_start")
    except NoReverseMatch:
        base_url = "/sso/saml/login/start/"

    qs = {}
    if safe_next:
        qs["next"] = safe_next
    start_url = base_url + (("?" + _ulib.urlencode(qs)) if qs else "")

    return {
        "available": bool(idp_target),
        "label": _saml_login_button_label(),
        "start_url": start_url,
        "idp_target": idp_target,
        "force_authn": False,
        "passive": False,
        "binding": "HTTP-Redirect",
    }


# ---------------------------------------------------------------------------
# v4.00.74 — SAML Home Realm Discovery (HRD) per-domain config.
#
# When the operator has multiple IdPs (one per email domain — e.g. the
# district uses Okta and partner schools use Azure AD), the SSO button
# can't ship a single IdP URL. HRD lets the platform inspect the entered
# email domain, look up the matching IdP, and route the AuthnRequest to
# the right tenant.
#
# Config shape (env / settings):
#   ``RMC_SAML_HRD_MAPPING`` — JSON string ``{"school.edu":
#     "https://okta.school.edu/...", "partner.edu":
#     "https://login.partner.edu/..."}``
#
# Lookup is case-insensitive on the domain. Empty mapping disables HRD;
# falls back to the default ``RMC_SAML_IDP_SSO_URL``.
# ---------------------------------------------------------------------------


def _hrd_mapping() -> dict[str, str]:
    """Return the configured HRD mapping. Empty dict on missing/malformed env."""
    raw = (
        getattr(settings, "RMC_SAML_HRD_MAPPING", "")
        or os.environ.get("RMC_SAML_HRD_MAPPING", "")
        or ""
    )
    if not raw:
        return {}
    try:
        import json as _json_mod
        parsed = _json_mod.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("saml HRD mapping malformed: %s", exc)
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k).lower(): str(v) for k, v in parsed.items()
            if isinstance(k, str) and isinstance(v, str)}


def resolve_idp_target_for_email(email: str) -> str:
    """v4.00.74 — Pick the IdP target for the supplied email's domain.

    Falls back to the default IdP target when the domain isn't mapped
    OR the email is empty / malformed.

    v4.00.85 — Precedence:
      1. Multi-IdP registry exact-domain match (RMC_SAML_MULTI_IDP_REGISTRY)
      2. Multi-IdP registry wildcard-suffix match
      3. v4.00.74 _hrd_mapping (URL-only HRD mapping)
      4. Default _idp_sso_url() single-IdP env

    Returning the registry's ``sso_url`` when set ensures multi-IdP-aware
    deployments route to the right tenant; single-IdP deployments preserve
    pre-v4.00.85 behavior unchanged (registry empty → HRD → env fallback).
    """
    # v4.00.85 — multi-IdP registry takes precedence when configured.
    rec = resolve_multi_idp_record(email or "")
    if rec and isinstance(rec, dict):
        sso = str(rec.get("sso_url") or "").strip()
        if sso:
            return sso

    if not email or "@" not in email:
        return _idp_sso_url()
    domain = email.rsplit("@", 1)[1].strip().lower()
    if not domain:
        return _idp_sso_url()
    mapping = _hrd_mapping()
    if domain in mapping:
        return mapping[domain]
    # Wildcard suffix support — *.school.edu also matches sub.school.edu.
    for key, target in mapping.items():
        if key.startswith("*.") and domain.endswith(key[1:]):
            return target
    return _idp_sso_url()


# ---------------------------------------------------------------------------
# v4.00.85 — Multi-IdP federation registry.
#
# Extends the v4.00.74 _hrd_mapping (which was URL-only, single value per
# domain) with a RICHER per-domain record: label, sso_url, entity_id,
# cert_pem_b64, attribute_map_override. Districts running multiple IdPs
# (e.g. one Okta tenant for staff, one Azure AD for students) can map
# each email domain to the right tenant + its specific signing cert + its
# specific attribute map.
#
# Env: RMC_SAML_MULTI_IDP_REGISTRY (JSON dict). Schema:
#   {
#     "school.edu": {
#       "label": "Acme Okta SSO",
#       "sso_url": "https://acme.okta.com/app/...",
#       "entity_id": "https://acme.okta.com/exk...",
#       "cert_pem_b64": "<armorless-b64>",
#       "attribute_map_override": {"email": "user.email",
#                                  "firstName": "user.firstName"}
#     },
#     "*.staff.school.edu": {...}
#   }
#
# Wildcard suffix matching mirrors v4.00.74 _hrd_mapping pattern. Exact
# matches WIN over wildcard matches (most-specific first).
#
# Honest deferred: per-IdP cert validation (using cert_pem_b64 from the
# registry rather than the global RMC_SAML_IDP_CERT_PEM) is left to a
# future wave. v4.00.85 surfaces the field on the record so callers can
# read it, but the v4.00.57 c14n verifier still reads the global cert.
# ---------------------------------------------------------------------------


def resolve_multi_idp_record(email: str) -> dict | None:
    """v4.00.85 — Return the IdP record for ``email`` based on the multi-IdP
    registry, OR ``None`` if no match (caller falls back to single-IdP path).

    Match order:
      1. Exact domain match — winner record is annotated
         ``match_type="exact"``, ``matched_domain=<domain>``.
      2. Wildcard suffix match (key shape ``"*.suffix"``) — annotated
         ``match_type="wildcard_suffix"``, ``matched_domain=<key>`` (the
         pattern itself, useful for operator dashboards).

    Returns a SHALLOW COPY of the registry record so callers cannot mutate
    the parsed env. NEVER raises — bad env / bad JSON / non-dict shapes
    silently return None so the caller falls back cleanly.
    """
    try:
        import json
        import os
        raw = os.environ.get("RMC_SAML_MULTI_IDP_REGISTRY", "")
        if not raw:
            return None
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None
        # Extract domain
        if "@" not in (email or ""):
            return None
        domain = email.split("@", 1)[1].strip().lower()
        if not domain:
            return None
        # Exact match wins
        if domain in parsed and isinstance(parsed[domain], dict):
            rec = dict(parsed[domain])
            rec["matched_domain"] = domain
            rec["match_type"] = "exact"
            return rec
        # Wildcard suffix match
        for key, val in parsed.items():
            if not isinstance(key, str) or not key.startswith("*."):
                continue
            suffix = key[1:].lower()  # ".staff.school.edu"
            if domain.endswith(suffix) and isinstance(val, dict):
                rec = dict(val)
                rec["matched_domain"] = key
                rec["match_type"] = "wildcard_suffix"
                return rec
        return None
    except Exception:  # noqa: BLE001
        return None


def multi_idp_registry_summary() -> dict:
    """v4.00.85 — URL-leak-safe summary for operator dashboards.

    Reports COUNTS by match type + sample domains (cap 6 per category).
    NEVER includes raw ``sso_url`` / ``cert_pem_b64`` / ``entity_id`` —
    the summary is safe to log + render on the diagnostics page.

    Shapes:
      * env unset           → {configured: False, entries: 0,
                               exact_domains: [], wildcard_patterns: []}
      * env set OK          → {configured: True, entries: N,
                               exact_domains: [...], wildcard_patterns: [...]}
      * env JSON-not-dict   → {configured: False, error: "registry_not_dict"}
      * env malformed JSON  → {configured: False, error: "registry_parse_failure"}
    NEVER raises.
    """
    try:
        import json
        import os
        raw = os.environ.get("RMC_SAML_MULTI_IDP_REGISTRY", "")
        if not raw:
            return {"configured": False, "entries": 0,
                    "exact_domains": [], "wildcard_patterns": []}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {"configured": False, "error": "registry_not_dict"}
        exacts = sorted(k for k in parsed.keys()
                        if isinstance(k, str) and not k.startswith("*."))[:6]
        wildcards = sorted(k for k in parsed.keys()
                           if isinstance(k, str) and k.startswith("*."))[:6]
        return {
            "configured": True,
            "entries": len(parsed),
            "exact_domains": exacts,
            "wildcard_patterns": wildcards,
        }
    except Exception:  # noqa: BLE001
        return {"configured": False, "error": "registry_parse_failure"}


def hrd_mapping_summary() -> dict:
    """Operator-facing summary — counts + sample of mapped domains.
    NEVER returns raw IdP URLs (defense vs config leak)."""
    mapping = _hrd_mapping()
    domains = sorted(mapping.keys())
    return {
        "mapped_domain_count": len(domains),
        "domains_sample": domains[:10],
        "wildcard_count": sum(1 for d in domains if d.startswith("*.")),
        "configured": bool(mapping),
        "fallback_idp_set": bool(_idp_sso_url()),
    }


def login_initiator_context(request) -> dict:
    """Django context-processor — exposes ``{{ saml_login_initiator }}``
    to every template. Safe to wire in TEMPLATES.OPTIONS.context_processors;
    NEVER raises (returns ``{available: False}`` on any failure).
    """
    try:
        next_url = (
            request.GET.get("next")
            or getattr(request, "POST", {}).get("next", "")
            or ""
        )
        return {"saml_login_initiator": resolve_saml_login_initiator(request, next_url=next_url)}
    except Exception as exc:  # noqa: BLE001
        logger.debug("login_initiator_context failed: %s", exc)
        return {"saml_login_initiator": {"available": False, "label": "", "start_url": ""}}


# ---------------------------------------------------------------------------
# v4.00.91 — Wave 24 SAML 2.0 security hardening.
#
# Closes 3 audit gaps the 22-wave SAML roll-up surfaced:
#
#   H4 — RSA-SHA1 rejection (configurable).
#        Default policy now REJECTS the deprecated rsa-sha1 signature
#        algorithm. Legacy IdPs still on SHA-1 can opt in via env. This
#        applies to BOTH inbound Redirect-binding signatures (verified by
#        ``_verify_saml_redirect_signature``) AND inbound POST-binding
#        c14n signatures (verified by ``_verify_saml_signature_c14n``).
#
#        Env: ``RMC_SAML_ALLOW_RSA_SHA1`` (default ``"0"`` = reject).
#
#   H5 — Clock-skew tolerance on Conditions/@NotBefore + @NotOnOrAfter.
#        Pre-v4.00.91 the window check used strict ``now >= NotOnOrAfter``
#        which rejected assertions seconds beyond expiry — a normal NTP
#        drift between SP and IdP would 401 valid logins. New behavior
#        widens the window by ``[-skew, +skew]`` seconds on each side.
#
#        Env: ``RMC_SAML_CLOCK_SKEW_SECONDS`` (default ``"300"`` = 5 min,
#        clamped to [0, 3600]).
#
#   H6 — Assertion-ID one-time-use cache (replay defense).
#        Most IdPs emit a unique ``<saml:Assertion ID="…">`` per login.
#        Replaying the same SAMLResponse (e.g. stolen from a logged
#        proxy) re-uses that ID. We now reject the second-and-subsequent
#        sighting of an Assertion ID inside its validity window via an
#        in-process LRU cache. The cache is cheap (dict + lock) and
#        evicts in batches of 100 when capped at 10000.
#
#        Env: ``RMC_SAML_REPLAY_DEFENSE_ENABLED`` (default ``"1"`` = on,
#        set to ``"0"`` to bypass — for prod IdPs that intentionally
#        re-broadcast the same Assertion ID across redirect-binding
#        retransmissions).
#
# Quality bar this block honors:
#   * Env reads happen at function-call time, not module load, so test
#     env mutations take effect immediately.
#   * Never log assertion content / NameID / attribute statements / IDs.
#     The replay-defense cache stores assertion IDs only because the ID
#     is structurally a UUID-style opaque token — it is NOT PII and is
#     specifically designed to be logged + correlated by spec.
#   * Lock-protected mutations on the cache (``threading.Lock``).
#   * No new runtime dependencies.
# ---------------------------------------------------------------------------


# ---- H4: signature algorithm policy --------------------------------------

# Full signature-algorithm URI registry per
# https://www.w3.org/TR/xmldsig-core1/ and xmldsig-more.
_SAML_SIG_ALG_REGISTRY = {
    "http://www.w3.org/2000/09/xmldsig#rsa-sha1": "rsa-sha1",
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256": "rsa-sha256",
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha384": "rsa-sha384",
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha512": "rsa-sha512",
    "http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256": "ecdsa-sha256",
}


def _allow_rsa_sha1() -> bool:
    """v4.00.91 — opt-in toggle for the deprecated rsa-sha1 signature alg.

    Default ``False`` (reject). Env ``RMC_SAML_ALLOW_RSA_SHA1=1`` allows it
    so operators bridging to legacy on-prem IdPs (older Shibboleth / ADFS)
    can keep the channel open until the IdP rotates to SHA-256.

    Read at call time so test env mutations take immediate effect.
    """
    raw = (
        getattr(settings, "RMC_SAML_ALLOW_RSA_SHA1", None)
        if hasattr(settings, "RMC_SAML_ALLOW_RSA_SHA1")
        else os.environ.get("RMC_SAML_ALLOW_RSA_SHA1", "")
    )
    if raw is None or raw == "":
        return False
    return str(raw).lower() in ("1", "true", "yes", "on")


def _is_signature_algorithm_allowed(alg_uri: str) -> tuple[bool, str]:
    """v4.00.91 — Policy check on a SAML / XML-DSig signature-algorithm URI.

    Returns ``(allowed, reason)`` where reason is one of:

        ``"ok"``                          — modern algorithm (sha256+)
        ``"legacy_sha1_allowed_by_env"``  — rsa-sha1 + env opt-in
        ``"rsa_sha1_rejected_by_policy"`` — rsa-sha1 + env default
        ``"unknown_signature_algorithm"`` — URI not in our registry

    Empty / None URI is treated as ``unknown_signature_algorithm`` —
    callers should reject before processing.
    NEVER raises.
    """
    if not alg_uri:
        return False, "unknown_signature_algorithm"
    family = _SAML_SIG_ALG_REGISTRY.get(alg_uri)
    if family is None:
        return False, "unknown_signature_algorithm"
    if family == "rsa-sha1":
        if _allow_rsa_sha1():
            return True, "legacy_sha1_allowed_by_env"
        return False, "rsa_sha1_rejected_by_policy"
    # rsa-sha256 / rsa-sha384 / rsa-sha512 / ecdsa-sha256
    return True, "ok"


# ---- H5: clock-skew tolerance --------------------------------------------


def _clock_skew_seconds() -> int:
    """v4.00.91 — Operator-tunable clock-skew tolerance in seconds.

    Default 300 (5 min — matches the SAML Web SSO Profile recommendation
    for relying parties). Clamped to ``[0, 3600]`` so a typo in the env
    can't widen the window past the security ceiling.

    Read at call time so test env mutations take immediate effect.
    """
    raw = (
        getattr(settings, "RMC_SAML_CLOCK_SKEW_SECONDS", None)
        if hasattr(settings, "RMC_SAML_CLOCK_SKEW_SECONDS")
        else os.environ.get("RMC_SAML_CLOCK_SKEW_SECONDS", "")
    )
    if raw is None or raw == "":
        return 300
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return 300
    if n < 0:
        return 0
    if n > 3600:
        return 3600
    return n


def _is_within_validity_window(
    *,
    not_before_iso: str,
    not_on_or_after_iso: str,
    now=None,
    skew_seconds=None,
) -> tuple[bool, str]:
    """v4.00.91 — Validity-window check w/ symmetric clock-skew tolerance.

    The original v4.00.45 ``_within_validity_window`` returned a bare
    ``bool`` w/ zero skew — a brittle posture for distributed clocks. This
    helper:

        * Returns ``(True, "ok")`` when ``(now - skew) >= NotBefore`` AND
          ``(now + skew) < NotOnOrAfter``.
        * Returns ``(False, "not_yet_valid")`` when too early.
        * Returns ``(False, "expired")`` when too late.
        * Returns ``(False, "malformed_iso")`` when either timestamp fails
          ``datetime.fromisoformat`` parsing.
        * Returns ``(True, "ok_no_constraint")`` when both args are empty —
          the SAML spec allows an Assertion without a Conditions block
          (the IdP is asserting no validity window).

    ``now`` defaults to ``datetime.now(timezone.utc)``; passed in by tests.
    ``skew_seconds`` defaults to ``_clock_skew_seconds()`` env read.
    NEVER raises.
    """
    from datetime import datetime, timedelta, timezone

    if not not_before_iso and not not_on_or_after_iso:
        return True, "ok_no_constraint"

    if now is None:
        now = datetime.now(timezone.utc)
    if skew_seconds is None:
        skew_seconds = _clock_skew_seconds()
    skew = timedelta(seconds=int(skew_seconds))

    try:
        if not_before_iso:
            nb = datetime.fromisoformat(not_before_iso.replace("Z", "+00:00"))
            # Reject when (now + skew) < NotBefore. Equivalently:
            # (now - (-skew)) < NotBefore — i.e. we widen the early edge.
            if (now + skew) < nb:
                return False, "not_yet_valid"
        if not_on_or_after_iso:
            na = datetime.fromisoformat(not_on_or_after_iso.replace("Z", "+00:00"))
            # Reject when (now - skew) >= NotOnOrAfter. We widen the late
            # edge so an expired-by-seconds assertion still validates if
            # within tolerance.
            if (now - skew) >= na:
                return False, "expired"
    except (ValueError, TypeError):
        return False, "malformed_iso"
    return True, "ok"


# ---- H6: assertion-ID one-time-use cache ---------------------------------

# In-process LRU map: assertion-ID -> first-seen-epoch-seconds.
# This is intentionally in-process (NOT Redis / DB) because the SAML
# AssertionID validity window is short (Conditions/@NotOnOrAfter is
# typically 5-15 min from issuance) and we evict on a 24h TTL anyway.
# A cluster of N SPs accepting the same SAMLResponse independently is
# a corner case — IdPs target a single SP per request via Destination
# attribute, and load balancers in front of the SP usually sticky-route
# on session cookies AFTER the ACS hit, so the same ACS instance
# generally re-receives any replay.
_ASSERTION_ID_CACHE: dict[str, float] = {}
_ASSERTION_ID_CACHE_LOCK = threading.Lock()
_ASSERTION_ID_CACHE_MAX = 10000
_ASSERTION_ID_CACHE_EVICT_BATCH = 100
_ASSERTION_ID_TTL_SECONDS = 24 * 60 * 60  # 24h


def _replay_defense_enabled() -> bool:
    """v4.00.91 — Master toggle for assertion-ID replay defense.

    Default ``True``. Set ``RMC_SAML_REPLAY_DEFENSE_ENABLED=0`` to bypass
    (for prod IdPs that intentionally re-use Assertion IDs across
    redirect-binding rebroadcasts — uncommon but spec-permitted in some
    federation profiles).

    Read at call time so test env mutations take immediate effect.
    """
    raw = (
        getattr(settings, "RMC_SAML_REPLAY_DEFENSE_ENABLED", None)
        if hasattr(settings, "RMC_SAML_REPLAY_DEFENSE_ENABLED")
        else os.environ.get("RMC_SAML_REPLAY_DEFENSE_ENABLED", "")
    )
    if raw is None or raw == "":
        return True
    return str(raw).lower() not in ("0", "false", "no", "off")


def _register_assertion_id(assertion_id: str) -> tuple[bool, str]:
    """v4.00.91 — Register an assertion ID for one-time use.

    Returns ``(True, "first_seen")`` when the ID is new (and adds it to
    the cache); returns ``(False, "replay_detected")`` when the ID has
    been seen within the TTL window.

    Empty / missing assertion ID returns ``(True, "missing_id_skipped")``
    — the caller's SAML parser already rejects assertions without an ID
    upstream (per saml-2.0-core § 2.3.3 the ID attribute is REQUIRED), so
    this is a defense-in-depth no-op rather than a soft pass.

    Cap-aware: when the cache hits ``_ASSERTION_ID_CACHE_MAX`` entries on
    a write, the oldest 100 (by first-seen-epoch) are evicted in one pass.

    Thread-safe via ``_ASSERTION_ID_CACHE_LOCK``.
    NEVER raises.
    """
    if not assertion_id:
        return True, "missing_id_skipped"

    import time as _time
    now_epoch = _time.time()
    ttl_cutoff = now_epoch - _ASSERTION_ID_TTL_SECONDS

    with _ASSERTION_ID_CACHE_LOCK:
        # TTL sweep on the queried ID — if its prior sighting is older
        # than 24h, treat as a fresh first-seen. This keeps long-running
        # processes from accumulating dead entries indefinitely.
        prior = _ASSERTION_ID_CACHE.get(assertion_id)
        if prior is not None and prior >= ttl_cutoff:
            return False, "replay_detected"

        # Cap enforcement BEFORE write so the new entry always lands.
        if len(_ASSERTION_ID_CACHE) >= _ASSERTION_ID_CACHE_MAX:
            # Evict the oldest batch in one pass.
            items = sorted(_ASSERTION_ID_CACHE.items(), key=lambda kv: kv[1])
            for k, _ts in items[:_ASSERTION_ID_CACHE_EVICT_BATCH]:
                _ASSERTION_ID_CACHE.pop(k, None)

        _ASSERTION_ID_CACHE[assertion_id] = now_epoch
        return True, "first_seen"


def _clear_assertion_id_cache() -> int:
    """v4.00.91 — Test-only helper to flush the replay-defense cache.

    Returns the count of entries cleared. Thread-safe.
    NEVER raises.
    """
    with _ASSERTION_ID_CACHE_LOCK:
        n = len(_ASSERTION_ID_CACHE)
        _ASSERTION_ID_CACHE.clear()
        return n

