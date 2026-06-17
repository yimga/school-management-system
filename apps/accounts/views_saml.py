"""Enterprise SAML SSO baseline views (tenant-scoped)."""

from __future__ import annotations

import base64
import logging
from binascii import Error as BinasciiError
import secrets
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from django.contrib.auth import login

logger = logging.getLogger(__name__)
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.accounts.federation_sso_health import record_sso_failure, record_sso_success
from apps.siteconfig.integration_registry import resolve_service_integration
from apps.integrations_marketplace.models import ServiceIntegration


def _resolve_school(request):
    school = getattr(request, "school", None)
    if school:
        return school
    slug = (request.GET.get("school_slug") or "").strip()
    if not slug:
        return None
    return School.objects.filter(slug=slug, is_active=True).first()


def _resolve_saml_integration(school, integration_ref: str):
    if not school:
        return None
    qs = ServiceIntegration.objects.filter(
        school=school,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        is_active=True,
    )
    try:
        pk = int(integration_ref)
        item = qs.filter(pk=pk).first()
        if item:
            return item
    except ValueError:
        pass
    ref = str(integration_ref).strip()
    direct = qs.filter(service_name__iexact=ref).first()
    if direct:
        return direct
    return resolve_service_integration(
        school,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        service_name=ref,
        name_hints=[ref, "saml"],
        allow_legacy_backfill=True,
    )


def _xml_text(node):
    if node is None:
        return ""
    return (node.text or "").strip()


def _parse_saml_response(xml_bytes: bytes) -> dict:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}

    subject_name_id = ""
    for node in root.findall(".//{*}NameID"):
        subject_name_id = _xml_text(node)
        if subject_name_id:
            break

    attrs = {}
    for attr in root.findall(".//{*}Attribute"):
        key = str(
            attr.attrib.get("Name") or attr.attrib.get("FriendlyName") or ""
        ).strip()
        if not key:
            continue
        values = []
        for val in attr.findall(".//{*}AttributeValue"):
            txt = _xml_text(val)
            if txt:
                values.append(txt)
        if values:
            attrs[key] = values

    def first(*keys):
        for key in keys:
            values = attrs.get(key) or []
            if values:
                return values[0]
        return ""

    groups = attrs.get("groups") or attrs.get("roles") or []
    return {
        "name_id": subject_name_id,
        "email": first("email", "mail", "EmailAddress"),
        "given_name": first("given_name", "first_name", "givenName", "FirstName"),
        "family_name": first("family_name", "last_name", "sn", "surname", "LastName"),
        "groups": groups if isinstance(groups, list) else [],
    }


class _NoSamlCertificate(Exception):
    """Raised when no IdP signing certificate is configured for the integration."""


def _idp_certificate_pem(cfg: dict) -> str:
    """Return the configured IdP signing cert as PEM (wrapping bare base64)."""
    raw = ""
    for key in (
        "idp_x509_cert",
        "idp_certificate",
        "x509_cert",
        "certificate",
        "idp_cert",
    ):
        value = str(cfg.get(key) or "").strip()
        if value:
            raw = value
            break
    if not raw:
        return ""
    if "BEGIN CERTIFICATE" in raw:
        return raw
    body = "\n".join(raw[i : i + 64] for i in range(0, len(raw), 64))
    return f"-----BEGIN CERTIFICATE-----\n{body}\n-----END CERTIFICATE-----\n"


def _verify_saml_signature(xml_bytes: bytes, cfg: dict) -> bytes:
    """Verify the SAML XML-DSig against the configured IdP cert.

    Returns the canonical bytes of the signature-covered (signed) element so claims are
    only ever read from signed data — defeating signature-wrapping. Raises
    ``_NoSamlCertificate`` when no cert is configured (caller must fail closed) and lets
    any signxml/parse error propagate (also a fail-closed signal).
    """
    cert_pem = _idp_certificate_pem(cfg)
    if not cert_pem:
        raise _NoSamlCertificate()
    from lxml import etree
    from signxml import XMLVerifier

    doc = etree.fromstring(xml_bytes)
    result = XMLVerifier().verify(doc, x509_cert=cert_pem)
    if isinstance(result, list):
        if not result:
            raise ValueError("no verified SAML signature")
        result = result[0]
    return etree.tostring(result.signed_xml)


