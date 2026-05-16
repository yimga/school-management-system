"""
Integrations Hub — tenant-facing UI + OAuth dance entry/exit views.

Routes (mounted at /integrations/ in config/urls.py):

  GET  /integrations/                          → hub catalog (school-scoped)
  GET  /integrations/connect/<slug>/           → start OAuth dance for slug
  GET  /integrations/callback/<slug>/          → finish OAuth dance
  POST /integrations/disconnect/<slug>/        → mark row inactive (per-school)
  POST /integrations/disconnect/<slug>/<campus_id>/  → per-campus disconnect

All views are `@login_required` and refuse access when no `request.school` is
present (mirrors the tenant-resolution contract used by views_lexicon /
views_configure / views_at_risk_labeling).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.integrations_marketplace.connector_registry import (
    CATEGORY_LABELS,
    get_connector,
    list_connectors_by_category,
)
from apps.integrations_marketplace.oauth import (
    build_authorize_redirect,
    build_token_exchange_payload,
    persist_oauth_tokens,
    validate_callback_state,
)
from apps.integrations_marketplace.resolver import list_connections_for_school

logger = logging.getLogger(__name__)


def _user_can_manage(request: HttpRequest) -> bool:
    """School admins / principals / proprietors can manage integrations."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    role = (getattr(user, "role", "") or "").lower()
    # role-string-allow: tenant operator gate mirrors views_lexicon._user_can_edit;
    # canonical role names live in apps.accounts.permissions / role_registry which
    # the SOT scanner already exempts.
    return role in {"admin", "principal", "proprietor"}


def _resolve_campus(school, campus_id):
    """Resolve campus_id to a Campus row, scoped to school. None on miss."""
    if not campus_id:
        return None
    try:
        cid = int(campus_id)
    except (TypeError, ValueError):
        return None
    from apps.schoolops.models import Campus

    return Campus.objects.filter(school=school, pk=cid).first()


# ---------------------------------------------------------------------------
# Hub
# ---------------------------------------------------------------------------

