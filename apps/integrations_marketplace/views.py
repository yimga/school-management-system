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
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.integrations_marketplace.connector_registry import (
    CATEGORY_LABELS,
    get_connector,
)
from apps.integrations_marketplace.oauth import (
    build_authorize_redirect,
    build_token_exchange_payload,
    persist_oauth_tokens,
    validate_callback_state,
)

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
    # Snapshot the rows BEFORE the bulk update so we can fire the lifecycle
    # signal per disconnected row (qs.update doesn't load instances).
    disconnected_rows = list(qs.filter(is_active=True))
    updated = qs.update(is_active=False)
    if disconnected_rows:
        try:
            from apps.integrations_marketplace.signals import connector_disconnected
            for r in disconnected_rows:
                connector_disconnected.send_robust(
                    sender="integrations_marketplace.connector",
                    row=r, connector=connector.slug, school=school,
                    campus=getattr(r, "campus", None), action="disconnected",
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "connector_disconnected dispatch crashed for %s", connector.slug
            )
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
    if reason == "connector_deprecated":
        note = (diag or {}).get("deprecation_note") or ""
        return (
            f"'{diag.get('connector_slug')}' has been deprecated and is no "
            f"longer accepting new connections."
            + (f" {note}" if note else "")
        )
    return "Could not start OAuth dance — please try again."


@login_required
@require_http_methods(["POST"])
def test_webhook(
    request: HttpRequest, connector_slug: str, integration_id: int
) -> HttpResponse:
    """v2.94 — operator-triggered synthetic webhook delivery.

    Operator clicks "Test" on a connected row; we synthesize a payload,
    sign it with the row's secret using the connector's expected algorithm,
    then in-process exercise BOTH the HMAC verifier AND the registered
    handler. Result is a JSON diagnostic the UI renders inline so the
    operator can confirm the webhook end-to-end without poking the
    upstream provider.
    """
    school = getattr(request, "school", None)
    if school is None or not _user_can_manage(request):
        return render(
            request, "integrations_marketplace/forbidden.html", status=403
        )
    from apps.integrations_marketplace import webhooks as _webhooks
    from apps.siteconfig.models_platform_catalog import ServiceIntegration
    import hashlib
    import hmac
    import json as _json
    import time as _time

    row = ServiceIntegration.objects.filter(
        pk=integration_id, school=school, connector_slug__iexact=connector_slug
    ).first()
    if row is None:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)
    secret = str((row.config or {}).get("webhook_secret") or "").strip()
    if not secret:
        return JsonResponse(
            {"ok": False, "error": "no_webhook_secret_configured"}, status=400
        )

    payload = {"type": "rmc.test", "ts": int(_time.time()), "row_id": row.pk}
    body = _json.dumps(payload).encode("utf-8")
    ts = str(int(_time.time()))

    # Build a request whose META carries the right signature scheme for
    # the connector. Slack uses its own; everything else uses the default.
    fake = HttpRequest()
    fake.method = "POST"
    fake.META["CONTENT_TYPE"] = "application/json"
    fake._body = body
    if connector_slug.lower() == "slack":
        base = f"v0:{ts}:".encode("utf-8") + body
        sig = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
        fake.META["HTTP_X_SLACK_SIGNATURE"] = sig
        fake.META["HTTP_X_SLACK_REQUEST_TIMESTAMP"] = ts
    else:
        msg = f"{ts}:".encode("utf-8") + body
        sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        fake.META["HTTP_X_RMC_SIGNATURE"] = f"v0={sig}"
        fake.META["HTTP_X_RMC_TIMESTAMP"] = ts

    verify_ok, verify_reason = _webhooks._verify(request=fake, row=row)
    handler_status = None
    handler_present = connector_slug.lower() in _webhooks.WEBHOOK_HANDLERS
    if verify_ok and handler_present:
        handler = _webhooks.WEBHOOK_HANDLERS[connector_slug.lower()]
        try:
            resp = handler(row, payload)
            handler_status = int(getattr(resp, "status_code", 0))
        except Exception as exc:  # noqa: BLE001 — surface to operator
            return JsonResponse({
                "ok": False, "verify_ok": True, "verify_reason": verify_reason,
                "handler_present": True, "handler_error": str(exc),
            }, status=500)
    return JsonResponse({
        "ok": bool(verify_ok),
        "verify_ok": verify_ok,
        "verify_reason": verify_reason,
        "handler_present": handler_present,
        "handler_status": handler_status,
        "synthetic_payload": payload,
    })


