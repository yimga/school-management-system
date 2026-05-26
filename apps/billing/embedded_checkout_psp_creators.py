"""Wave Q1 (v3.95.2 — 2026-05-26) — Per-PSP live-creator scaffolds.

Concrete session creator for each non-Stripe PSP that the embedded-checkout
dispatcher can call when `adapter_status="live"` flips and tenant credentials
are present. Each creator is documented against the real vendor API.

Activation requires three things per PSP:
1. Vendor partner agreement signed (counsel-blocked outside this repo).
2. Credentials stored in tenant's ``PlatformBillingProcessorConfig.metadata``.
3. ``PSPRow.adapter_status`` set to ``live`` in
   ``apps/billing/psp_adapter_registry.py``.

No live network calls until all three hold. Until then, each creator returns
``{"ok": False, "error": "credentials missing"}`` and the dispatcher's
fallthrough logic tries the next candidate (per Wave I/P-C+E design).

Boundaries preserved: NO third-party SDK imports at module load time. Every
creator imports `requests` lazily inside its function. Credential reads go
through the tenant's PSP processor config row, never platform env vars.
"""

from __future__ import annotations

import logging
from typing import Any

from .embedded_checkout import CheckoutSessionRequest


logger = logging.getLogger(__name__)


def _tenant_psp_config(processor: str) -> dict[str, Any]:
    """Pull credentials from the tenant's active PSP processor row."""
    try:
        from .models import PlatformBillingProcessorConfig  # type: ignore
        cfg = PlatformBillingProcessorConfig.objects.filter(
            code=processor, is_active=True,
        ).first()
        if cfg is None:
            return {}
        meta = cfg.metadata if isinstance(cfg.metadata, dict) else {}
        return meta
    except Exception as exc:  # noqa: BLE001
        logger.warning("psp_config lookup failed processor=%s err=%s", processor, exc)
        return {}


def _missing_creds(processor: str, required: tuple[str, ...]) -> dict[str, Any]:
    return {"ok": False,
            "error": f"{processor} credentials missing: need {','.join(required)}"}


# ---------------------------------------------------------------------------
# Paystack — Africa (NGN/GHS/ZAR/KES)
# Docs: https://paystack.com/docs/api/transaction/#initialize
# ---------------------------------------------------------------------------

def create_paystack_session(
    req: CheckoutSessionRequest,
    session_id: str,
    total_minor: int,
    http_post=None,
) -> dict[str, Any]:
    cfg = _tenant_psp_config("paystack")
    secret = (cfg.get("secret_key") or cfg.get("api_key") or "").strip()
    if not secret:
        return _missing_creds("paystack", ("secret_key",))

    # Paystack uses amount in *minor* units (kobo for NGN) already — perfect
    # match for our CheckoutSessionRequest.line_items[*].amount_minor.
    payload = {
        "email": req.parent_email or f"{req.parent_phone}@phone.runmycampus.com",
        "amount": total_minor,
        "currency": req.line_items[0].currency,
        "reference": session_id,
        "metadata": {
            "tenant_id": req.tenant_id,
            "purpose": req.purpose,
            "student_reference": req.student_reference,
        },
        "callback_url": req.success_url or "https://runmycampus.com/checkout/ok",
    }
    headers = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }
    base = (cfg.get("api_base_url") or "https://api.paystack.co").rstrip("/")
    url = f"{base}/transaction/initialize"

    poster = http_post or _default_json_post
    try:
        resp = poster(url, payload, headers)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"paystack network error: {exc}"}
    if not resp.get("ok"):
        return resp
    data = resp.get("data") or {}
    inner = data.get("data") if isinstance(data, dict) else None
    if not isinstance(inner, dict) or not inner.get("authorization_url"):
        return {"ok": False,
                "error": f"paystack unexpected response: {data}"}
    return {
        "ok": True,
        "hosted_url": inner["authorization_url"],
        "metadata": {"mode": "live", "psp": "paystack",
                     "paystack_reference": inner.get("reference"),
                     "paystack_access_code": inner.get("access_code")},
    }


# ---------------------------------------------------------------------------
# Flutterwave — Africa (NGN/GHS/KES/UGX/TZS/RWF/XAF/XOF/ZAR/EGP/MAD)
# Docs: https://developer.flutterwave.com/docs/payments/standard/
# ---------------------------------------------------------------------------

