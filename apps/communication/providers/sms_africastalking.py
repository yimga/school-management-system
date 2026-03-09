"""
AfricasTalking SMS adapter. No direct AfricasTalking usage outside this module.
"""
from __future__ import annotations

import logging
from typing import Any

from .sms_base import SMSProvider, SMSResult

logger = logging.getLogger(__name__)


class AfricasTalkingSMSProvider(SMSProvider):
    """SMS via AfricasTalking API."""

    def __init__(self, site_settings: Any):
        self.site_settings = site_settings

    def send(
        self,
        to_phone: str,
        body: str,
        *,
        sender_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SMSResult:
        api_key = getattr(self.site_settings, "sms_api_key", None)
        if not api_key:
            return SMSResult(ok=False, error="AfricasTalking api_key not set")
        from_ = sender_id or getattr(self.site_settings, "sms_sender_id", None) or "RUNMYCAMPUS"
        try:
            import africastalking
            at = africastalking.SMS(api_key=api_key)
            response = at.send(body, [to_phone], sender_id=from_ or None)
            msg_id = None
            if isinstance(response, dict):
                recipients = response.get("SMSMessageData", {}).get("Recipients") or []
                if recipients:
                    msg_id = recipients[0].get("messageId")
                    ok = (recipients[0].get("status") or "").lower() != "failed"
                else:
                    ok = True
            else:
                ok = True
            logger.info("SMS sent via AfricasTalking: %s", msg_id or response)
            return SMSResult(ok=ok, provider_message_id=msg_id)
        except Exception as e:
            logger.exception("AfricasTalking SMS failed: %s", e)
            return SMSResult(ok=False, error=str(e))