@login_required
def scope_override(
    request: HttpRequest, connector_slug: str
) -> HttpResponse:
    """v2.94 — per-tenant OAuth scope override UI.

    GET renders a checkbox list of `connector.default_scopes` with the
    current selection (config["scopes_override"]) pre-checked. POST writes
    the narrowed set back — subset-only is re-validated server-side so a
    crafted form post can't widen.
    """
    school = getattr(request, "school", None)
    if school is None or not _user_can_manage(request):
        return render(
            request, "integrations_marketplace/forbidden.html", status=403
        )
    from apps.integrations_marketplace.connector_registry import (
        AUTH_KIND_OAUTH2, get_connector,
    )
    from apps.siteconfig.models_platform_catalog import ServiceIntegration

    connector = get_connector(connector_slug)
    if connector is None or connector.auth_kind != AUTH_KIND_OAUTH2:
        messages.error(request, "Scope override only applies to OAuth connectors.")
        return redirect("integrations_marketplace:hub")

    campus = _resolve_campus(school, request.GET.get("campus"))
    qs = ServiceIntegration.objects.filter(
        school=school, connector_slug__iexact=connector.slug
    )
    qs = qs.filter(campus=campus) if campus else qs.filter(campus__isnull=True)
    row = qs.first()

    default_scopes = list(connector.default_scopes)

    if request.method == "POST":
        if row is None:
            messages.error(request, f"{connector.label} is not connected at this scope.")
            return redirect("integrations_marketplace:hub")
        # Form submits one checkbox per scope; multi-select.
        chosen = request.POST.getlist("scopes")
        # Enforce subset-only.
        default_set = set(default_scopes)
        rejected = [s for s in chosen if s not in default_set]
        if rejected:
            messages.error(
                request,
                f"Scopes outside the default set were rejected: {', '.join(rejected)}.",
            )
            return redirect(
                f"{reverse('integrations_marketplace:scope_override', kwargs={'connector_slug': connector.slug})}"
                + (f"?campus={campus.pk}" if campus else "")
            )
        cfg = dict(row.config or {})
        if chosen and set(chosen) != default_set:
            # Preserve registry order for readability.
            cfg["scopes_override"] = [s for s in default_scopes if s in chosen]
        else:
            cfg.pop("scopes_override", None)
        row.config = cfg
        row.save(update_fields=["config", "updated_at"])
        messages.success(
            request, f"{connector.label} scopes updated. Reconnect to apply."
        )
        return redirect("integrations_marketplace:hub")

    current_override = []
    if row is not None:
        raw = (row.config or {}).get("scopes_override") or []
        if isinstance(raw, str):
            current_override = [s.strip() for s in raw.replace(",", " ").split() if s.strip()]
        elif isinstance(raw, (list, tuple)):
            current_override = [str(s).strip() for s in raw if str(s).strip()]
    selected_set = set(current_override) if current_override else set(default_scopes)

    return render(request, "integrations_marketplace/scope_override.html", {
        "connector": connector.to_dict(),
        "default_scopes": default_scopes,
        "selected": selected_set,
        "row": row,
        "campus": campus,
        "is_overriding": bool(current_override) and set(current_override) != set(default_scopes),
    })


