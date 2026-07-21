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

    provider_key = "twilio"

    def __init__(self, site_settings: Any):
        self.site_settings = site_settings
        self._client = None
        # Distinguishes "operator has not set credentials" from "the twilio
        # wheel is missing from the deployed image". Both fail the send, but
        # only the second one is a deploy defect and it must say so.
        self._last_client_error: str = ""

    def _get_client(self):
        if self._client is not None:
            return self._client
        self._last_client_error = ""
        try:
            from twilio.rest import Client

            sid = getattr(settings, "TWILIO_ACCOUNT_SID", None) or getattr(
                self.site_settings, "twilio_account_sid", None
            )
            token = getattr(settings, "TWILIO_AUTH_TOKEN", None) or getattr(
                self.site_settings, "twilio_auth_token", None
            )
            if not sid or not token:
                self._last_client_error = "twilio_not_configured"
                return None
            self._client = Client(sid, token)
            return self._client
        except ImportError:
            logger.error(
                "Twilio SDK not installed -- SMS cannot be sent. Pin `twilio` in "
                "requirements.txt (build.sh installs that file only).",
                extra={"scope": "sms_twilio.sdk_missing"},
            )
            self._last_client_error = "twilio_sdk_not_installed"
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
            return SMSResult(
                ok=False,
                error=self._last_client_error or "twilio_not_configured",
            )
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
