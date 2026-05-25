"""
PaymentRailAdapter protocol + rail registry + selection runtime.

Architectural facade requested by the runtime-proof-hardening audit. Routes
payment intents through a typed adapter contract with idempotency keys and
signature verification contracts. No live vendor calls are made here — real
integrations live in apps/finance/* and apps/billing/* behind feature flags.

Manual / cash adapter ships as the always-on fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Protocol


logger = logging.getLogger(__name__)


class PaymentRailUnavailableError(RuntimeError):
    pass


class PaymentRailSignatureError(RuntimeError):
    pass


class PaymentRailIdempotencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PaymentIntent:
    tenant_id: str
    currency: str
    amount: Decimal
    idempotency_key: str
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("amount must be Decimal")  # money-float-allow: enforcement, not a money read
        if self.amount <= 0:
            raise ValueError("amount must be positive")
        if not self.idempotency_key:
            raise ValueError("idempotency_key required")


@dataclass
class PaymentResult:
    rail_id: str
    success: bool
    reference: str
    detail: str = ""


class PaymentRailAdapter(Protocol):
    rail_id: str
    currencies: tuple[str, ...]
    enabled: bool

    def authorize(self, intent: PaymentIntent) -> PaymentResult: ...

    def verify_webhook_signature(
        self,
        *,
        payload: bytes,
        signature_header: str,
    ) -> bool: ...


@dataclass
class _RegistryEntry:
    adapter: PaymentRailAdapter
    enabled: bool = True


class PaymentRailRegistry:
    def __init__(self) -> None:
        self._entries: list[_RegistryEntry] = []
        self._idempotency_seen: dict[str, str] = {}

    def register(self, adapter: PaymentRailAdapter, *, enabled: bool = True) -> None:
        self._entries.append(_RegistryEntry(adapter=adapter, enabled=enabled))

    def clear(self) -> None:
        self._entries.clear()
        self._idempotency_seen.clear()

    def rails(self) -> list[PaymentRailAdapter]:
        return [e.adapter for e in self._entries]

    def select(self, *, currency: str, preferred: Iterable[str] = ()) -> PaymentRailAdapter:
        ordered: list[PaymentRailAdapter] = []
        preferred_list = list(preferred)
        for pref in preferred_list:
            for entry in self._entries:
                if entry.enabled and entry.adapter.enabled and entry.adapter.rail_id == pref:
                    if not entry.adapter.currencies or currency in entry.adapter.currencies:
                        ordered.append(entry.adapter)
        if not ordered:
            for entry in self._entries:
                if entry.enabled and entry.adapter.enabled:
                    if not entry.adapter.currencies or currency in entry.adapter.currencies:
                        ordered.append(entry.adapter)
        if not ordered:
            raise PaymentRailUnavailableError(
                f"no enabled rail for currency={currency!r}"
            )
        return ordered[0]

    def authorize(
        self,
        intent: PaymentIntent,
        *,
        preferred: Iterable[str] = (),
    ) -> PaymentResult:
        seen = self._idempotency_seen.get(intent.idempotency_key)
        if seen and seen != _intent_fingerprint(intent):
            raise PaymentRailIdempotencyError(
                "idempotency_key already used with different intent"
            )
        rail = self.select(currency=intent.currency, preferred=preferred)
        result = rail.authorize(intent)
        self._idempotency_seen[intent.idempotency_key] = _intent_fingerprint(intent)
        logger.info(
            "payment_rail.authorize rail=%s success=%s currency=%s",
            result.rail_id,
            result.success,
            intent.currency,
            extra={"scope": "payment_rail.authorize"},
        )
        return result


def _intent_fingerprint(intent: PaymentIntent) -> str:
    raw = f"{intent.tenant_id}|{intent.currency}|{intent.amount}|{intent.description}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


_REGISTRY = PaymentRailRegistry()


def registry() -> PaymentRailRegistry:
    return _REGISTRY


@dataclass
class ManualFallbackRail:
    rail_id: str = "manual-cash"
    currencies: tuple[str, ...] = ()
    enabled: bool = True
    shared_secret: bytes = b""

    def authorize(self, intent: PaymentIntent) -> PaymentResult:
        return PaymentResult(
            rail_id=self.rail_id,
            success=True,
            reference=f"manual:{intent.idempotency_key[:12]}",
            detail="recorded for manual settlement",
        )

    def verify_webhook_signature(self, *, payload: bytes, signature_header: str) -> bool:
        if not self.shared_secret:
            return False
        digest = hmac.new(self.shared_secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, signature_header)


def register_manual_fallback() -> None:
    _REGISTRY.register(ManualFallbackRail(), enabled=True)


__all__ = [
    "ManualFallbackRail",
    "PaymentIntent",
    "PaymentRailAdapter",
    "PaymentRailIdempotencyError",
    "PaymentRailRegistry",
    "PaymentRailSignatureError",
    "PaymentRailUnavailableError",
    "PaymentResult",
    "register_manual_fallback",
    "registry",
]
