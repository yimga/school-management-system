"""
Stripe Checkout and Customer Portal session creation (real API calls when configured).

Uses application/x-www-form-urlencoded posts to Stripe's API. Callers must only invoke
when ``PlatformBillingProcessorConfig`` (code=stripe) is active and ``secret_key`` is set
in processor ``metadata`` — never fabricate success URLs.
"""

from __future__ import annotations

from typing import Any
from django.http import HttpRequest

from apps.billing.models import PlatformBillingProcessorConfig
from apps.billing.processors import _default_form_post


def get_active_stripe_processor_config() -> PlatformBillingProcessorConfig | None:
    return PlatformBillingProcessorConfig.objects.filter(
        code="stripe", is_active=True
    ).first()


def stripe_secret_key(config: PlatformBillingProcessorConfig) -> str:
    meta = config.metadata if isinstance(config.metadata, dict) else {}
    return str(meta.get("secret_key") or meta.get("api_key") or "").strip()


def stripe_api_base(config: PlatformBillingProcessorConfig) -> str:
    meta = config.metadata if isinstance(config.metadata, dict) else {}
    return str(meta.get("api_base_url") or "https://api.stripe.com").rstrip("/")


def create_checkout_session(
    *,
    config: PlatformBillingProcessorConfig,
    stripe_price_id: str,
    success_url: str,
    cancel_url: str,
    customer_id: str = "",
    customer_email: str = "",
    metadata: dict[str, str] | None = None,
    http_post_form=None,
) -> tuple[bool, str, str, dict[str, Any]]:
    """
    Create a Stripe Checkout Session (mode=subscription).

    Returns (ok, error_message, checkout_url, raw_body_dict).
    """
    key = stripe_secret_key(config)
    if not key:
        return False, "Stripe secret key is not configured on the processor.", "", {}
    price = (stripe_price_id or "").strip()
    if not price:
        return False, "Stripe price id is missing.", "", {}

    post = http_post_form or _default_form_post
    url = f"{stripe_api_base(config)}/v1/checkout/sessions"
    payload: dict[str, str] = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][price]": price,
        "line_items[0][quantity]": "1",
    }
    cid = (customer_id or "").strip()
    if cid:
        payload["customer"] = cid
    else:
        em = (customer_email or "").strip()
        if em:
            payload["customer_email"] = em
        else:
            return False, "Customer email or Stripe customer id is required.", "", {}
    if metadata:
        for k, v in metadata.items():
            ks = str(k).strip()
            if not ks:
                continue
            payload[f"metadata[{ks}]"] = str(v)[:500]
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    status_code, body, raw_text = post(url, payload, headers, 30)
    if not 200 <= int(status_code or 0) < 300:
        err = ""
        if isinstance(body.get("error"), dict):
            err = str(body["error"].get("message") or "")
        return False, err or raw_text or "Stripe checkout session failed.", "", body
    checkout_url = str(body.get("url") or "").strip()
    if not checkout_url:
        return False, "Stripe did not return a checkout URL.", "", body
    return True, "", checkout_url, body


def create_billing_portal_session(
    *,
    config: PlatformBillingProcessorConfig,
    customer_id: str,
    return_url: str,
    http_post_form=None,
) -> tuple[bool, str, str, dict[str, Any]]:
    key = stripe_secret_key(config)
    if not key:
        return False, "Stripe secret key is not configured on the processor.", "", {}
    cid = (customer_id or "").strip()
    if not cid:
        return False, "Stripe customer id is missing.", "", {}
    post = http_post_form or _default_form_post
    url = f"{stripe_api_base(config)}/v1/billing_portal/sessions"
    payload = {"customer": cid, "return_url": return_url}
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    status_code, body, raw_text = post(url, payload, headers, 30)
    if not 200 <= int(status_code or 0) < 300:
        err = ""
        if isinstance(body.get("error"), dict):
            err = str(body["error"].get("message") or "")
        return False, err or raw_text or "Stripe billing portal session failed.", "", body
    portal_url = str(body.get("url") or "").strip()
    if not portal_url:
        return False, "Stripe did not return a portal URL.", "", body
    return True, "", portal_url, body


def absolute_urls_for_billing(
    request: HttpRequest,
    *,
    success_name: str = "siteconfig:billing_plan_readonly",
    cancel_name: str = "siteconfig:billing_plan_readonly",
) -> tuple[str, str]:
    from django.urls import reverse

    try:
        ok_path = reverse(success_name, urlconf="config.tenant_urls")
    except Exception:  # noqa: BLE001
        ok_path = reverse(success_name)
    try:
        cancel_path = reverse(cancel_name, urlconf="config.tenant_urls")
    except Exception:  # noqa: BLE001
        cancel_path = reverse(cancel_name)
    base = request.build_absolute_uri("/").rstrip("/")
    success = f"{base}{ok_path}?billing=checkout_complete"
    cancel = f"{base}{cancel_path}?billing=checkout_canceled"
    return success, cancel
