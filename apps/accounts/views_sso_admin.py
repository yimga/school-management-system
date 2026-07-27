"""Tenant-admin self-serve SSO connection wizard (F5b).

Lets a school admin create + manage OIDC / SAML single-sign-on connections
without the Django admin. Each connection is a per-school ``ServiceIntegration``
(service_type=OAUTH) row — the exact row the login page's SSO buttons
(``_get_login_sso_integrations``) and the OIDC/SAML flows (``views_oidc`` /
``views_saml``) already consume — so saving one here lights up the
"Sign in with Google / Microsoft / SSO" button on this school's login page
automatically.
"""

from __future__ import annotations

import json
import logging
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import User
from apps.accounts.sso_connection_service import (
    SSO_PROVIDER_PRESETS,
    fetch_oidc_discovery,
    preset_idp_type,
    provider_choices,
    resolve_discovery_url,
)
from apps.accounts.tenant_user_provisioning import (
    is_provisionable_role,
    provisionable_role_choices,
)
from apps.integrations_marketplace.models import ServiceIntegration
from apps.schools.mixins import require_school

logger = logging.getLogger(__name__)

_OAUTH = ServiceIntegration.ServiceType.OAUTH
_DEFAULT_SCOPE = "openid email profile"


def _can_manage(user, school) -> bool:
    # Lazy import avoids any accounts view-module load-order coupling.
    from apps.accounts.views_tenant_identity import _can_manage_tenant_identity

    return _can_manage_tenant_identity(user, school)


