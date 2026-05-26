"""Wave P-C (v3.95.1 — 2026-05-26) — Embedded checkout HTTP endpoint.

Accepts a JSON POST from the tenant's site (or our parent portal) and
returns the hosted checkout URL.

Wired at ``/billing/embedded-checkout/session/``.

Security:
- Public endpoint (no auth — parents aren't logged in to RMC when they pay
  from a tenant's marketing site). Tenant is identified by the `tenant_id`
  in the request body, validated against the request `host` middleware.
- Rate-limited per tenant via the existing tenant-scope middleware.
- Replay-resistant via session_id (cryptographically random).
"""

from __future__ import annotations

import json
import logging

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .embedded_checkout import (
    CheckoutLineItem,
    CheckoutSessionRequest,
    create_session,
)
from .embedded_checkout_psp_dispatcher import make_dispatcher


logger = logging.getLogger(__name__)


def _parse_payload(raw: bytes) -> tuple[CheckoutSessionRequest | None, str]:
    """Parse the inbound JSON into a CheckoutSessionRequest.

    Returns (request, error_message). Both never set simultaneously."""
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "JSON body must be an object"

    items_raw = data.get("line_items")
    if not isinstance(items_raw, list) or not items_raw:
        return None, "line_items must be a non-empty array"
    line_items: list[CheckoutLineItem] = []
    for li in items_raw:
        if not isinstance(li, dict):
            return None, "every line item must be an object"
        try:
            line_items.append(CheckoutLineItem(
                sku=str(li.get("sku") or ""),
                description=str(li.get("description") or ""),
                amount_minor=int(li.get("amount_minor") or 0),
                currency=str(li.get("currency") or ""),
                quantity=int(li.get("quantity") or 1),
            ))
        except (TypeError, ValueError) as exc:
            return None, f"line item parse error: {exc}"

    try:
        req = CheckoutSessionRequest(
            tenant_id=str(data.get("tenant_id") or ""),
            parent_email=str(data.get("parent_email") or ""),
            parent_phone=str(data.get("parent_phone") or ""),
            line_items=tuple(line_items),
            purpose=str(data.get("purpose") or "tuition_fee"),
            student_reference=str(data.get("student_reference") or ""),
            locale=str(data.get("locale") or "en"),
            success_url=str(data.get("success_url") or ""),
            cancel_url=str(data.get("cancel_url") or ""),
            preferred_processor=str(data.get("preferred_processor") or ""),
        )
    except (TypeError, ValueError) as exc:
        return None, f"request parse error: {exc}"
    return req, ""


@csrf_exempt
@require_POST
def create_embedded_checkout_session(request: HttpRequest) -> JsonResponse:
    """POST endpoint — accepts JSON, returns checkout session info."""
    req, err = _parse_payload(request.body)
    if err or req is None:
        return JsonResponse({"ok": False, "error": err or "unknown"}, status=400)

    # Cross-check tenant identity against the request's resolved School.
    request_school = getattr(request, "school", None)
    if request_school is not None:
        request_tenant_id = str(getattr(request_school, "pk", "") or "")
        if request_tenant_id and request_tenant_id != req.tenant_id:
            logger.warning(
                "embedded_checkout tenant mismatch: request_school=%s body_tenant=%s",
                request_tenant_id, req.tenant_id,
            )
            return JsonResponse({"ok": False, "error": "tenant mismatch"},
                                status=403)

    dispatcher = make_dispatcher()
    result = create_session(req, psp_dispatcher=dispatcher)
    if not result.ok:
        return JsonResponse({
            "ok": False,
            "error": result.error,
            "currency": result.currency,
            "total_minor": result.total_minor,
        }, status=422)
    return JsonResponse({
        "ok": True,
        "session_id": result.session_id,
        "hosted_url": result.hosted_url,
        "processor": result.processor,
        "currency": result.currency,
        "total_minor": result.total_minor,
        "metadata": result.metadata,
    })