@login_required
def integrations_events(request: HttpRequest) -> HttpResponse:
    """
    v2.89 follow-up — tenant-scoped webhook delivery log.

    Queries `compliance.AuditLog` for rows the webhook handler audit trail
    writes (`app_label="integrations_marketplace"`, `model_name="ServiceIntegration"`,
    `reason` starts with `"webhook:"`). Scope:
      - the active tenant (request.school via the per-row school_id we
        stored in `new_values`)
      - optional `?connector=<slug>` filter
      - last 200 events, newest first

    This closes the v2.89-honest-gap-#4 "no webhook delivery log / dashboard."
    """
    school = getattr(request, "school", None)
    if school is None:
        return render(
            request, "integrations_marketplace/no_tenant.html", status=400
        )
    if not _user_can_manage(request):
        return render(
            request, "integrations_marketplace/forbidden.html", status=403
        )

    connector_filter = (request.GET.get("connector") or "").strip().lower()

    events: list[dict] = []
    try:
        from apps.compliance.models_audit import AuditLog

        # tenant-isolation-allow: AuditLog has no school FK; per-tenant scope is
        # enforced via the school_id we wrote into new_values at audit time.
        qs = (
            AuditLog.objects
            .filter(
                app_label="integrations_marketplace",
                model_name="ServiceIntegration",
                reason__startswith="webhook:",
            )
            .order_by("-timestamp")
        )
        for row in qs.iterator():
            vals = row.new_values or {}
            if vals.get("school_id") != getattr(school, "pk", None):
                continue
            if connector_filter and vals.get("connector") != connector_filter:
                continue
            events.append({
                "timestamp": row.timestamp,
                "connector": vals.get("connector") or "",
                "event_type": vals.get("event_type") or "",
                "campus_id": vals.get("campus_id"),
                "payload_keys": vals.get("payload_keys") or [],
                "row_id": row.object_id,
                "audit_log_id": row.pk,
            })
            if len(events) >= 200:
                break
    except ImportError:
        logger.warning("integrations_events: compliance.models_audit not available")

    from apps.integrations_marketplace.connector_registry import list_connectors
    connectors_for_filter = sorted(
        {c.slug for c in list_connectors()}
    )

    ctx = {
        "school": school,
        "events": events,
        "connector_filter": connector_filter,
        "connectors": connectors_for_filter,
    }
    return render(request, "integrations_marketplace/events.html", ctx)


@login_required
@require_http_methods(["POST"])
def rotate_webhook_secret(
    request: HttpRequest, connector_slug: str, integration_id: int
) -> HttpResponse:
    """v3.4 — one-click rotate of `config["webhook_secret"]`.

    The operator copies the new secret into the upstream marketplace console.
    Old secret is preserved in `config["webhook_secret_prev"]` for a short
    rollback window so a slow upstream-update doesn't immediately start
    failing signature_mismatch.
    """
    import secrets as _secrets

    school = getattr(request, "school", None)
    if school is None or not _user_can_manage(request):
        return render(request, "integrations_marketplace/forbidden.html", status=403)
    from apps.siteconfig.models_platform_catalog import ServiceIntegration

    row = ServiceIntegration.objects.filter(
        pk=integration_id, school=school, connector_slug__iexact=connector_slug
    ).first()
    if row is None:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)
    cfg = dict(row.config or {})
    prev = str(cfg.get("webhook_secret") or "").strip()
    new = _secrets.token_urlsafe(32)
    if prev:
        cfg["webhook_secret_prev"] = prev
    cfg["webhook_secret"] = new
    cfg["webhook_secret_rotated_at"] = __import__("time").time()
    row.config = cfg
    row.save(update_fields=["config", "updated_at"])
    return JsonResponse({"ok": True, "new_secret": new})


@login_required
@require_http_methods(["POST"])
def bulk_disconnect(
    request: HttpRequest, connector_slug: str
) -> HttpResponse:
    """v3.4 — tenant kill-switch: disable EVERY row for a connector at the
    current school (across campuses). Requires `confirm=YES` POST field so
    a stray button-click can't wipe an integration.
    """
    school = getattr(request, "school", None)
    if school is None or not _user_can_manage(request):
        return render(request, "integrations_marketplace/forbidden.html", status=403)
    connector = get_connector(connector_slug)
    if connector is None:
        messages.error(request, f"Unknown connector: {connector_slug}")
        return redirect("integrations_marketplace:hub")
    if (request.POST.get("confirm") or "").strip().upper() != "YES":
        messages.warning(request, "Bulk disconnect requires explicit confirmation.")
        return redirect("integrations_marketplace:hub")

    from apps.siteconfig.models_platform_catalog import ServiceIntegration

    qs = ServiceIntegration.objects.filter(
        school=school, connector_slug__iexact=connector.slug, is_active=True
    )
    rows = list(qs)
    updated = qs.update(is_active=False)
    # Fire signal per disconnected row.
    try:
        from apps.integrations_marketplace.signals import connector_disconnected
        for r in rows:
            connector_disconnected.send_robust(
                sender="integrations_marketplace.connector",
                row=r, connector=connector.slug, school=school,
                campus=getattr(r, "campus", None), action="bulk_disconnected",
            )
    except Exception:  # noqa: BLE001
        logger.exception("Bulk disconnect signal dispatch crashed")
    messages.success(
        request,
        f"Bulk-disconnected {updated} {connector.label} row(s) for this school.",
    )
    return redirect("integrations_marketplace:hub")