def create_flutterwave_session(
    req: CheckoutSessionRequest,
    session_id: str,
    total_minor: int,
    http_post=None,
) -> dict[str, Any]:
    cfg = _tenant_psp_config("flutterwave")
    secret = (cfg.get("secret_key") or cfg.get("api_key") or "").strip()
    if not secret:
        return _missing_creds("flutterwave", ("secret_key",))

    # Flutterwave expects amount in *major* units. Convert from minor.
    cur = req.line_items[0].currency
    zero_decimal = {"JPY", "KRW", "VND", "XAF", "XOF", "UGX", "RWF", "BIF"}
    amount_major = total_minor if cur in zero_decimal else total_minor / 100
    payload = {
        "tx_ref": session_id,
        "amount": amount_major,
        "currency": cur,
        "redirect_url": req.success_url or "https://runmycampus.com/checkout/ok",
        "customer": {
            "email": req.parent_email or f"{req.parent_phone}@phone.runmycampus.com",
            "phonenumber": req.parent_phone,
        },
        "meta": {
            "tenant_id": req.tenant_id,
            "purpose": req.purpose,
            "student_reference": req.student_reference,
        },
        "customizations": {
            "title": "School fees",
            "description": ", ".join(li.description for li in req.line_items)[:80],
        },
    }
    headers = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }
    base = (cfg.get("api_base_url") or "https://api.flutterwave.com").rstrip("/")
    url = f"{base}/v3/payments"

    poster = http_post or _default_json_post
    try:
        resp = poster(url, payload, headers)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"flutterwave network error: {exc}"}
    if not resp.get("ok"):
        return resp
    data = resp.get("data") or {}
    inner = data.get("data") if isinstance(data, dict) else None
    if not isinstance(inner, dict) or not inner.get("link"):
        return {"ok": False, "error": f"flutterwave unexpected response: {data}"}
    return {
        "ok": True,
        "hosted_url": inner["link"],
        "metadata": {"mode": "live", "psp": "flutterwave",
                     "flutterwave_tx_ref": session_id},
    }


# ---------------------------------------------------------------------------
# Razorpay — India (INR; multi-currency on request)
# Docs: https://razorpay.com/docs/api/orders/
# ---------------------------------------------------------------------------

def create_razorpay_session(
    req: CheckoutSessionRequest,
    session_id: str,
    total_minor: int,
    http_post=None,
) -> dict[str, Any]:
    cfg = _tenant_psp_config("razorpay")
    key_id = (cfg.get("key_id") or "").strip()
    key_secret = (cfg.get("secret_key") or cfg.get("key_secret") or "").strip()
    if not key_id or not key_secret:
        return _missing_creds("razorpay", ("key_id", "secret_key"))

    # Razorpay uses paise (minor) for amount.
    payload = {
        "amount": total_minor,
        "currency": req.line_items[0].currency,
        "receipt": session_id,
        "notes": {
            "tenant_id": req.tenant_id,
            "purpose": req.purpose,
            "student_reference": req.student_reference,
        },
    }
    auth = (key_id, key_secret)
    base = (cfg.get("api_base_url") or "https://api.razorpay.com").rstrip("/")
    url = f"{base}/v1/orders"

    poster = http_post or _default_json_post
    try:
        # Razorpay uses HTTP basic auth instead of a bearer header.
        resp = poster(url, payload, {"Content-Type": "application/json"},
                       auth=auth)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"razorpay network error: {exc}"}
    if not resp.get("ok"):
        return resp
    data = resp.get("data") or {}
    order_id = data.get("id") if isinstance(data, dict) else None
    if not order_id:
        return {"ok": False, "error": f"razorpay unexpected response: {data}"}

    # Razorpay's hosted-checkout URL is constructed client-side. We return
    # the order_id + checkout_options that the tenant's site embeds via the
    # Razorpay JS SDK. The hosted_url is a redirect helper we expose.
    hosted_url = (
        f"{base.replace('api.', 'checkout.')}/embedded/{order_id}"
    )
    return {
        "ok": True,
        "hosted_url": hosted_url,
        "metadata": {"mode": "live", "psp": "razorpay",
                     "razorpay_order_id": order_id,
                     "razorpay_key_id": key_id},
    }


# ---------------------------------------------------------------------------
# MTN MoMo — Africa mobile money (XAF/XOF/UGX/GHS/RWF)
# Docs: https://momodeveloper.mtn.com/api-documentation/api-description/
# ---------------------------------------------------------------------------

