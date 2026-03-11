"""Enterprise SAML SSO baseline views (tenant-scoped)."""

from __future__ import annotations

import base64
import secrets
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from django.contrib.auth import login
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
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
    except Exception:
        return {}

    subject_name_id = ""
    for node in root.findall(".//{*}NameID"):
        subject_name_id = _xml_text(node)
        if subject_name_id:
            break

    attrs = {}
    for attr in root.findall(".//{*}Attribute"):
        key = str(attr.attrib.get("Name") or attr.attrib.get("FriendlyName") or "").strip()
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


def _choose_user_role(claims: dict, integration: ServiceIntegration) -> str:
    cfg = integration.config or {}
    valid_roles = {choice[0] for choice in User.Role.choices}
    default_role = str(cfg.get("default_role") or User.Role.PARENT).strip().upper()
    if default_role not in valid_roles:
        default_role = User.Role.PARENT
    role_map = cfg.get("role_map") or {}
    if not isinstance(role_map, dict):
        return default_role
    for group in (claims.get("groups") or []):
        mapped = str(role_map.get(str(group), "")).strip().upper()
        if mapped in valid_roles:
            return mapped
    return default_role


def _build_authn_request(*, request_id: str, issuer: str, acs_url: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<samlp:AuthnRequest '
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
        return JsonResponse({"error": "SAML integration misconfigured", "required": ["sso_url"]}, status=400)

    request_id = f"_{secrets.token_hex(16)}"
    acs_url = request.build_absolute_uri(reverse("accounts:saml_acs", args=[integration.pk]))
    issuer = str(cfg.get("entity_id") or request.build_absolute_uri(reverse("home"))).strip()
    authn_request_xml = _build_authn_request(request_id=request_id, issuer=issuer, acs_url=acs_url)
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
@require_http_methods(["GET", "POST"])
def saml_acs(request, integration_id: int):
    relay_state = (
        (request.POST.get("RelayState") or "").strip()
        or (request.GET.get("RelayState") or "").strip()
    )
    if not relay_state:
        return JsonResponse({"error": "Missing RelayState"}, status=400)

    pending = request.session.get(f"saml:{integration_id}:{relay_state}") or {}
    if not pending:
        return JsonResponse({"error": "Invalid or expired RelayState"}, status=403)

    integration = ServiceIntegration.objects.filter(
        pk=integration_id,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        is_active=True,
    ).select_related("school").first()
    if not integration:
        return JsonResponse({"error": "SAML integration not found"}, status=404)
    school = integration.school
    if str(pending.get("school_id")) != str(school.pk):
        return JsonResponse({"error": "Tenant mismatch"}, status=403)

    saml_response = (
        (request.POST.get("SAMLResponse") or "").strip()
        or (request.GET.get("SAMLResponse") or "").strip()
    )
    if not saml_response:
        return JsonResponse({"error": "Missing SAMLResponse"}, status=400)
    try:
        xml_bytes = base64.b64decode(saml_response)
    except Exception:
        return JsonResponse({"error": "Invalid SAMLResponse"}, status=400)

    claims = _parse_saml_response(xml_bytes)
    if not claims:
        return JsonResponse({"error": "Could not parse SAML assertion"}, status=400)

    email = (claims.get("email") or "").strip().lower()
    name_id = (claims.get("name_id") or "").strip()
    if not email and not name_id:
        return JsonResponse({"error": "No account identifier in SAML assertion"}, status=400)

    username_seed = (email.split("@")[0] if email else name_id) or f"saml_{name_id[:12]}"
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

    try:
        del request.session[f"saml:{integration_id}:{relay_state}"]
        request.session.modified = True
    except Exception:
        pass

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    next_url = str(pending.get("next") or "").strip() or str((integration.config or {}).get("post_login_redirect") or "").strip()
    return redirect(next_url or reverse("accounts:redirect"))


@require_GET
def saml_metadata(request, integration_id: int):
    integration = ServiceIntegration.objects.filter(
        pk=integration_id,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        is_active=True,
    ).first()
    if not integration:
        return JsonResponse({"error": "SAML integration not found"}, status=404)
    acs_url = request.build_absolute_uri(reverse("accounts:saml_acs", args=[integration.pk]))
    entity_id = str((integration.config or {}).get("entity_id") or request.build_absolute_uri(reverse("home"))).strip()
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" '
        f'entityID="{entity_id}">'
        '<SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
        '<AssertionConsumerService '
        'Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'Location="{acs_url}" index="0" isDefault="true"/>'
        '</SPSSODescriptor>'
        '</EntityDescriptor>'
    )
    return HttpResponse(xml, content_type="application/samlmetadata+xml")
