"""
Internal contract for SMS delivery. Implementations in sms_twilio, sms_africastalking.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any



@dataclass
class SMSResult:
    """Result of an SMS send (internal only)."""
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None


class SMSProvider(ABC):
    """Abstract SMS backend. All SMS goes through this contract."""

    @abstractmethod
    def send(
        self,
        to_phone: str,
        body: str,
        *,
        sender_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SMSResult:
        """Send SMS. to_phone must be E.164-style. Returns result with ok and optional provider_message_id."""
        pass

    def health_check(self) -> bool:
        """Optional: verify credentials/connectivity."""
        return True


def get_sms_provider(site_settings: Any) -> SMSProvider | None:
    """
    Return the configured SMS provider adapter for the given site settings.
    Returns None if SMS is not configured (caller should fall back to email).
    """
    if not site_settings:
        return None
    provider = (getattr(site_settings, "sms_provider", None) or "").strip().lower()
    if not provider or provider == "console":
        return None
    if provider == "twilio":
        from .sms_twilio import TwilioSMSProvider
        return TwilioSMSProvider(site_settings)
    if provider == "africastalking":
        from .sms_africastalking import AfricasTalkingSMSProvider
        return AfricasTalkingSMSProvider(site_settings)
    return None
