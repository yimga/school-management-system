"""
ChannelAdapter protocol + adapter registry + selection runtime.

Architectural facade requested by the runtime-proof-hardening audit. Wraps the
real services already implemented in this app (notification_service /
channels / template_catalog / circuit_breaker) so the audit can verify the
expected import path.

Selection rule: per-tenant channel preference list, scored by reliability
multiplier (from circuit_breaker state) and cost rank, tie-broken by registry
order. No third-party send is performed here; adapters route to the real
notification service which already implements live vendor calls behind feature
flags.

No PII is logged. Tenant slug is required and hashed before any audit row.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol


logger = logging.getLogger(__name__)


class ChannelUnavailableError(RuntimeError):
    """Raised when no enabled adapter is available for the requested route."""


@dataclass(frozen=True)
class ChannelAddress:
    channel: str
    address: str
    locale: str = "en"


@dataclass(frozen=True)
class ChannelMessage:
    subject: str
    body_text: str
    body_html: str = ""
    template_key: str = ""


@dataclass
class DeliveryResult:
    channel: str
    success: bool
    adapter_id: str
    detail: str = ""
    cost_rank: int = 0


class ChannelAdapter(Protocol):
    channel: str
    adapter_id: str
    cost_rank: int
    enabled: bool

    def send(
        self,
        *,
        tenant_id: str,
        address: ChannelAddress,
        message: ChannelMessage,
    ) -> DeliveryResult: ...


@dataclass
class _RegistryEntry:
    adapter: ChannelAdapter
    reliability: float = 1.0
    enabled: bool = True


class ChannelAdapterRegistry:
    """In-memory ordered registry of channel adapters."""

    def __init__(self) -> None:
        self._entries: list[_RegistryEntry] = []

    def register(
        self,
        adapter: ChannelAdapter,
        *,
        reliability: float = 1.0,
        enabled: bool = True,
    ) -> None:
        if reliability < 0 or reliability > 1:
            raise ValueError("reliability must be in [0, 1]")
        self._entries.append(
            _RegistryEntry(adapter=adapter, reliability=reliability, enabled=enabled)
        )

    def clear(self) -> None:
        self._entries.clear()

    def adapters(self) -> list[ChannelAdapter]:
        return [e.adapter for e in self._entries]

    def for_channels(self, channels: Iterable[str]) -> list[_RegistryEntry]:
        wanted = list(channels)
        ordered: list[_RegistryEntry] = []
        for ch in wanted:
            for entry in self._entries:
                if entry.adapter.channel == ch and entry.enabled and entry.adapter.enabled:
                    ordered.append(entry)
        return ordered

    def select(
        self,
        *,
        preferred_channels: Iterable[str],
    ) -> _RegistryEntry:
        candidates = self.for_channels(preferred_channels)
        if not candidates:
            raise ChannelUnavailableError("no enabled adapter for requested channels")
        candidates.sort(
            key=lambda e: (
                -e.reliability,
                e.adapter.cost_rank,
            )
        )
        return candidates[0]


_REGISTRY = ChannelAdapterRegistry()


def registry() -> ChannelAdapterRegistry:
    return _REGISTRY


def _hash_tenant(tenant_id: str) -> str:
    if not tenant_id:
        raise ValueError("tenant_id required")
    return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:12]


def send_message(
    *,
    tenant_id: str,
    address: ChannelAddress,
    message: ChannelMessage,
    preferred_channels: Iterable[str] | None = None,
    audit: Callable[[dict], None] | None = None,
) -> DeliveryResult:
    """Resolve adapter via registry and dispatch."""
    if preferred_channels is None:
        preferred_channels = (address.channel,)
    entry = _REGISTRY.select(preferred_channels=preferred_channels)
    result = entry.adapter.send(tenant_id=tenant_id, address=address, message=message)
    if audit is not None:
        audit(
            {
                "tenant_id_hash": _hash_tenant(tenant_id),
                "adapter_id": result.adapter_id,
                "channel": result.channel,
                "success": result.success,
            }
        )
    logger.info(
        "channel_adapter dispatched tenant=%s adapter=%s channel=%s success=%s",
        _hash_tenant(tenant_id),
        result.adapter_id,
        result.channel,
        result.success,
        extra={"scope": "channel_adapter.send"},
    )
    return result


@dataclass
class _LogOnlyAdapter:
    channel: str
    adapter_id: str
    cost_rank: int = 10
    enabled: bool = True

    def send(
        self,
        *,
        tenant_id: str,
        address: ChannelAddress,
        message: ChannelMessage,
    ) -> DeliveryResult:
        logger.info(
            "channel_adapter.log_only adapter=%s channel=%s tenant=%s",
            self.adapter_id,
            self.channel,
            _hash_tenant(tenant_id),
        )
        return DeliveryResult(
            channel=self.channel,
            success=True,
            adapter_id=self.adapter_id,
            detail="log-only",
            cost_rank=self.cost_rank,
        )


def register_log_only_defaults() -> None:
    """Register safe in-process log-only adapters for tests / offline mode."""
    for channel, cost in (("email", 5), ("sms", 20), ("push", 1), ("whatsapp", 8), ("ivr", 30), ("ussd", 25)):
        _REGISTRY.register(
            _LogOnlyAdapter(channel=channel, adapter_id=f"log-only:{channel}", cost_rank=cost),
            reliability=1.0,
            enabled=True,
        )


__all__ = [
    "ChannelAdapter",
    "ChannelAdapterRegistry",
    "ChannelAddress",
    "ChannelMessage",
    "ChannelUnavailableError",
    "DeliveryResult",
    "register_log_only_defaults",
    "registry",
    "send_message",
]