@login_required
def integrations_hub(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    if school is None:
        return render(
            request,
            "integrations_marketplace/no_tenant.html",
            status=400,
        )
    if not _user_can_manage(request):
        return render(
            request,
            "integrations_marketplace/forbidden.html",
            status=403,
        )

    # Wave v2.76: optional ?campus=<id> scopes the hub to a specific campus.
    # Per-campus rows take precedence over school-level rows in the cascade,
    # so the displayed status reflects what the resolver would actually return
    # for that campus.
    selected_campus = _resolve_campus(school, request.GET.get("campus"))

    from apps.integrations_marketplace.resolver import resolve_connector_config
    from apps.integrations_marketplace.connector_registry import list_connectors

    connections: list[dict] = []
    for connector in list_connectors():
        resolved = resolve_connector_config(
            connector.slug, school=school, campus=selected_campus
        )
        cdict = connector.to_dict()
        # Pre-build the brand-mark class server-side so the template doesn't carry
        # a `--{{ var }}` literal that trips scan_undefined_css_classes (the
        # scanner strips Django tags and would see the orphan `rmc-integration-mark--`).
        cdict["brand_mark_class"] = f"rmc-integration-mark rmc-integration-mark--{connector.slug}"
        connections.append({
            "connector": cdict,
            "source": resolved.source if resolved else "none",
            "is_configured": bool(resolved and resolved.is_configured),
            "is_active": bool(resolved and resolved.is_active),
            "integration_id": resolved.integration_id if resolved else None,
        })

    grouped: dict[str, list[dict]] = {}
    for entry in connections:
        cat = entry["connector"]["category"]
        grouped.setdefault(cat, []).append(entry)

    category_order = [
        "meeting", "calendar", "mailbox", "transactional_mail", "chat",
        "messaging", "payment", "lms", "badges",
    ]
    sections = [
        {
            "slug": slug,
            "label": CATEGORY_LABELS.get(slug, slug),
            "entries": grouped.get(slug, []),
        }
        for slug in category_order
        if grouped.get(slug)
    ]

    from apps.schoolops.models import Campus
    available_campuses = list(
        Campus.objects.filter(school=school, is_active=True).order_by("name")
    )

    ctx = {
        "school": school,
        "sections": sections,
        "connections": connections,
        "selected_campus": selected_campus,
        "available_campuses": available_campuses,
    }
    return render(request, "integrations_marketplace/hub.html", ctx)


# ---------------------------------------------------------------------------
# OAuth — connect
# ---------------------------------------------------------------------------

@login_required
def oauth_connect(request: HttpRequest, connector_slug: str) -> HttpResponse:
    school = getattr(request, "school", None)
    if school is None or not _user_can_manage(request):
        return render(
            request,
            "integrations_marketplace/forbidden.html",
            status=403,
        )

    campus = _resolve_campus(school, request.GET.get("campus"))
    url, diag = build_authorize_redirect(
        request=request,
        connector_slug=connector_slug,
        school=school,
        campus=campus,
        redirect_back=request.GET.get("next") or reverse(
            "integrations_marketplace:hub"
        ),
    )
    if url is None:
        logger.warning("OAuth connect refused: %s", diag)
        messages.error(
            request,
            _refusal_message(diag),
        )
        return redirect("integrations_marketplace:hub")
    return HttpResponseRedirect(url)


# ---------------------------------------------------------------------------
# OAuth — callback
# ---------------------------------------------------------------------------

@login_required
def oauth_callback(request: HttpRequest, connector_slug: str) -> HttpResponse:
    school = getattr(request, "school", None)
    if school is None or not _user_can_manage(request):
        return render(
            request,
            "integrations_marketplace/forbidden.html",
            status=403,
        )

    connector = get_connector(connector_slug)
    if connector is None:
        messages.error(request, f"Unknown connector: {connector_slug}")
        return redirect("integrations_marketplace:hub")

    error = request.GET.get("error")
    if error:
        messages.error(
            request,
            f"{connector.label} authorisation was cancelled or refused ({error}).",
        )
        return redirect("integrations_marketplace:hub")

    code = (request.GET.get("code") or "").strip()
    state = request.GET.get("state") or ""
    payload, diag = validate_callback_state(
        request=request, connector_slug=connector_slug, state=state
    )
    if payload is None:
        logger.warning("OAuth state validation failed: %s", diag)
        messages.error(
            request,
            "Could not validate the authorisation response. Please try again.",
        )
        return redirect("integrations_marketplace:hub")
    if not code:
        messages.error(request, "Authorisation response did not include a code.")
        return redirect("integrations_marketplace:hub")

    # Re-resolve scope from the signed state so the user can't tamper via query string.
    campus = None
    if payload.get("campus_id"):
        from apps.schoolops.models import Campus

        campus = Campus.objects.filter(
            school=school, pk=payload["campus_id"]
        ).first()

    body = build_token_exchange_payload(
        request=request,
        connector=connector,
        code=code,
        state_payload=payload,
    )

    token_response = _exchange_code_for_tokens(
        token_url=connector.token_url, body=body
    )
    if not isinstance(token_response, dict) or not token_response.get("access_token"):
        logger.warning(
            "OAuth token exchange failed for %s: %s",
            connector.slug,
            token_response,
        )
        messages.error(
            request,
            f"{connector.label} token exchange failed. Check platform credentials.",
        )
        return redirect("integrations_marketplace:hub")

    try:
        persist_oauth_tokens(
            connector=connector,
            school=school,
            campus=campus,
            token_response=token_response,
        )
    except ValueError as exc:
        logger.warning("OAuth persistence refused for %s: %s", connector.slug, exc)
        messages.error(request, f"Could not save {connector.label} connection: {exc}")
        return redirect("integrations_marketplace:hub")

    request.session.pop(f"oauth_state_{connector.slug}", None)
    messages.success(
        request,
        f"{connector.label} connected"
        + (f" for campus {campus.name}" if campus is not None else "")
        + ".",
    )
    redirect_back = payload.get("redirect_back") or reverse(
        "integrations_marketplace:hub"
    )
    return redirect(redirect_back)


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def disconnect(
    request: HttpRequest, connector_slug: str, campus_id: int | None = None
) -> HttpResponse:
    school = getattr(request, "school", None)
    if school is None or not _user_can_manage(request):
        return render(
            request,
            "integrations_marketplace/forbidden.html",
            status=403,
        )
    connector = get_connector(connector_slug)
    if connector is None:
        messages.error(request, f"Unknown connector: {connector_slug}")
        return redirect("integrations_marketplace:hub")

    from apps.siteconfig.models_platform_catalog import ServiceIntegration

    campus = _resolve_campus(school, campus_id) if campus_id else None
    qs = ServiceIntegration.objects.filter(
        school=school, connector_slug__iexact=connector.slug
    )
    if campus is None:
        qs = qs.filter(campus__isnull=True)
    else:
        qs = qs.filter(campus=campus)
    updated = qs.update(is_active=False)
    if updated:
        messages.success(request, f"{connector.label} disconnected.")
    else:
        messages.info(request, f"{connector.label} was not connected at this scope.")
    return redirect("integrations_marketplace:hub")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _exchange_code_for_tokens(*, token_url: str, body: dict) -> dict:
    """
    POST application/x-www-form-urlencoded body to the upstream token endpoint
    and return the parsed JSON. Returns `{}` on any transport failure (caller
    surfaces a user-facing error).
    """
    if not token_url:
        return {}
    from urllib.parse import urlencode

    encoded = urlencode({k: v for k, v in body.items() if v is not None}).encode("utf-8")
    req = urllib.request.Request(
        token_url,
        data=encoded,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — token URL from registry
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("OAuth token endpoint unreachable: %s", exc)
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _refusal_message(diag: dict) -> str:
    reason = (diag or {}).get("reason", "unknown")
    if reason == "unknown_connector":
        return f"Connector '{diag.get('connector_slug')}' is not registered."
    if reason == "wrong_auth_kind":
        return (
            f"'{diag.get('connector_slug')}' is not an OAuth2 connector "
            f"(auth kind: {diag.get('auth_kind')}). Configure it from the catalog instead."
        )
    if reason == "missing_client_credentials":
        return (
            "The platform owner has not registered this app yet. "
            f"Set {diag.get('env_var_hint')} in the deployment environment."
        )
    return "Could not start OAuth dance — please try again."


@login_required
def redirect_uri_registry(request: HttpRequest) -> HttpResponse:
    """
    Platform-owner-facing surface: shows the absolute redirect URI to paste
    into each upstream's OAuth marketplace console (Zoom, Google, Microsoft,
    Slack, etc.) and surfaces which connector client credentials are
    configured in env. Read-only — no mutations.
    """
    user = getattr(request, "user", None)
    if not user or not (user.is_authenticated and (user.is_superuser or user.is_staff)):
        return render(
            request,
            "integrations_marketplace/forbidden.html",
            status=403,
        )

    from apps.integrations_marketplace.connector_registry import (
        list_oauth_connectors,
        resolve_oauth_client_credentials,
    )

    base = (
        getattr(__import__("django.conf", fromlist=["settings"]).settings,
                "OAUTH_CALLBACK_BASE_URL", "")
        or _request_origin_for(request)
    )

    rows = []
    for connector in list_oauth_connectors():
        cid, secret = resolve_oauth_client_credentials(connector.slug)
        cdict = connector.to_dict()
        cdict["brand_mark_class"] = f"rmc-integration-mark rmc-integration-mark--{connector.slug}"
        rows.append({
            "connector": cdict,
            "redirect_uri": f"{base.rstrip('/')}{reverse(
                'integrations_marketplace:oauth_callback',
                kwargs={'connector_slug': connector.slug},
            )}",
            "has_client_id": bool(cid),
            "has_client_secret": bool(secret),
            "env_id_var": f"INTEGRATIONS_{connector.slug.upper()}_CLIENT_ID",
            "env_secret_var": f"INTEGRATIONS_{connector.slug.upper()}_CLIENT_SECRET",
        })

    return render(
        request,
        "integrations_marketplace/redirect_uri_registry.html",
        {"rows": rows, "base_url": base},
    )


def _request_origin_for(request) -> str:
    if request is None:
        return ""
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host() if hasattr(request, "get_host") else ""
    return f"{scheme}://{host}" if host else ""


__all__ = [
    "disconnect",
    "integrations_hub",
    "oauth_callback",
    "oauth_connect",
    "redirect_uri_registry",
]
