"""
Internal contract for SMS delivery. Implementations in sms_twilio, sms_africastalking.
"""

from __future__ import annotations

import importlib.util
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


# Provider key -> the top-level vendor SDK module its adapter imports at send
# time. Used by :func:`sms_sdk_available` so callers can tell "operator has not
# configured this provider" apart from "the wheel is missing from the deployed
# image" -- the second one is a deploy defect and must never look like a
# successful or merely-unconfigured send.
SMS_PROVIDER_SDK_MODULES: dict[str, str] = {
    "twilio": "twilio",
    "africastalking": "africastalking",
}


def sms_sdk_available(provider_key: str | None) -> bool:
    """True when the vendor SDK backing ``provider_key`` is importable.

    ``console`` / blank / unknown provider keys have no SDK requirement and
    return True (there is nothing to import); a known provider whose wheel is
    absent from the image returns False.
    """
    key = (provider_key or "").strip().lower()
    module = SMS_PROVIDER_SDK_MODULES.get(key)
    if not module:
        return True
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, AttributeError, ModuleNotFoundError):
        # A broken/partial install raises rather than returning None. Treat it
        # exactly like "absent" -- unusable is unusable.
        return False


@dataclass
class SMSResult:
    """Result of an SMS send (internal only)."""

    ok: bool
    provider_message_id: str | None = None
    error: str | None = None


class SMSProvider(ABC):
    """Abstract SMS backend. All SMS goes through this contract."""

    #: Provider key this adapter implements (see SMS_PROVIDER_SDK_MODULES).
    provider_key: str = ""

    def sdk_available(self) -> bool:
        """False when this adapter's vendor SDK is not installed."""
        return sms_sdk_available(self.provider_key)

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
