"""Multi-gateway SMS router with country-aware failover (Phase 4E)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from apps.communication.providers.sms_base import SMSProvider, SMSResult, get_sms_provider

logger = logging.getLogger(__name__)

# Country code → ordered provider keys (first = primary).
_COUNTRY_PROVIDER_CHAIN: dict[str, tuple[str, ...]] = {
    "CM": ("africastalking", "twilio"),
    "NG": ("africastalking", "twilio"),
    "KE": ("africastalking", "twilio"),
    "GH": ("africastalking", "twilio"),
    "US": ("twilio", "africastalking"),
    "GB": ("twilio", "africastalking"),
}

_DEFAULT_CHAIN = ("twilio", "africastalking")


@dataclass(frozen=True)
class SMSRouteAttempt:
    provider_key: str
    result: SMSResult


def _provider_chain_for_country(country_code: str | None) -> tuple[str, ...]:
    iso = str(country_code or "").strip().upper()[:2]
    return _COUNTRY_PROVIDER_CHAIN.get(iso, _DEFAULT_CHAIN)


def _provider_for_key(site_settings: Any, provider_key: str) -> SMSProvider | None:
    patched = type(
        "PatchedSettings",
        (),
        {"sms_provider": provider_key},
    )()
    for attr in ("twilio_account_sid", "twilio_auth_token", "twilio_from_number"):
        if hasattr(site_settings, attr):
            setattr(patched, attr, getattr(site_settings, attr))
    for attr in ("africastalking_username", "africastalking_api_key", "africastalking_sender_id"):
        if hasattr(site_settings, attr):
            setattr(patched, attr, getattr(site_settings, attr))
    # Audit P2 — the Africa's Talking provider reads ``sms_api_key`` /
    # ``sms_username`` / ``sms_sender_id`` (NOT the africastalking_* names), so
    # the patched shim must expose those aliases or the provider always sees
    # "api_key not set". Map both the africastalking_* and any generic sms_*
    # source attributes onto the canonical sms_* names the provider expects.
    _at_alias = {
        "sms_api_key": ("sms_api_key", "africastalking_api_key"),
        "sms_username": ("sms_username", "africastalking_username"),
        "sms_sender_id": ("sms_sender_id", "africastalking_sender_id"),
    }
    for target, sources in _at_alias.items():
        for src in sources:
            if hasattr(site_settings, src) and getattr(site_settings, src):
                setattr(patched, target, getattr(site_settings, src))
                break
    return get_sms_provider(patched)


class SMSMultiGatewayRouter:
    """Try primary then fallback SMS providers for a destination country."""

    def __init__(self, site_settings: Any, *, country_code: str | None = None) -> None:
        self.site_settings = site_settings
        self.country_code = country_code

    def provider_chain(self) -> Sequence[str]:
        return _provider_chain_for_country(self.country_code)

    def send(
        self,
        to_phone: str,
        body: str,
        *,
        sender_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[SMSResult, list[SMSRouteAttempt]]:
        attempts: list[SMSRouteAttempt] = []
        last_result = SMSResult(ok=False, error="no_providers_configured")

        for provider_key in self.provider_chain():
            provider = _provider_for_key(self.site_settings, provider_key)
            if provider is None:
                last_result = SMSResult(ok=False, error=f"provider_unavailable:{provider_key}")
                attempts.append(SMSRouteAttempt(provider_key=provider_key, result=last_result))
                continue
            result = provider.send(
                to_phone,
                body,
                sender_id=sender_id,
                idempotency_key=idempotency_key,
            )
            attempts.append(SMSRouteAttempt(provider_key=provider_key, result=result))
            if result.ok:
                logger.info(
                    "sms_router.delivered provider=%s country=%s",
                    provider_key,
                    self.country_code or "",
                    extra={"scope": "sms_router.send"},
                )
                return result, attempts
            last_result = result
            logger.warning(
                "sms_router.failover provider=%s error=%s",
                provider_key,
                result.error or "",
                extra={"scope": "sms_router.send"},
            )

        return last_result, attempts