def _choose_user_role(claims: dict, integration: ServiceIntegration) -> str:
    cfg = integration.config or {}
    valid_roles = {choice[0] for choice in User.Role.choices}
    default_role = str(cfg.get("default_role") or User.Role.PARENT).strip().upper()
    if default_role not in valid_roles:
        default_role = User.Role.PARENT
    role_map = cfg.get("role_map") or {}
    if not isinstance(role_map, dict):
        return default_role
    for group in claims.get("groups") or []:
        mapped = str(role_map.get(str(group), "")).strip().upper()
        if mapped in valid_roles:
            return mapped
    return default_role


def _build_authn_request(*, request_id: str, issuer: str, acs_url: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<samlp:AuthnRequest "
        'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{request_id}" Version="2.0" '
        'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'AssertionConsumerServiceURL="{acs_url}">'
        f"<saml:Issuer>{issuer}</saml:Issuer>"
        "</samlp:AuthnRequest>"
    )


@require_GET
def saml_start(request, integration_ref: str):
    school = _resolve_school(request)
    if not school:
        return HttpResponseForbidden("School context required.")
    integration = _resolve_saml_integration(school, integration_ref)
    if not integration:
        return JsonResponse({"error": "SAML integration not found"}, status=404)

    cfg = integration.config or {}
    sso_url = str(cfg.get("sso_url") or integration.endpoint_url or "").strip()
    if not sso_url:
        return JsonResponse(
            {"error": "SAML integration misconfigured", "required": ["sso_url"]},
            status=400,
        )

    request_id = f"_{secrets.token_hex(16)}"
    acs_url = request.build_absolute_uri(
        reverse("accounts:saml_acs", args=[integration.pk])
    )
    issuer = str(
        cfg.get("entity_id") or request.build_absolute_uri(reverse("home"))
    ).strip()
    authn_request_xml = _build_authn_request(
        request_id=request_id, issuer=issuer, acs_url=acs_url
    )
    saml_request = base64.b64encode(authn_request_xml.encode("utf-8")).decode("utf-8")

    relay_state = request_id
    request.session[f"saml:{integration.pk}:{relay_state}"] = {
        "school_id": str(school.pk),
        "next": request.GET.get("next") or "",
    }
    request.session.modified = True

    params = {"SAMLRequest": saml_request, "RelayState": relay_state}
    joiner = "&" if "?" in sso_url else "?"
    return redirect(f"{sso_url}{joiner}{urlencode(params)}")