@login_required
def integrations_data_inventory_csv(request: HttpRequest) -> HttpResponse:
    """v3.4 — FERPA/GDPR data inventory: one row per configured integration
    for the current tenant. Used for "what third parties does this school
    share data with" audit responses.
    """
    school = getattr(request, "school", None)
    if school is None:
        return render(request, "integrations_marketplace/no_tenant.html", status=400)
    if not _user_can_manage(request):
        return render(request, "integrations_marketplace/forbidden.html", status=403)

    import csv
    import io as _io
    from apps.integrations_marketplace.connector_registry import (
        CATEGORY_LABELS, get_connector,
    )
    from apps.siteconfig.models_platform_catalog import ServiceIntegration

    qs = (
        ServiceIntegration.objects
        .filter(school=school)
        .exclude(connector_slug="")
        .select_related("campus")
        .order_by("connector_slug", "campus__name")
    )

    buf = _io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "connector", "category", "label", "campus", "is_active",
        "default_scopes", "scopes_override", "has_refresh_token",
        "has_webhook_secret", "expires_at_iso", "documentation_url",
    ])
    for row in qs.iterator():
        connector = get_connector(row.connector_slug)
        cfg = row.config or {}
        scopes_override = cfg.get("scopes_override") or []
        if isinstance(scopes_override, str):
            scopes_override = [s for s in scopes_override.replace(",", " ").split() if s]
        exp = cfg.get("expires_at")
        try:
            exp_iso = __import__("datetime").datetime.utcfromtimestamp(
                float(exp)
            ).isoformat() + "Z" if exp else ""
        except (TypeError, ValueError):
            exp_iso = ""
        writer.writerow([
            row.connector_slug,
            CATEGORY_LABELS.get(connector.category if connector else "", "")
                if connector else "",
            connector.label if connector else "",
            getattr(row.campus, "name", "") if row.campus else "",
            "yes" if row.is_active else "no",
            ";".join(connector.default_scopes) if connector else "",
            ";".join(str(s) for s in scopes_override),
            "yes" if cfg.get("refresh_token") else "no",
            "yes" if cfg.get("webhook_secret") else "no",
            exp_iso,
            connector.documentation_url if connector else "",
        ])

    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    school_slug = "".join(
        ch for ch in (getattr(school, "name", "school") or "school").lower()
        if ch.isalnum() or ch in {"-", "_"}
    ) or "school"
    resp["Content-Disposition"] = (
        f'attachment; filename="integrations-data-inventory-{school_slug}.csv"'
    )
    return resp


@login_required
def integrations_rejections(request: HttpRequest) -> HttpResponse:
    """v2.100 — tenant-scoped webhook REJECTION log.

    Mirror of `integrations_events` but for the deliveries that didn't make
    it past HMAC verify / rate limit. Operator surface for triaging
    "why are upstream deliveries failing" without grep'ing worker logs.
    Queries `compliance.AuditLog` filtered to `reason__startswith="webhook_rejected:"`.
    """
    school = getattr(request, "school", None)
    if school is None:
        return render(request, "integrations_marketplace/no_tenant.html", status=400)
    if not _user_can_manage(request):
        return render(request, "integrations_marketplace/forbidden.html", status=403)

    connector_filter = (request.GET.get("connector") or "").strip().lower()
    reason_filter = (request.GET.get("reason") or "").strip().lower()

    events: list[dict] = []
    counts_by_reason: dict[str, int] = {}
    try:
        from apps.compliance.models_audit import AuditLog

        # tenant-isolation-allow: AuditLog has no school FK; scope enforced via
        # the school_id we wrote into new_values at rejection time.
        qs = (
            AuditLog.objects
            .filter(
                app_label="integrations_marketplace",
                model_name="ServiceIntegration",
                reason__startswith="webhook_rejected:",
            )
            .order_by("-timestamp")
        )
        for row in qs.iterator():
            vals = row.new_values or {}
            if vals.get("school_id") != getattr(school, "pk", None):
                continue
            if connector_filter and vals.get("connector") != connector_filter:
                continue
            if reason_filter and vals.get("reason") != reason_filter:
                continue
            counts_by_reason[vals.get("reason") or "unknown"] = (
                counts_by_reason.get(vals.get("reason") or "unknown", 0) + 1
            )
            events.append({
                "timestamp": row.timestamp,
                "connector": vals.get("connector") or "",
                "reason": vals.get("reason") or "",
                "client_ip": vals.get("client_ip") or "",
                "row_id": row.object_id,
            })
            if len(events) >= 200:
                break
    except ImportError:
        logger.warning("integrations_rejections: compliance.models_audit not available")

    from apps.integrations_marketplace.connector_registry import list_connectors
    return render(request, "integrations_marketplace/rejections.html", {
        "school": school,
        "events": events,
        "connector_filter": connector_filter,
        "reason_filter": reason_filter,
        "counts_by_reason": sorted(counts_by_reason.items()),
        "connectors": sorted({c.slug for c in list_connectors()}),
    })


