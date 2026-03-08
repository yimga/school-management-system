from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.http import HttpRequest
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.billing.models import PlatformBillingProcessorConfig


def _request_header(request: HttpRequest, header_name: str) -> str:
    return (
        request.headers.get(header_name)
        or request.META.get(f"HTTP_{header_name.upper().replace('-', '_')}")
        or ""
    )


def _parse_json_body(raw_body: bytes) -> dict:
    if not raw_body:
        return {}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _hexdigest(secret: str, raw_body: bytes, algorithm: str) -> str:
    hash_impl = getattr(hashlib, algorithm, None)
    if hash_impl is None:
        raise ValueError(f"Unsupported signature algorithm: {algorithm}")
    return hmac.new(secret.encode(), raw_body, hash_impl).hexdigest()


def _to_decimal_minor_units(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return (Decimal(str(value)) / Decimal("100")).quantize(Decimal("0.01"))


def _to_minor_units(value) -> int:
    return int((Decimal(str(value or "0")) * Decimal("100")).quantize(Decimal("1")))


def _to_datetime_from_unix(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _parse_response_json(raw_text: str) -> dict:
    try:
        payload = json.loads(raw_text or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _default_json_post(url: str, payload: dict, headers: dict[str, str], timeout: int = 30) -> tuple[int, dict, str]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
            return int(response.getcode() or 200), _parse_response_json(raw_text), raw_text
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return int(exc.code or 500), _parse_response_json(detail), detail
    except URLError as exc:
        return 0, {}, str(exc.reason)


def _default_form_post(url: str, data: dict[str, str], headers: dict[str, str], timeout: int = 30) -> tuple[int, dict, str]:
    body = urlencode(data, doseq=True).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
            return int(response.getcode() or 200), _parse_response_json(raw_text), raw_text
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return int(exc.code or 500), _parse_response_json(detail), detail
    except URLError as exc:
        return 0, {}, str(exc.reason)


class BasePlatformBillingProcessor:
    def __init__(self, config: PlatformBillingProcessorConfig):
        self.config = config

    def parse_request(self, request: HttpRequest) -> tuple[dict, bytes]:
        raw_body = request.body or b""
        return _parse_json_body(raw_body), raw_body

    def verify_request(self, request: HttpRequest, raw_body: bytes) -> tuple[bool, str]:
        if not self.config.webhook_secret:
            return False, "Webhook secret is not configured."

        signature = _request_header(request, self.config.signature_header).strip()
        if not signature:
            return False, "Signature header is missing."

        expected = _hexdigest(self.config.webhook_secret, raw_body, self.config.signature_algorithm)
        candidate = signature
        if self.config.signature_style == PlatformBillingProcessorConfig.SignatureStyle.PREFIXED_HMAC:
            if "=" in signature:
                _, candidate = signature.split("=", 1)
            candidate = candidate.strip()
        if not hmac.compare_digest(candidate.lower(), expected.lower()):
            return False, "Webhook signature mismatch."
        return True, ""

    def normalize(self, payload: dict) -> list[dict]:
        """Subclasses must implement; converts provider webhook payload to normalized list of billing snapshots."""
        raise NotImplementedError

    def execute_payout(self, payout, *, http_post_json=None, http_post_form=None) -> dict:
        """Subclasses must implement; executes a payout via the provider API."""
        raise NotImplementedError


class NoOpPlatformBillingProcessor(BasePlatformBillingProcessor):
    """No-op processor for unconfigured or placeholder provider; never raises."""

    def normalize(self, payload: dict) -> list[dict]:
        return []

    def execute_payout(self, payout, *, http_post_json=None, http_post_form=None) -> dict:
        return {"status": "noop", "message": "Processor not implemented."}


class GenericRelayProcessor(BasePlatformBillingProcessor):
    def normalize(self, payload: dict) -> list[dict]:
        snapshots = payload if isinstance(payload, list) else payload.get("snapshots") or [payload]
        normalized = []
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                continue
            if snapshot.get("current_period_start") and isinstance(snapshot["current_period_start"], str):
                snapshot["current_period_start"] = parse_datetime(snapshot["current_period_start"])
            if snapshot.get("current_period_end") and isinstance(snapshot["current_period_end"], str):
                snapshot["current_period_end"] = parse_datetime(snapshot["current_period_end"])
            if snapshot.get("trial_end_date") and isinstance(snapshot["trial_end_date"], str):
                snapshot["trial_end_date"] = parse_date(snapshot["trial_end_date"])
            if snapshot.get("happened_at") and isinstance(snapshot["happened_at"], str):
                snapshot["happened_at"] = parse_datetime(snapshot["happened_at"])
            normalized.append(snapshot)
        return normalized

    def execute_payout(self, payout, *, http_post_json=None, http_post_form=None) -> dict:
        del http_post_form
        endpoint_url = str(
            self.config.metadata.get("payout_endpoint_url")
            or self.config.metadata.get("relay_payout_url")
            or ""
        ).strip()
        if not endpoint_url:
            raise ValueError("Relay payout endpoint URL is not configured.")
        bearer_token = str(self.config.metadata.get("payout_bearer_token") or "").strip()
        headers = {"Content-Type": "application/json"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        payload = {
            "payout_id": payout.pk,
            "payee_name": payout.payee_name,
            "payee_ref": payout.payee_ref,
            "amount": str(payout.net_amount),
            "currency": payout.currency_code,
            "scope": payout.payout_scope,
            "external_payout_ref": payout.external_payout_ref,
            "source_school_id": str(getattr(payout.source_school, "pk", "") or "") or None,
            "metadata": payout.metadata or {},
        }
        http_post_json = http_post_json or _default_json_post
        status_code, response_payload, raw_text = http_post_json(endpoint_url, payload, headers, 30)
        if not 200 <= int(status_code or 0) < 300:
            raise ValueError(raw_text or "Relay payout request failed.")
        processor_status = str(response_payload.get("status") or "submitted").strip().lower()
        return {
            "external_payout_ref": (
                response_payload.get("external_payout_ref")
                or response_payload.get("payout_id")
                or response_payload.get("id")
                or ""
            ),
            "status": processor_status or "submitted",
            "payload": response_payload,
            "message": str(response_payload.get("message") or "").strip(),
        }


class StripeConnectProcessor(BasePlatformBillingProcessor):
    def verify_request(self, request: HttpRequest, raw_body: bytes) -> tuple[bool, str]:
        if self.config.signature_style != PlatformBillingProcessorConfig.SignatureStyle.STRIPE_V1:
            return super().verify_request(request, raw_body)
        signature = _request_header(request, self.config.signature_header).strip()
        if not self.config.webhook_secret:
            return False, "Webhook secret is not configured."
        if not signature:
            return False, "Stripe signature header is missing."

        parts = {}
        for chunk in signature.split(","):
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            parts[key.strip()] = value.strip()
        timestamp = parts.get("t")
        signature_v1 = parts.get("v1")
        if not timestamp or not signature_v1:
            return False, "Stripe signature header is malformed."
        try:
            timestamp_int = int(timestamp)
        except (TypeError, ValueError):
            return False, "Stripe signature timestamp is invalid."

        now_ts = int(timezone.now().timestamp())
        if abs(now_ts - timestamp_int) > int(self.config.timestamp_tolerance_seconds or 300):
            return False, "Stripe signature timestamp is outside the allowed tolerance."

        signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
        expected = hmac.new(
            self.config.webhook_secret.encode(),
            signed_payload,
            getattr(hashlib, self.config.signature_algorithm, hashlib.sha256),
        ).hexdigest()
        if not hmac.compare_digest(signature_v1.lower(), expected.lower()):
            return False, "Stripe signature mismatch."
        return True, ""

    def normalize(self, payload: dict) -> list[dict]:
        event_type = str(payload.get("type") or "").strip()
        data = payload.get("data") or {}
        obj = data.get("object") if isinstance(data, dict) else {}
        if not isinstance(obj, dict):
            obj = {}
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        school_slug = metadata.get("school_slug") or metadata.get("tenant_slug") or metadata.get("school")
        school_id = metadata.get("school_id")
        external_customer_ref = obj.get("customer") or metadata.get("customer")
        external_subscription_ref = obj.get("subscription") or obj.get("id")
        stripe_status = str(obj.get("status") or "").strip().lower()

        subscription_status = stripe_status or "active"
        account_status = "active"
        if event_type == "invoice.payment_failed":
            account_status = "past_due"
            subscription_status = stripe_status or "past_due"
        elif event_type == "customer.subscription.deleted":
            account_status = "canceled"
            subscription_status = "canceled"
        elif stripe_status in {"past_due", "unpaid"}:
            account_status = "past_due"
            subscription_status = "past_due"
        elif stripe_status == "canceled":
            account_status = "canceled"
            subscription_status = "canceled"

        message = ""
        if event_type == "invoice.payment_failed":
            message = str(
                ((obj.get("last_finalization_error") or {}).get("message"))
                or ((obj.get("last_payment_error") or {}).get("message"))
                or "Stripe reported a payment failure."
            )

        return [
            {
                "school_slug": school_slug,
                "school_id": school_id,
                "event_type": event_type or "stripe.event",
                "account_status": account_status,
                "subscription_status": subscription_status,
                "external_customer_ref": external_customer_ref,
                "external_subscription_ref": external_subscription_ref,
                "currency_code": str(obj.get("currency") or "").upper() or None,
                "billed_amount": _to_decimal_minor_units(obj.get("amount_paid") or obj.get("amount_due")),
                "current_period_start": _to_datetime_from_unix(
                    obj.get("current_period_start") or metadata.get("current_period_start")
                ),
                "current_period_end": _to_datetime_from_unix(
                    obj.get("current_period_end") or metadata.get("current_period_end")
                ),
                "message": message,
                "payload": payload,
            }
        ]

    def execute_payout(self, payout, *, http_post_json=None, http_post_form=None) -> dict:
        del http_post_json
        api_key = str(
            self.config.metadata.get("api_key")
            or self.config.metadata.get("secret_key")
            or self.config.metadata.get("bearer_token")
            or ""
        ).strip()
        if not api_key:
            raise ValueError("Stripe processor API key is not configured.")
        destination = str(payout.payee_ref or "").strip()
        if not destination:
            raise ValueError("Stripe payout destination reference is missing.")
        api_base_url = str(self.config.metadata.get("api_base_url") or "https://api.stripe.com").rstrip("/")
        endpoint_url = str(self.config.metadata.get("payout_api_url") or f"{api_base_url}/v1/transfers").strip()
        transfer_group_prefix = str(self.config.metadata.get("transfer_group_prefix") or "runmycampus").strip()
        descriptor = str(self.config.metadata.get("statement_descriptor") or "RunMyCampus payout").strip()
        payload = {
            "amount": str(_to_minor_units(payout.net_amount)),
            "currency": str(payout.currency_code or "USD").lower(),
            "destination": destination,
            "description": f"{descriptor} {payout.payee_name}".strip(),
            "transfer_group": f"{transfer_group_prefix}:{payout.pk}",
            "metadata[payout_id]": str(payout.pk),
            "metadata[payee_ref]": destination,
            "metadata[payout_scope]": str(payout.payout_scope),
        }
        if getattr(payout.source_school, "pk", None):
            payload["metadata[source_school_id]"] = str(payout.source_school.pk)
        http_post_form = http_post_form or _default_form_post
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        status_code, response_payload, raw_text = http_post_form(endpoint_url, payload, headers, 30)
        if not 200 <= int(status_code or 0) < 300:
            raise ValueError(
                str(response_payload.get("error", {}).get("message") or raw_text or "Stripe payout request failed.")
            )
        processor_status = "paid" if response_payload.get("status") == "paid" else "submitted"
        return {
            "external_payout_ref": str(response_payload.get("id") or ""),
            "status": processor_status,
            "payload": response_payload,
            "message": str(response_payload.get("description") or "").strip(),
        }


_PROCESSOR_REGISTRY = {
    "relay": GenericRelayProcessor,
    "stripe": StripeConnectProcessor,
}


def get_platform_billing_processor(config: PlatformBillingProcessorConfig) -> BasePlatformBillingProcessor:
    processor_class = _PROCESSOR_REGISTRY.get(config.code, GenericRelayProcessor)
    return processor_class(config)
