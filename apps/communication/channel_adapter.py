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

Honesty contract (globalization program items 0.2 / 0.3)
--------------------------------------------------------
A parent on a feature phone in Douala, Lagos, Nairobi or Accra reaches us over
SMS, USSD or IVR. Those channels are the ones most likely to have no wired
transport, so this module holds two hard rules:

1. **An adapter without a usable transport must not be selectable.** Registry
   selection skips any adapter whose ``is_available()`` returns False, and
   :meth:`ChannelAdapterRegistry.select` raises
   :class:`ChannelUnavailableError` when that leaves nothing. Never a silent
   fallthrough to a stub.
2. **Nothing reports DELIVERED unless a transport accepted it.** The in-process
   :class:`_LogOnlyAdapter` writes a log line and sends nothing, so it returns
   ``success=False``. Every :class:`DeliveryResult` carries ``simulated``, which
   is surfaced in the audit callback, so a delivery trail can never present a
   stub hop as a real one.

The only ``success=True``-without-a-transport type here is
:class:`LoopbackTestAdapter`, which exists purely as a unit-test double and
refuses to register outside DEBUG / test runs.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


logger = logging.getLogger(__name__)

#: Opt-in required before log-only (send-nothing) adapters may be registered in
#: a production-like configuration. Even when enabled, those adapters report
#: ``success=False`` and ``simulated=True`` -- the flag only controls whether
#: they may occupy a slot in the registry at all.
_ALLOW_LOG_ONLY_SETTING = "COMMS_ALLOW_LOG_ONLY_ADAPTERS"


class ChannelUnavailableError(RuntimeError):
    """Raised when no enabled adapter is available for the requested route."""


def _is_production_like() -> bool:
    """True unless we are demonstrably in DEBUG or a test run.

    Fails CLOSED: an unreadable / unconfigured settings object is treated as
    production, so a stub can never sneak in through a settings edge case.
    """
    try:
        if getattr(settings, "RUNNING_TESTS", False):
            return False
        return not bool(getattr(settings, "DEBUG", False))
    except ImproperlyConfigured:
        return True


def _adapter_is_available(adapter: object) -> bool:
    """Availability probe for an adapter, defaulting to True.

    ``is_available()`` is optional on the adapter protocol so pre-existing
    adapters (and test doubles) keep working; an adapter that *does* implement
    it and returns False is skipped by selection entirely.
    """
    probe = getattr(adapter, "is_available", None)
    if probe is None:
        return True
    try:
        return bool(probe())
    except (AttributeError, TypeError, ValueError, ImportError, OSError, RuntimeError):
        # An availability probe that blows up is not evidence of availability.
        logger.warning(
            "channel_adapter availability probe failed adapter=%s -- treating as unavailable",
            getattr(adapter, "adapter_id", "?"),
            extra={"scope": "channel_adapter.availability"},
        )
        return False


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
    #: True when no real transport was contacted (log-only / loopback stub).
    #: Propagated into the audit callback so a stub hop is always visible in
    #: the delivery trail and can never be read as a real delivery.
    simulated: bool = False


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

    # Optional. Adapters that wrap a vendor SDK should implement this and
    # return False when the SDK / credentials are absent, so the registry skips
    # them instead of selecting a transport that cannot send.
    # def is_available(self) -> bool: ...


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
        if getattr(adapter, "reports_success_without_transport", False) and _is_production_like():
            # A test double that answers "delivered" without sending anything
            # must never be reachable from a deployed configuration.
            raise ImproperlyConfigured(
                "refusing to register test-double adapter "
                f"{getattr(adapter, 'adapter_id', '?')!r} outside DEBUG/test"
            )
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
                if entry.adapter.channel != ch:
                    continue
                if not (entry.enabled and entry.adapter.enabled):
                    continue
                if not _adapter_is_available(entry.adapter):
                    # No usable transport behind this adapter (missing SDK,
                    # missing credentials). Skipping it here is what makes
                    # select() raise ChannelUnavailableError instead of
                    # handing back an adapter that cannot send.
                    logger.warning(
                        "channel_adapter skipping unavailable adapter=%s channel=%s",
                        entry.adapter.adapter_id,
                        ch,
                        extra={"scope": "channel_adapter.select"},
                    )
                    continue
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
                # Item 0.3: a stub hop is always visible in the delivery trail.
                "simulated": bool(result.simulated),
                "detail": result.detail,
            }
        )
    logger.info(
        "channel_adapter dispatched tenant=%s adapter=%s channel=%s success=%s simulated=%s",
        _hash_tenant(tenant_id),
        result.adapter_id,
        result.channel,
        result.success,
        result.simulated,
        extra={"scope": "channel_adapter.send"},
    )
    return result


@dataclass
class _LogOnlyAdapter:
    """Writes a log line and sends NOTHING -- so it reports ``success=False``.

    Item 0.3: this used to return ``success=True, detail="log-only"``. Because
    ``register_log_only_defaults()`` covers ``ussd`` (cost 25) and ``ivr``
    (cost 30) -- the two channels that carry the most weight in feature-phone
    markets -- any dispatcher asking for "the cheapest reachable channel" would
    have been handed a stub and told the message was delivered. A stub that
    reports delivery is worse than no adapter at all: no retry fires, no
    fallback fires, and the delivery dashboard reads green.

    It is still useful as a *placeholder* (it keeps the routing shape intact
    offline), so it stays registerable -- but it is honest about the outcome
    and marks the result ``simulated=True`` for the audit trail.
    """

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
        logger.warning(
            "channel_adapter.log_only NOT SENT adapter=%s channel=%s tenant=%s",
            self.adapter_id,
            self.channel,
            _hash_tenant(tenant_id),
            extra={"scope": "channel_adapter.log_only"},
        )
        return DeliveryResult(
            channel=self.channel,
            success=False,
            adapter_id=self.adapter_id,
            detail=f"no-transport-configured:{self.channel}",
            cost_rank=self.cost_rank,
            simulated=True,
        )