@csrf_exempt
@require_http_methods(["POST"])
def saml_acs(request, integration_id: int):
    relay_state = (request.POST.get("RelayState") or "").strip()
    if not relay_state:
        record_sso_failure(integration_id, "Missing RelayState")
        return JsonResponse({"error": "Missing RelayState"}, status=400)

    pending = request.session.get(f"saml:{integration_id}:{relay_state}") or {}
    if not pending:
        record_sso_failure(integration_id, "Invalid or expired RelayState")
        return JsonResponse({"error": "Invalid or expired RelayState"}, status=403)

    integration = (
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        ServiceIntegration.objects.filter(
            pk=integration_id,
            service_type=ServiceIntegration.ServiceType.OAUTH,
            is_active=True,
        )
        .select_related("school")
        .first()
    )
    if not integration:
        record_sso_failure(integration_id, "SAML integration not found")
        return JsonResponse({"error": "SAML integration not found"}, status=404)
    school = integration.school
    if str(pending.get("school_id")) != str(school.pk):
        record_sso_failure(integration_id, "Tenant mismatch")
        return JsonResponse({"error": "Tenant mismatch"}, status=403)

    cfg = integration.config or {}
    saml_response = (request.POST.get("SAMLResponse") or "").strip()
    if not saml_response:
        record_sso_failure(integration_id, "Missing SAMLResponse")
        return JsonResponse({"error": "Missing SAMLResponse"}, status=400)
    try:
        xml_bytes = base64.b64decode(saml_response, validate=True)
    except (BinasciiError, ValueError):
        record_sso_failure(integration_id, "Invalid SAMLResponse")
        return JsonResponse({"error": "Invalid SAMLResponse"}, status=400)

    # SECURITY (2026-06-17 auth-bypass seal): verify the assertion's XML signature against
    # the configured IdP certificate BEFORE trusting any attribute. A SAML assertion is
    # always relayed through the browser, so there is no transport fallback — if no cert
    # is configured we fail closed. Claims are parsed only from the signed subtree.
    try:
        signed_xml_bytes = _verify_saml_signature(xml_bytes, cfg)
    except _NoSamlCertificate:
        logger.warning(
            "SAML rejected: no IdP signing certificate configured for integration %s",
            integration_id,
        )
        record_sso_failure(integration_id, "SAML IdP certificate not configured")
        return JsonResponse(
            {"error": "SAML SSO not fully configured (missing IdP certificate)"},
            status=400,
        )
    except Exception:  # any verification/parse failure -> reject (fail closed)
        logger.warning(
            "SAML signature verification failed for integration %s", integration_id
        )
        record_sso_failure(integration_id, "SAML signature verification failed")
        return JsonResponse(
            {"error": "SAML signature verification failed"}, status=401
        )

    claims = _parse_saml_response(signed_xml_bytes)
    if not claims:
        record_sso_failure(integration_id, "Could not parse SAML assertion")
        return JsonResponse({"error": "Could not parse SAML assertion"}, status=400)

    email = (claims.get("email") or "").strip().lower()
    name_id = (claims.get("name_id") or "").strip()
    if not email and not name_id:
        record_sso_failure(integration_id, "No account identifier in SAML assertion")
        return JsonResponse(
            {"error": "No account identifier in SAML assertion"}, status=400
        )

    username_seed = (
        email.split("@")[0] if email else name_id
    ) or f"saml_{name_id[:12]}"
    username = username_seed[:150]
    role = _choose_user_role(claims, integration)

    user = User.objects.filter(email__iexact=email).first() if email else None
    if not user:
        user = User.objects.filter(username__iexact=username).first()
    if not user:
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=str(claims.get("given_name") or "").strip(),
            last_name=str(claims.get("family_name") or "").strip(),
            role=role,
            password=secrets.token_urlsafe(24),
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
    else:
        dirty = False
        if email and user.email != email:
            user.email = email
            dirty = True
        if not user.first_name and claims.get("given_name"):
            user.first_name = str(claims.get("given_name")).strip()
            dirty = True
        if not user.last_name and claims.get("family_name"):
            user.last_name = str(claims.get("family_name")).strip()
            dirty = True
        if user.role != role:
            user.role = role
            dirty = True
        if dirty:
            user.save()

    SchoolMembership.objects.get_or_create(
        school=school,
        user=user,
        defaults={"role": role, "is_primary": True},
    )

    session_key = f"saml:{integration_id}:{relay_state}"
    if session_key in request.session:
        del request.session[session_key]
        request.session.modified = True

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    record_sso_success(integration_id)
    # Audit log (no PII): acs_request_id, integration_id (idp proxy), authenticated
    logger.info(
        "saml_acs_success",
        extra={
            "acs_request_id": relay_state,
            "integration_id": integration_id,
            "authenticated": True,
        },
    )
    next_url = (
        str(pending.get("next") or "").strip()
        or str((integration.config or {}).get("post_login_redirect") or "").strip()
    )
    return redirect(next_url or reverse("accounts:redirect"))


@require_GET
def saml_metadata(request, integration_id: int):
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    integration = ServiceIntegration.objects.filter(
        pk=integration_id,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        is_active=True,
    ).first()
    if not integration:
        return JsonResponse({"error": "SAML integration not found"}, status=404)
    acs_url = request.build_absolute_uri(
        reverse("accounts:saml_acs", args=[integration.pk])
    )
    entity_id = str(
        (integration.config or {}).get("entity_id")
        or request.build_absolute_uri(reverse("home"))
    ).strip()
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" '
        f'entityID="{entity_id}">'
        '<SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
        "<AssertionConsumerService "
        'Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'Location="{acs_url}" index="0" isDefault="true"/>'
        "</SPSSODescriptor>"
        "</EntityDescriptor>"
    )
    return HttpResponse(xml, content_type="application/samlmetadata+xml")
