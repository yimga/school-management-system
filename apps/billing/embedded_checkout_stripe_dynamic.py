"""Wave Q2 (v3.95.2 — 2026-05-26) — Stripe ad-hoc checkout via price_data.

The existing :mod:`apps.billing.stripe_checkout` module ships subscription
sessions that consume pre-created Stripe Price IDs. Embedded checkout for
school fees needs **dynamic per-invoice amounts** with no Price object
upfront — Stripe's ``price_data`` parameter on Checkout Sessions supports
this exact case.

Docs: https://docs.stripe.com/api/checkout/sessions/create#create_checkout_session-line_items-price_data
"""

from __future__ import annotations

import logging
from typing import Any

from .embedded_checkout import CheckoutSessionRequest


logger = logging.getLogger(__name__)


def _stripe_amount_for_currency(amount_minor: int, currency: str) -> int:
    """Stripe expects the *smallest currency unit* (cents for USD/EUR/GBP,
    yen for JPY, etc.). ``amount_minor`` is already in that unit. Stripe
    requires int."""
    return int(amount_minor)


def create_stripe_dynamic_session(
    req: CheckoutSessionRequest,
    session_id: str,
    total_minor: int,
    http_post_form=None,
) -> dict[str, Any]:
    """Create a Stripe Checkout Session with dynamic ``price_data`` line items.

    Returns either ``{"ok": True, "hosted_url": ...}`` or
    ``{"ok": False, "error": ...}`` shaped for the dispatcher.

    Falls back to ``{"ok": False, "error": "credentials missing"}`` when the
    tenant has not stored their Stripe secret key in the processor config.
    """
    try:
        from .stripe_checkout import (  # type: ignore
            get_active_stripe_processor_config,
            stripe_api_base,
            stripe_secret_key,
        )
        from .processors import _default_form_post  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("stripe dynamic creator: import error %s", exc)
        return {"ok": False, "error": f"stripe import error: {exc}"}

    cfg = get_active_stripe_processor_config()
    if cfg is None:
        return {"ok": False, "error": "stripe processor config not active"}
    key = stripe_secret_key(cfg)
    if not key:
        return {"ok": False, "error": "stripe credentials missing"}

    success_url = req.success_url or "https://runmycampus.com/checkout/ok"
    cancel_url = req.cancel_url or "https://runmycampus.com/checkout/cancel"

    # Stripe Checkout Session API uses form-encoded params with nested keys.
    # We build line_items via ``line_items[N][price_data][...]``.
    params: dict[str, str] = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": session_id,
        "metadata[tenant_id]": req.tenant_id,
        "metadata[purpose]": req.purpose,
        "metadata[student_reference]": req.student_reference,
        "metadata[session_id]": session_id,
    }
    if req.parent_email:
        params["customer_email"] = req.parent_email

    cur = (req.line_items[0].currency or "usd").lower()
    for idx, li in enumerate(req.line_items):
        line_amount = _stripe_amount_for_currency(li.amount_minor, cur)
        prefix = f"line_items[{idx}]"
        params[f"{prefix}[quantity]"] = str(li.quantity)
        params[f"{prefix}[price_data][currency]"] = cur
        params[f"{prefix}[price_data][unit_amount]"] = str(line_amount)
        # product_data is required by Stripe when not referencing an
        # existing product/price.
        params[f"{prefix}[price_data][product_data][name]"] = (
            li.description or li.sku or "School fee"
        )[:250]
        if li.sku:
            params[f"{prefix}[price_data][product_data][metadata][sku]"] = li.sku

    url = f"{stripe_api_base(cfg)}/v1/checkout/sessions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    poster = http_post_form or _default_form_post

    try:
        resp = poster(url, params, headers)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"stripe network error: {exc}"}

    # _default_form_post returns (status, body_dict).
    if isinstance(resp, tuple) and len(resp) == 2:
        status, body = resp
    else:
        # Some callers return dict-shaped {ok, status, data}.
        if isinstance(resp, dict) and "data" in resp:
            status = resp.get("status", 0)
            body = resp.get("data") or {}
        else:
            return {"ok": False, "error": f"stripe unexpected response shape: {resp!r}"}

    if status not in (200, 201):
        err_msg = "stripe http error"
        if isinstance(body, dict):
            err = body.get("error") or {}
            err_msg = err.get("message") or err.get("code") or err_msg
        return {"ok": False, "error": f"{err_msg} (status {status})"}

    hosted_url = ""
    stripe_session_id = ""
    if isinstance(body, dict):
        hosted_url = body.get("url") or ""
        stripe_session_id = body.get("id") or ""
    if not hosted_url:
        return {"ok": False, "error": "stripe did not return a session URL"}

    return {
        "ok": True,
        "hosted_url": hosted_url,
        "metadata": {
            "mode": "live",
            "psp": "stripe",
            "stripe_session_id": stripe_session_id,
        },
    }