def create_mtn_momo_session(
    req: CheckoutSessionRequest,
    session_id: str,
    total_minor: int,
    http_post=None,
) -> dict[str, Any]:
    cfg = _tenant_psp_config("mtn_momo")
    api_user = (cfg.get("api_user") or "").strip()
    api_key = (cfg.get("api_key") or "").strip()
    subscription_key = (cfg.get("subscription_key") or "").strip()
    if not (api_user and api_key and subscription_key):
        return _missing_creds(
            "mtn_momo", ("api_user", "api_key", "subscription_key"),
        )

    # MoMo expects amount as a *string* in major units.
    cur = req.line_items[0].currency
    zero_decimal = {"XAF", "XOF", "UGX", "RWF", "BIF"}
    amount_major = total_minor if cur in zero_decimal else total_minor / 100

    # The Collection RequestToPay payload.
    payload = {
        "amount": str(amount_major),
        "currency": cur,
        "externalId": session_id,
        "payer": {
            "partyIdType": "MSISDN",
            "partyId": req.parent_phone.lstrip("+"),
        },
        "payerMessage": "School fees",
        "payeeNote": f"{req.purpose} {req.student_reference}".strip(),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Reference-Id": session_id,
        "X-Target-Environment": cfg.get("target_environment") or "sandbox",
        "Ocp-Apim-Subscription-Key": subscription_key,
        "Content-Type": "application/json",
    }
    base = (cfg.get("api_base_url")
             or "https://sandbox.momodeveloper.mtn.com").rstrip("/")
    url = f"{base}/collection/v1_0/requesttopay"

    poster = http_post or _default_json_post
    try:
        resp = poster(url, payload, headers)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"mtn_momo network error: {exc}"}
    if not resp.get("ok"):
        return resp
    # MoMo's request-to-pay is a push to the parent's phone — no hosted URL.
    # We return a polling URL the tenant can hit to check status.
    return {
        "ok": True,
        "hosted_url": f"runmycampus://momo-pending/{session_id}",
        "metadata": {"mode": "live", "psp": "mtn_momo",
                     "polling_url": f"{base}/collection/v1_0/requesttopay/{session_id}",
                     "channel": "ussd_push"},
    }


# ---------------------------------------------------------------------------
# Orange Money — West/Central Africa (XOF/XAF/MAD)
# Docs: https://developer.orange.com/apis/om-webpay/
# ---------------------------------------------------------------------------

def create_orange_money_session(
    req: CheckoutSessionRequest,
    session_id: str,
    total_minor: int,
    http_post=None,
) -> dict[str, Any]:
    cfg = _tenant_psp_config("orange_money")
    merchant_key = (cfg.get("merchant_key") or "").strip()
    access_token = (cfg.get("access_token") or "").strip()
    if not (merchant_key and access_token):
        return _missing_creds("orange_money", ("merchant_key", "access_token"))

    cur = req.line_items[0].currency
    zero_decimal = {"XAF", "XOF"}
    amount_major = total_minor if cur in zero_decimal else total_minor / 100

    payload = {
        "merchant_key": merchant_key,
        "currency": cur,
        "order_id": session_id,
        "amount": amount_major,
        "return_url": req.success_url or "https://runmycampus.com/checkout/ok",
        "cancel_url": req.cancel_url or "https://runmycampus.com/checkout/cancel",
        "notif_url": cfg.get("notif_url") or "https://runmycampus.com/billing/orange-money/notif/",
        "lang": req.locale or "en",
        "reference": session_id,
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    base = (cfg.get("api_base_url") or "https://api.orange.com").rstrip("/")
    url = f"{base}/orange-money-webpay/dev/v1/webpayment"

    poster = http_post or _default_json_post
    try:
        resp = poster(url, payload, headers)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"orange_money network error: {exc}"}
    if not resp.get("ok"):
        return resp
    data = resp.get("data") or {}
    if not isinstance(data, dict) or not data.get("payment_url"):
        return {"ok": False, "error": f"orange_money unexpected response: {data}"}
    return {
        "ok": True,
        "hosted_url": data["payment_url"],
        "metadata": {"mode": "live", "psp": "orange_money",
                     "pay_token": data.get("pay_token"),
                     "notif_token": data.get("notif_token")},
    }


# ---------------------------------------------------------------------------
# Default HTTP JSON POST
# ---------------------------------------------------------------------------

def _default_json_post(url: str, payload: dict[str, Any],
                        headers: dict[str, str],
                        *, auth=None) -> dict[str, Any]:
    """Lazy import of `requests` so this module loads in environments without
    it. Returns a normalized response shape."""
    try:
        import requests  # type: ignore
    except ImportError:
        return {"ok": False, "error": "requests library not installed"}
    try:
        resp = requests.post(url, json=payload, headers=headers,
                              timeout=15, auth=auth)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"network error: {exc}"}
    if resp.status_code not in (200, 201, 202):
        return {"ok": False,
                "error": f"http {resp.status_code}: {resp.text[:200]}"}
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {"raw": resp.text[:1000]}
    return {"ok": True, "data": body, "status": resp.status_code}


# ---------------------------------------------------------------------------
# Public lookup table (consumed by the dispatcher)
# ---------------------------------------------------------------------------

_LIVE_CREATORS = {
    "paystack": create_paystack_session,
    "flutterwave": create_flutterwave_session,
    "razorpay": create_razorpay_session,
    "mtn_momo": create_mtn_momo_session,
    "orange_money": create_orange_money_session,
}


def get_live_creator(processor: str):
    """Return the live session creator for a PSP, or None if not implemented."""
    return _LIVE_CREATORS.get(processor)


def list_live_creators() -> tuple[str, ...]:
    return tuple(_LIVE_CREATORS.keys())