def _unique_service_name(school, base: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", base or "").strip("-").lower()[:80] or "sso"
    name = slug
    i = 1
    while ServiceIntegration.objects.filter(  # tenant-isolation-allow: uniqueness probe scoped to the request.school SSO admin surface
        school=school, campus__isnull=True, service_name__iexact=name
    ).exists():
        i += 1
        name = f"{slug}-{i}"[:100]
    return name


def _connection_rows(school):
    rows = []
    for c in ServiceIntegration.objects.filter(  # tenant-isolation-allow: request.school-scoped SSO connections list for the tenant admin
        school=school, service_type=_OAUTH
    ).order_by("service_name"):
        cfg = c.config or {}
        idp_type = str(cfg.get("idp_type") or "oidc")
        if idp_type == "saml":
            live = bool(cfg.get("sso_url")) and bool(cfg.get("idp_x509_cert"))
        else:
            live = bool(cfg.get("authorization_endpoint")) and bool(cfg.get("token_endpoint"))
        rows.append(
            {
                "obj": c,
                "idp_type": idp_type,
                "label": cfg.get("display_name") or c.service_name,
                "default_role": cfg.get("default_role") or "",
                "configured": live,
                "login_visible": bool(c.is_active) and live,
            }
        )
    return rows


def _form_from_integration(integration) -> dict:
    cfg = integration.config or {}
    return {
        "provider": _guess_provider(integration, cfg),
        "display_name": cfg.get("display_name") or "",
        "client_id": integration.client_id or "",
        "discovery_url": cfg.get("discovery_url") or "",
        "issuer": cfg.get("issuer") or "",
        "scope": cfg.get("scope") or _DEFAULT_SCOPE,
        "default_role": cfg.get("default_role") or "",
        "role_map": json.dumps(cfg.get("role_map"), indent=2) if cfg.get("role_map") else "",
        "saml_sso_url": cfg.get("sso_url") or "",
        "saml_entity_id": cfg.get("entity_id") or "",
        "saml_cert": cfg.get("idp_x509_cert") or "",
        "is_active": bool(integration.is_active),
    }


def _guess_provider(integration, cfg) -> str:
    if str(cfg.get("idp_type") or "") == "saml":
        return "saml"
    name = (integration.service_name or "").lower()
    disc = (cfg.get("discovery_url") or "").lower()
    if "google" in name or "accounts.google.com" in disc:
        return "google"
    if "microsoft" in name or "azure" in name or "microsoftonline.com" in disc:
        return "microsoft"
    if "okta" in name or "okta.com" in disc:
        return "okta"
    return "oidc"


def _render_page(request, school, *, form=None, edit=None, warnings=None):
    ctx = {
        "school": school,
        "connections": _connection_rows(school),
        "provider_choices": provider_choices(),
        "role_choices": provisionable_role_choices(),
        "form": form or {"provider": "google", "scope": _DEFAULT_SCOPE, "is_active": True},
        "edit": edit,
        "warnings": warnings or [],
        "default_scope": _DEFAULT_SCOPE,
        "probe_url": reverse("accounts:sso_discovery_probe"),
    }
    return render(request, "accounts/sso_connections.html", ctx)


def _parse_role_map(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None, None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None, _("Group→role map must be valid JSON (or left blank).")
    if not isinstance(parsed, dict):
        return None, _("Group→role map must be a JSON object of {group: ROLE}.")
    cleaned = {
        str(k): str(v).strip().upper()
        for k, v in parsed.items()
        if str(k).strip() and is_provisionable_role(str(v))
    }
    return cleaned, None


def _apply_form(request, school, *, existing=None):
    post = request.POST
    provider = (post.get("provider") or "oidc").strip().lower()
    preset = SSO_PROVIDER_PRESETS.get(provider, SSO_PROVIDER_PRESETS["oidc"])
    idp_type = preset_idp_type(provider)
    label = (post.get("display_name") or "").strip() or str(preset.get("label") or provider.title())

    default_role = (post.get("default_role") or "").strip().upper()
    if not is_provisionable_role(default_role):
        default_role = User.Role.PARENT

    config: dict = {"idp_type": idp_type, "display_name": label, "default_role": default_role}
    warnings: list[str] = []
    activate = post.get("is_active") == "on"
    endpoint_url = ""
    client_id = ""

    if idp_type == "oidc":
        client_id = (post.get("client_id") or "").strip()
        if not client_id:
            return _render_page(
                request, school,
                form=_form_from_post(post), edit=existing,
                warnings=[_("A client ID is required for an OIDC connection.")],
            )
        config["scope"] = (post.get("scope") or "").strip() or str(preset.get("scope") or _DEFAULT_SCOPE)
        discovery_url = resolve_discovery_url(
            provider,
            discovery_url=post.get("discovery_url", ""),
            issuer=post.get("issuer", ""),
            tenant=post.get("ms_tenant", ""),
        )
        if discovery_url:
            config["discovery_url"] = discovery_url
            result = fetch_oidc_discovery(discovery_url)
            if result.get("ok"):
                config.update(result["endpoints"])
                endpoint_url = result["endpoints"].get("authorization_endpoint", "")
            else:
                warnings.append(
                    result.get("error", _("Discovery failed."))
                    + " " + _("Saved as a draft — activate once the IdP is reachable.")
                )
                activate = False
        else:
            for key in ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer"):
                val = (post.get(key) or "").strip()
                if val:
                    config[key] = val
            endpoint_url = config.get("authorization_endpoint", "")
            if not (config.get("authorization_endpoint") and config.get("token_endpoint")):
                warnings.append(
                    _("No discovery URL and no manual endpoints — saved as a draft.")
                )
                activate = False
        role_map, role_map_err = _parse_role_map(post.get("role_map", ""))
        if role_map_err:
            return _render_page(
                request, school, form=_form_from_post(post), edit=existing,
                warnings=[role_map_err],
            )
        if role_map:
            config["role_map"] = role_map
    else:  # SAML
        sso_url = (post.get("saml_sso_url") or "").strip()
        entity_id = (post.get("saml_entity_id") or "").strip()
        cert = (post.get("saml_cert") or "").strip()
        config["sso_url"] = sso_url
        if entity_id:
            config["entity_id"] = entity_id
        if cert:
            config["idp_x509_cert"] = cert
        endpoint_url = sso_url
        if not (sso_url and cert):
            warnings.append(
                _("SAML needs an SSO URL and IdP signing certificate — saved as a draft.")
            )
            activate = False

    if existing is not None:
        integration = existing
    else:
        integration = ServiceIntegration(
            school=school, service_name=_unique_service_name(school, label or provider)
        )
    integration.service_type = _OAUTH
    if idp_type == "oidc":
        integration.client_id = client_id
    client_secret = (post.get("client_secret") or "").strip()
    if client_secret:
        integration.client_secret = client_secret
    integration.endpoint_url = endpoint_url or integration.endpoint_url or ""
    integration.config = config
    integration.is_active = activate
    integration.save()

    if warnings:
        for w in warnings:
            messages.warning(request, w)
    else:
        messages.success(
            request,
            _("SSO connection “%(label)s” saved. It now appears on your login page.")
            % {"label": label},
        )
    return redirect("accounts:sso_connections")


def _form_from_post(post) -> dict:
    return {
        "provider": (post.get("provider") or "oidc"),
        "display_name": post.get("display_name", ""),
        "client_id": post.get("client_id", ""),
        "discovery_url": post.get("discovery_url", ""),
        "issuer": post.get("issuer", ""),
        "ms_tenant": post.get("ms_tenant", ""),
        "scope": post.get("scope", "") or _DEFAULT_SCOPE,
        "default_role": post.get("default_role", ""),
        "role_map": post.get("role_map", ""),
        "saml_sso_url": post.get("saml_sso_url", ""),
        "saml_entity_id": post.get("saml_entity_id", ""),
        "saml_cert": post.get("saml_cert", ""),
        "is_active": post.get("is_active") == "on",
    }


@login_required
@require_school
@require_http_methods(["GET", "POST"])
def sso_connections(request):
    school = request.school
    if not _can_manage(request.user, school):
        return HttpResponseForbidden(_("You do not have permission to manage SSO for this school."))
    if request.method == "POST":
        return _apply_form(request, school)
    return _render_page(request, school)


@login_required
@require_school
@require_http_methods(["GET", "POST"])
def sso_connection_edit(request, pk: int):
    school = request.school
    if not _can_manage(request.user, school):
        return HttpResponseForbidden(_("You do not have permission to manage SSO for this school."))
    integration = get_object_or_404(
        ServiceIntegration, pk=pk, school=school, service_type=_OAUTH
    )
    if request.method == "POST":
        return _apply_form(request, school, existing=integration)
    return _render_page(request, school, form=_form_from_integration(integration), edit=integration)


@login_required
@require_school
@require_POST
def sso_connection_toggle(request, pk: int):
    school = request.school
    if not _can_manage(request.user, school):
        return HttpResponseForbidden(_("Not permitted."))
    integration = get_object_or_404(
        ServiceIntegration, pk=pk, school=school, service_type=_OAUTH
    )
    integration.is_active = not integration.is_active
    integration.save(update_fields=["is_active"])
    messages.success(
        request,
        _("SSO connection %(state)s.")
        % {"state": _("enabled") if integration.is_active else _("disabled")},
    )
    return redirect("accounts:sso_connections")


@login_required
@require_school
@require_POST
def sso_connection_delete(request, pk: int):
    school = request.school
    if not _can_manage(request.user, school):
        return HttpResponseForbidden(_("Not permitted."))
    integration = get_object_or_404(
        ServiceIntegration, pk=pk, school=school, service_type=_OAUTH
    )
    integration.delete()
    messages.success(request, _("SSO connection removed."))
    return redirect("accounts:sso_connections")


@login_required
@require_school
@require_POST
def sso_discovery_probe(request):
    """AJAX: fetch an OIDC discovery doc and return its endpoints (autofill + test)."""
    school = request.school
    if not _can_manage(request.user, school):
        return JsonResponse({"ok": False, "error": _("Not permitted.")}, status=403)
    provider = (request.POST.get("provider") or "oidc").strip().lower()
    discovery_url = resolve_discovery_url(
        provider,
        discovery_url=request.POST.get("discovery_url", ""),
        issuer=request.POST.get("issuer", ""),
        tenant=request.POST.get("ms_tenant", ""),
    )
    if not discovery_url:
        return JsonResponse(
            {"ok": False, "error": _("Enter a discovery URL or issuer to test.")}
        )
    result = fetch_oidc_discovery(discovery_url)
    result["discovery_url"] = discovery_url
    return JsonResponse(result)
