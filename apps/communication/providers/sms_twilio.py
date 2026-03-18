"""
Twilio SMS adapter. No direct Twilio usage outside this module.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from .sms_base import SMSProvider, SMSResult

logger = logging.getLogger(__name__)

# Typed exceptions for Twilio send (SDK/network).
_SMS_TWILIO_SEND_ERRORS: tuple[type[BaseException], ...] = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    OSError,
    ConnectionError,
    TimeoutError,
    RuntimeError,
)


class TwilioSMSProvider(SMSProvider):
    """SMS via Twilio API."""

    def __init__(self, site_settings: Any):
        self.site_settings = site_settings
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from twilio.rest import Client

            sid = getattr(settings, "TWILIO_ACCOUNT_SID", None) or getattr(
                self.site_settings, "twilio_account_sid", None
            )
            token = getattr(settings, "TWILIO_AUTH_TOKEN", None) or getattr(
                self.site_settings, "twilio_auth_token", None
            )
            if not sid or not token:
                return None
            self._client = Client(sid, token)
            return self._client
        except ImportError:
            logger.warning("Twilio SDK not installed; SMS will fail.")
            return None

    def send(
        self,
        to_phone: str,
        body: str,
        *,
        sender_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SMSResult:
        from_ = (
            sender_id
            or getattr(self.site_settings, "sms_sender_id", None)
            or "RUNMYCAMPUS"
        )
        client = self._get_client()
        if not client:
            return SMSResult(ok=False, error="Twilio not configured")
        try:
            msg = client.messages.create(
                body=body,
                from_=from_,
                to=to_phone,
            )
            logger.info("SMS sent via Twilio: %s", getattr(msg, "sid", None))
            return SMSResult(ok=True, provider_message_id=getattr(msg, "sid", None))
        except _SMS_TWILIO_SEND_ERRORS as e:
            logger.exception("Twilio SMS failed: %s", e)
            return SMSResult(ok=False, error=str(e))