@login_required
def integrations_rollup(request: HttpRequest) -> HttpResponse:
    """
    v2.79 follow-up — one table, every campus × every connector.

    The per-campus hub at `?campus=<id>` is the right place to *change* a
    connection, but a school with 4 campuses had to flip the dropdown 4
    times to see status. This view gives them the bird's-eye: rows are
    connectors, columns are campuses (plus a "school" column for the
    school-level baseline), cells are status badges with a click-through
    to the campus-scoped hub.
    """
    school = getattr(request, "school", None)
    if school is None:
        return render(
            request, "integrations_marketplace/no_tenant.html", status=400
        )
    if not _user_can_manage(request):
        return render(
            request, "integrations_marketplace/forbidden.html", status=403
        )

    from apps.integrations_marketplace.connector_registry import list_connectors
    from apps.integrations_marketplace.resolver import resolve_connector_config
    from apps.schoolops.models import Campus

    campuses = list(
        Campus.objects.filter(school=school, is_active=True).order_by("name")
    )
    # The "school-level" baseline is rendered as its own column on the left
    # so a school without any campus rows still sees a useful table.
    scopes: list[dict] = [{"key": "school", "label": "School", "campus": None}]
    for c in campuses:
        scopes.append({"key": f"campus:{c.pk}", "label": c.name, "campus": c})

    rows: list[dict] = []
    totals = {"connected": 0, "missing": 0, "inactive": 0}
    for connector in list_connectors():
        cdict = connector.to_dict()
        cdict["brand_mark_class"] = (
            f"rmc-integration-mark rmc-integration-mark--{connector.slug}"
        )
        cells: list[dict] = []
        for scope in scopes:
            resolved = resolve_connector_config(
                connector.slug, school=school, campus=scope["campus"]
            )
            is_configured = bool(resolved and resolved.is_configured)
            is_active = bool(resolved and resolved.is_active)
            source = resolved.source if resolved else "none"
            if is_configured and is_active:
                state = "connected"
                totals["connected"] += 1
            elif is_configured and not is_active:
                state = "inactive"
                totals["inactive"] += 1
            else:
                state = "missing"
                totals["missing"] += 1
            cells.append({
                "scope": scope,
                "state": state,
                "source": source,
                "is_configured": is_configured,
                "is_active": is_active,
            })
        rows.append({"connector": cdict, "cells": cells})

    ctx = {
        "school": school,
        "scopes": scopes,
        "rows": rows,
        "totals": totals,
        "has_campuses": bool(campuses),
    }
    return render(request, "integrations_marketplace/rollup.html", ctx)


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

    from apps.integrations_marketplace.startup_checks import (
        oauth_callback_base_url_state,
    )

    return render(
        request,
        "integrations_marketplace/redirect_uri_registry.html",
        {
            "rows": rows,
            "base_url": base,
            "base_url_state": oauth_callback_base_url_state(),
        },
    )


def _request_origin_for(request) -> str:
    if request is None:
        return ""
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host() if hasattr(request, "get_host") else ""
    return f"{scheme}://{host}" if host else ""


__all__ = [
    "bulk_disconnect",
    "disconnect",
    "integrations_data_inventory_csv",
    "integrations_events",
    "integrations_hub",
    "integrations_rejections",
    "integrations_rollup",
    "oauth_callback",
    "oauth_connect",
    "redirect_uri_registry",
    "rotate_webhook_secret",
    "scope_override",
    "test_webhook",
]
