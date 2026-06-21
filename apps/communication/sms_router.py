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

# E.164 calling-code → ISO-3166 alpha-2, scoped to exactly the countries the
# chain map above distinguishes. Unknown prefixes resolve to ``None`` so the
# router falls back to ``_DEFAULT_CHAIN`` (identical to the pre-failover path).
# These are ITU-T E.164 country-calling-code constants, not tenant config.
_CALLING_CODE_TO_ISO: tuple[tuple[str, str], ...] = (
    ("237", "CM"),  # magic-number-allow: itu-e164-calling-code-cameroon
    ("234", "NG"),  # magic-number-allow: itu-e164-calling-code-nigeria
    ("254", "KE"),  # magic-number-allow: itu-e164-calling-code-kenya
    ("233", "GH"),  # magic-number-allow: itu-e164-calling-code-ghana
    ("44", "GB"),  # magic-number-allow: itu-e164-calling-code-united-kingdom
    ("1", "US"),  # magic-number-allow: itu-e164-calling-code-north-america
)


@dataclass(frozen=True)
class SMSRouteAttempt:
    provider_key: str
    result: SMSResult


@dataclass(frozen=True)
class SMSRouterOutcome:
    """Structured failover result a caller can branch on without re-deriving it.

    ``ok`` mirrors the winning provider's ``result.ok``; ``provider_key`` is the
    provider that accepted the message (``None`` when every provider failed);
    ``result`` is the final :class:`SMSResult`; ``attempts`` is the ordered
    per-provider trail (success + every failover) for receipt persistence.
    """

    ok: bool
    provider_key: str | None
    result: SMSResult
    attempts: list[SMSRouteAttempt]


def country_code_from_e164(to_phone: str | None) -> str | None:
    """Best-effort ISO-3166 alpha-2 from an E.164 number's calling-code prefix.

    Returns ``None`` for blank/unparseable/unmapped numbers — the router then
    uses :data:`_DEFAULT_CHAIN`, so an unknown country never changes behaviour
    versus the single-provider path. Longest-prefix-first so ``+1`` doesn't
    shadow a future 3-digit ``1`` overlap.
    """
    digits = "".join(ch for ch in str(to_phone or "") if ch.isdigit())
    if not digits:
        return None
    for code, iso in sorted(_CALLING_CODE_TO_ISO, key=lambda kv: -len(kv[0])):
        if digits.startswith(code):
            return iso
    return None


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

    @classmethod
    def for_destination(cls, site_settings: Any, to_phone: str | None) -> "SMSMultiGatewayRouter":
        """Construct a router whose chain is country-aware for ``to_phone``."""
        return cls(site_settings, country_code=country_code_from_e164(to_phone))

    def provider_chain(self) -> Sequence[str]:
        return _provider_chain_for_country(self.country_code)

    def route(
        self,
        to_phone: str,
        body: str,
        *,
        sender_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SMSRouterOutcome:
        """Run the failover chain and return a structured :class:`SMSRouterOutcome`.

        Thin wrapper over :meth:`send` (which owns the failover loop) that names
        the winning provider so the caller can persist attempts + record the
        circuit-breaker outcome without re-walking the trail.
        """
        result, attempts = self.send(
            to_phone,
            body,
            sender_id=sender_id,
            idempotency_key=idempotency_key,
        )
        winning_key: str | None = None
        if result.ok:
            for attempt in attempts:
                if attempt.result.ok:
                    winning_key = attempt.provider_key
                    break
        return SMSRouterOutcome(
            ok=bool(result.ok),
            provider_key=winning_key,
            result=result,
            attempts=attempts,
        )

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