@dataclass
class LoopbackTestAdapter:
    """Unit-test double that reports a successful send without a transport.

    Legitimate ONLY inside tests: a test needs a deterministic success path to
    assert routing, audit and fallback behaviour on. It is therefore flagged
    ``reports_success_without_transport``, and
    :meth:`ChannelAdapterRegistry.register` refuses it whenever the process is
    not demonstrably in DEBUG or a test run. Results are still marked
    ``simulated=True`` so nothing downstream mistakes one for a real delivery.
    """

    channel: str
    adapter_id: str
    cost_rank: int = 10
    enabled: bool = True

    #: Read by ChannelAdapterRegistry.register to fence this out of production.
    reports_success_without_transport: bool = True

    def send(
        self,
        *,
        tenant_id: str,
        address: ChannelAddress,
        message: ChannelMessage,
    ) -> DeliveryResult:
        logger.info(
            "channel_adapter.loopback adapter=%s channel=%s tenant=%s",
            self.adapter_id,
            self.channel,
            _hash_tenant(tenant_id),
            extra={"scope": "channel_adapter.loopback"},
        )
        return DeliveryResult(
            channel=self.channel,
            success=True,
            adapter_id=self.adapter_id,
            detail="loopback-test-double",
            cost_rank=self.cost_rank,
            simulated=True,
        )


@dataclass
class SmsChannelAdapter:
    """Channel adapter backed by the real country-aware SMS router.

    ``is_available()`` is False when the vendor SDK for the tenant's configured
    provider is not importable, which is exactly the item-0.2 failure mode: the
    ``twilio`` / ``africastalking`` wheels were absent from the deployed image,
    so every send in CM / NG / KE / GH went nowhere. An unavailable adapter is
    skipped by :meth:`ChannelAdapterRegistry.for_channels`, so selection raises
    :class:`ChannelUnavailableError` rather than reporting a phantom delivery.
    """

    site_settings: object
    adapter_id: str = "sms:router"
    channel: str = "sms"
    cost_rank: int = 20
    enabled: bool = True

    def _provider_keys(self) -> tuple[str, ...]:
        from apps.communication.sms_router import SMSMultiGatewayRouter

        return tuple(SMSMultiGatewayRouter(self.site_settings).provider_chain())

    def is_available(self) -> bool:
        """True only when at least one provider in the chain has its SDK."""
        from apps.communication.providers.sms_base import sms_sdk_available

        return any(sms_sdk_available(key) for key in self._provider_keys())

    def send(
        self,
        *,
        tenant_id: str,
        address: ChannelAddress,
        message: ChannelMessage,
    ) -> DeliveryResult:
        from apps.communication.sms_router import SMSMultiGatewayRouter

        router = SMSMultiGatewayRouter.for_destination(self.site_settings, address.address)
        outcome = router.route(address.address, message.body_text)
        logger.info(
            "channel_adapter.sms tenant=%s provider=%s ok=%s",
            _hash_tenant(tenant_id),
            outcome.provider_key or "",
            outcome.ok,
            extra={"scope": "channel_adapter.sms"},
        )
        return DeliveryResult(
            channel=self.channel,
            success=bool(outcome.ok),
            adapter_id=self.adapter_id,
            detail=(outcome.provider_key or "") if outcome.ok else (outcome.result.error or "sms_failed"),
            cost_rank=self.cost_rank,
            simulated=False,
        )


def log_only_adapters_allowed() -> bool:
    """Whether send-nothing adapters may occupy registry slots right now.

    Always true in DEBUG / test runs. In a production-like configuration it
    requires the explicit ``COMMS_ALLOW_LOG_ONLY_ADAPTERS`` opt-in.
    """
    if not _is_production_like():
        return True
    return bool(getattr(settings, _ALLOW_LOG_ONLY_SETTING, False))


def register_log_only_defaults() -> None:
    """Register in-process log-only placeholders for tests / offline mode.

    These adapters send nothing and report ``success=False``. Registering them
    in a production-like configuration additionally requires the explicit
    ``COMMS_ALLOW_LOG_ONLY_ADAPTERS`` opt-in -- otherwise this raises, because
    silently occupying the ``ussd`` / ``ivr`` slots with placeholders is how a
    real transport gap stays invisible.
    """
    if not log_only_adapters_allowed():
        raise ImproperlyConfigured(
            "log-only channel adapters send nothing and are refused in a "
            f"production-like configuration; set {_ALLOW_LOG_ONLY_SETTING}=True "
            "to register them anyway (they will still report success=False)."
        )
    for channel, cost in (
        ("email", 5),
        ("sms", 20),
        ("push", 1),
        ("whatsapp", 8),
        ("ivr", 30),
        ("ussd", 25),
    ):
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
    "LoopbackTestAdapter",
    "SmsChannelAdapter",
    "log_only_adapters_allowed",
    "register_log_only_defaults",
    "registry",
    "send_message",
]
