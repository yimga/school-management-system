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

    hash_alg = hashes.SHA256() if hash_name == "sha256" else hashes.SHA1()
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

    try:
        root = ET.fromstring(decoded)
    except ET.ParseError as exc:
        return {"error": f"bad_xml: {exc}"}

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
        }

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
        "attributes": attrs,
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
    """RFC 3339 / ISO 8601 timestamp check against now()."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    try:
        if not_before:
            nb = datetime.fromisoformat(not_before.replace("Z", "+00:00"))
            if now < nb:
                return False
        if not_on_or_after:
            na = datetime.fromisoformat(not_on_or_after.replace("Z", "+00:00"))
            if now >= na:
                return False
    except ValueError:
        return False
    return True


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


def _extract_saml_attr(attrs: dict, priority: tuple) -> str:
    """Walk the priority list, return first non-empty stripped value."""
    for key in priority:
        val = attrs.get(key, "")
        if val and str(val).strip():
            return str(val).strip()
    return ""


def _provision_user_from_saml(name_id: str, attrs: dict) -> tuple:
    """Get-or-create User by email (NameID often *is* the email). Returns
    ``(user, created)``.

    v4.00.66 — Attribute lookup now routes through the operator-configurable
    map (RMC_SAML_ATTR_FIRST_NAME / _LAST_NAME / _EMAIL). Defaults preserve
    v4.00.45 behavior so unconfigured deployments keep working.
    """
    from django.contrib.auth import get_user_model

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

    if not _within_validity_window(parsed.get("not_before", ""), parsed.get("not_on_or_after", "")):
        return JsonResponse({"success": False, "stage": "validity_window_failed", "not_before": parsed.get("not_before", ""), "not_on_or_after": parsed.get("not_on_or_after", "")}, status=401)

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

    try:
        user, created = _provision_user_from_saml(name_id, parsed.get("attributes") or {})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"success": False, "stage": "provision_failed", "detail": str(exc)}, status=500)

    try:
        _login_saml_session(request, user)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"success": False, "stage": "session_login_failed", "detail": str(exc)}, status=500)

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
    """
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
