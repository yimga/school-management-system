"""
Stripe Connect Express onboarding — Account + AccountLink (stdlib HTTP).

Uses the same urllib form-post pattern as ``apps.billing.stripe_checkout``.
"""

from __future__ import annotations

from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from apps.billing.models import PlatformBillingProcessorConfig
from apps.billing.stripe_checkout import (
    get_active_stripe_processor_config,
    stripe_api_base,
    stripe_secret_key,
)


def _parse_response_json(raw_text: str) -> dict:
    import json

    try:
        payload = json.loads(raw_text or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _default_form_post(
    url: str, data: dict[str, str], headers: dict[str, str], timeout: int = 30
) -> tuple[int, dict, str]:
    body = urlencode(data, doseq=True).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
            return (
                int(response.getcode() or 200),
                _parse_response_json(raw_text),
                raw_text,
            )
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return int(exc.code or 500), _parse_response_json(detail), detail
    except URLError as exc:
        return 0, {}, str(exc.reason)


def _default_get(
    url: str, headers: dict[str, str], timeout: int = 30
) -> tuple[int, dict, str]:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
            return (
                int(response.getcode() or 200),
                _parse_response_json(raw_text),
                raw_text,
            )
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return int(exc.code or 500), _parse_response_json(detail), detail
    except URLError as exc:
        return 0, {}, str(exc.reason)


def platform_connect_config(
    config: PlatformBillingProcessorConfig | None = None,
) -> dict[str, Any]:
    cfg = config or get_active_stripe_processor_config()
    if not cfg:
        return {"enabled": False, "account_type": "express", "application_fee_percent": ""}
    meta = cfg.metadata if isinstance(cfg.metadata, dict) else {}
    enabled = bool(meta.get("connect_enabled", meta.get("stripe_connect_enabled")))
    return {
        "enabled": enabled,
        "account_type": str(meta.get("connect_account_type") or "express").strip()[:32],
        # Compatibility key intentionally pinned blank. Tenant school-fee
        # collection currently has no platform application fee.
        "application_fee_percent": "",
    }


def connect_is_configured(config: PlatformBillingProcessorConfig | None = None) -> bool:
    cfg = config or get_active_stripe_processor_config()
    if not cfg or not stripe_secret_key(cfg):
        return False
    return bool(platform_connect_config(cfg).get("enabled"))


def create_express_account(
    *,
    config: PlatformBillingProcessorConfig,
    school,
    http_post_form=None,
) -> tuple[bool, str, dict[str, Any]]:
    key = stripe_secret_key(config)
    if not key:
        return False, "Stripe secret key is not configured.", {}
    connect_cfg = platform_connect_config(config)
    if not connect_cfg.get("enabled"):
        return False, "Stripe Connect is not enabled on the platform processor.", {}

    post = http_post_form or _default_form_post
    url = f"{stripe_api_base(config)}/v1/accounts"
    account_type = str(connect_cfg.get("account_type") or "express").strip()
    payload: dict[str, str] = {
        "type": account_type,
        "metadata[school_id]": str(getattr(school, "pk", "") or ""),
        "metadata[school_slug]": str(getattr(school, "slug", "") or "")[:500],
        "metadata[tenant_slug]": str(getattr(school, "slug", "") or "")[:500],
    }
    country = str(getattr(school, "country_code", "") or "").strip().upper()
    if len(country) == 2:
        payload["country"] = country
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    status_code, body, raw_text = post(url, payload, headers, 30)
    if not 200 <= int(status_code or 0) < 300:
        err = ""
        if isinstance(body.get("error"), dict):
            err = str(body["error"].get("message") or "")
        return False, err or raw_text or "Stripe account creation failed.", body
    account_id = str(body.get("id") or "").strip()
    if not account_id:
        return False, "Stripe did not return an account id.", body
    return True, "", body


def create_account_link(
    *,
    config: PlatformBillingProcessorConfig,
    account_id: str,
    refresh_url: str,
    return_url: str,
    http_post_form=None,
) -> tuple[bool, str, str, dict[str, Any]]:
    key = stripe_secret_key(config)
    acct = (account_id or "").strip()
    if not key:
        return False, "Stripe secret key is not configured.", "", {}
    if not acct:
        return False, "Stripe Connect account id is missing.", "", {}

    post = http_post_form or _default_form_post
    url = f"{stripe_api_base(config)}/v1/account_links"
    payload = {
        "account": acct,
        "refresh_url": refresh_url,
        "return_url": return_url,
        "type": "account_onboarding",
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    status_code, body, raw_text = post(url, payload, headers, 30)
    if not 200 <= int(status_code or 0) < 300:
        err = ""
        if isinstance(body.get("error"), dict):
            err = str(body["error"].get("message") or "")
        return False, err or raw_text or "Stripe account link failed.", "", body
    link_url = str(body.get("url") or "").strip()
    if not link_url:
        return False, "Stripe did not return an onboarding URL.", "", body
    return True, "", link_url, body


def fetch_connect_account(
    *,
    config: PlatformBillingProcessorConfig,
    account_id: str,
    http_get=None,
) -> tuple[bool, str, dict[str, Any]]:
    key = stripe_secret_key(config)
    acct = (account_id or "").strip()
    if not key:
        return False, "Stripe secret key is not configured.", {}
    if not acct:
        return False, "Stripe Connect account id is missing.", {}

    get = http_get or _default_get
    url = f"{stripe_api_base(config)}/v1/accounts/{acct}"
    headers = {"Authorization": f"Bearer {key}"}
    status_code, body, raw_text = get(url, headers, 30)
    if not 200 <= int(status_code or 0) < 300:
        err = ""
        if isinstance(body.get("error"), dict):
            err = str(body["error"].get("message") or "")
        return False, err or raw_text or "Stripe account fetch failed.", body
    return True, "", body


HttpPostForm = Callable[[str, dict[str, str], dict[str, str], int], tuple[int, dict, str]]
