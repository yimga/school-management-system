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
    sig_present = root.find("{http://www.w3.org/2000/09/xmldsig#}Signature") is not None or (
        assertion.find("{http://www.w3.org/2000/09/xmldsig#}Signature") is not None
    )

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
        "attributes": attrs,
    }


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


def _provision_user_from_saml(name_id: str, attrs: dict) -> tuple:
    """Get-or-create User by email (NameID often *is* the email). Returns
    ``(user, created)``."""
    from django.contrib.auth import get_user_model

    UserModel = get_user_model()
    email = (attrs.get("email") or attrs.get("mail") or "").strip().lower()
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
    given = (attrs.get("givenName") or attrs.get("firstName") or "").strip()
    family = (attrs.get("sn") or attrs.get("surname") or attrs.get("familyName") or "").strip()
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


@require_http_methods(["GET", "POST"])
def sls(request):
    """SLO endpoint stub — logs + acks; full SLO flow deferred."""
    logger.info("saml sls: logout request received (method=%s)", request.method)
    return JsonResponse({"success": True, "stage": "logout-acknowledged"})
