"""
Phase 7 Task 8: Third-Party Integrations (WhatsApp, Zoom, Communication)

§2.4: Broad except replaced with typed exception tuples and structured logging.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from json import JSONDecodeError

from django.conf import settings

logger = logging.getLogger(__name__)

# Typed exception set for external API/HTTP and token/serialization failures (§2.4)
try:
    import requests

    _REQUESTS_ERRORS: tuple[type[BaseException], ...] = (requests.RequestException,)
except ImportError:
    _REQUESTS_ERRORS = ()
_COMMUNICATION_INTEGRATION_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ConnectionError,
    TimeoutError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
    JSONDecodeError,
) + _REQUESTS_ERRORS


class IntegrationService(ABC):
    """Base class for third-party integrations."""

    @abstractmethod
    def send_message(self, recipient, message, **kwargs):
        """Send a message via the integration."""
        pass

    @abstractmethod
    def verify_webhook(self, request):
        """Verify webhook signature."""
        pass

    @abstractmethod
    def check_health(self):
        """Check if service is available."""
        pass


class WhatsAppIntegration(IntegrationService):
    """WhatsApp Business API integration."""

    def __init__(self):
        self.api_token = settings.WHATSAPP_API_TOKEN
        self.api_url = settings.WHATSAPP_API_URL
        self.phone_number = settings.WHATSAPP_BUSINESS_NUMBER

    def send_message(self, recipient, message, template=None, **kwargs):
        """
        Send WhatsApp message.

        Args:
            recipient: Phone number (e.g., "+237123456789")
            message: Message text
            template: Template name (for templated messages)
        """
        try:
            import requests

            if template:
                # Use template message
                payload = {
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "template",
                    "template": {"name": template, "language": {"code": "en_US"}},
                }
            else:
                # Send text message
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient,
                    "type": "text",
                    "text": {"preview_url": True, "body": message},
                }

            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                f"{self.api_url}/messages", json=payload, headers=headers, timeout=10
            )

            if response.status_code in [200, 201]:
                logger.info("WhatsApp message sent to %s", recipient)
                return {
                    "success": True,
                    "message_id": response.json().get("messages")[0]["id"],
                }
            logger.error("WhatsApp send failed: %s", response.text)
            return {"success": False, "error": response.text}

        except _COMMUNICATION_INTEGRATION_ERRORS as e:
            logger.exception(
                "WhatsApp integration error: %s",
                e,
                extra={"recipient": recipient, "integration": "whatsapp"},
            )
            return {"success": False, "error": str(e)}

    def verify_webhook(self, request):
        """Verify a WhatsApp Cloud API webhook delivery.

        Two flows are supported:

        - GET verification handshake: WhatsApp sends ``hub.mode=subscribe`` plus
          ``hub.verify_token`` and expects the verify-token configured in the
          dashboard echoed back. The caller (the view) is responsible for echoing
          ``hub.challenge`` — this method only confirms the token matches.
        - POST event delivery: signed with HMAC-SHA256 of the raw body using the
          *App Secret* from Meta; header ``X-Hub-Signature-256`` is
          ``sha256={hex}``.

        Returns ``True`` only on successful verification. Never logs the
        signature header or app secret.
        """
        import hashlib
        import hmac

        method = (getattr(request, "method", "") or "").upper()
        if method == "GET":
            verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "") or ""
            if not verify_token:
                return False
            mode = (request.GET.get("hub.mode") or "").strip()
            token = (request.GET.get("hub.verify_token") or "").strip()
            if mode != "subscribe":
                return False
            return hmac.compare_digest(token, verify_token)

        app_secret = getattr(settings, "WHATSAPP_APP_SECRET", "") or ""
        if not app_secret:
            return False
        sig_header = (
            request.headers.get("X-Hub-Signature-256")
            if hasattr(request, "headers")
            else None
        ) or request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
        sig_header = (sig_header or "").strip()
        if not sig_header.startswith("sha256="):
            return False
        candidate = sig_header.split("=", 1)[1].strip()
        raw_body = getattr(request, "body", b"") or b""
        expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(candidate.lower(), expected.lower())

    def check_health(self):
        """Check WhatsApp API health."""
        try:
            import requests

            response = requests.get(
                f"{self.api_url}/health",
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=5,
            )
            return response.status_code == 200
        except _COMMUNICATION_INTEGRATION_ERRORS as e:
            logger.debug(
                "WhatsApp health check failed: %s", e, extra={"integration": "whatsapp"}
            )
            return False


class ZoomIntegration(IntegrationService):
    """Zoom meeting integration."""

    def __init__(self):
        self.api_key = settings.ZOOM_API_KEY
        self.api_secret = settings.ZOOM_API_SECRET
        self.api_url = "https://api.zoom.us/v2"

    def get_token(self):
        """Return a short-lived JWT for Zoom API calls (create_meeting, check_health, etc.)."""
        import jwt
        from datetime import datetime, timedelta

        payload = {
            "iss": self.api_key,
            "exp": datetime.utcnow() + timedelta(seconds=60),
        }
        return jwt.encode(payload, self.api_secret, algorithm="HS256")

    def create_meeting(self, host_email, topic, duration=30, **kwargs):
        """Create a Zoom meeting."""
        try:
            import requests

            token = self.get_token()

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Caller may pass an explicit ``timezone`` kwarg (IANA name,
            # e.g. "Africa/Douala"); otherwise fall back to the deployment's
            # configured timezone, then UTC as a last resort.
            meeting_timezone = (
                kwargs.get("timezone")
                or getattr(settings, "TIME_ZONE", None)
                or "UTC"
            )

            # Create meeting
            meeting_data = {
                "topic": topic,
                "type": 2,  # Scheduled meeting
                "duration": duration,
                "timezone": meeting_timezone,
                "settings": {
                    "host_video": True,
                    "participant_video": True,
                    "join_before_host": True,
                    "waiting_room": True,
                },
            }

            response = requests.post(
                f"{self.api_url}/users/{host_email}/meetings",
                json=meeting_data,
                headers=headers,
                timeout=10,
            )

            if response.status_code == 201:
                data = response.json()
                logger.info(f"Zoom meeting created: {data['id']}")
                return {
                    "success": True,
                    "meeting_id": data["id"],
                    "join_url": data["join_url"],
                    "start_time": data.get("start_time"),
                }
            logger.error("Zoom meeting creation failed: %s", response.text)
            return {"success": False, "error": response.text}

        except _COMMUNICATION_INTEGRATION_ERRORS as e:
            logger.exception(
                "Zoom integration error: %s",
                e,
                extra={"host_email": host_email, "topic": topic, "integration": "zoom"},
            )
            return {"success": False, "error": str(e)}

    def send_message(self, recipient, message, **kwargs):
        """Zoom does not support direct messaging; use create_meeting for video. Intentional stub."""
        raise NotImplementedError("Use create_meeting instead")

    def verify_webhook(self, request):
        """Verify a Zoom webhook delivery.

        Zoom signs deliveries with the *Webhook Secret Token* configured in the
        marketplace app:

        - Header ``x-zm-signature`` is ``v0={hex}`` where ``{hex}`` is
          ``hmac_sha256(secret, "v0:{x-zm-request-timestamp}:{raw_body}")``.
        - The timestamp must be within 5 minutes of now.

        Returns ``True`` only on successful verification.
        """
        import hashlib
        import hmac
        import time

        secret = getattr(settings, "ZOOM_WEBHOOK_SECRET_TOKEN", "") or ""
        if not secret:
            return False
        headers = getattr(request, "headers", None)
        if headers is not None:
            sig = (headers.get("x-zm-signature") or headers.get("X-Zm-Signature") or "").strip()
            ts = (headers.get("x-zm-request-timestamp") or headers.get("X-Zm-Request-Timestamp") or "").strip()
        else:
            sig = (request.META.get("HTTP_X_ZM_SIGNATURE") or "").strip()
            ts = (request.META.get("HTTP_X_ZM_REQUEST_TIMESTAMP") or "").strip()
        if not sig or not ts:
            return False
        try:
            ts_int = int(ts)
        except (TypeError, ValueError):
            return False
        if abs(int(time.time()) - ts_int) > 300:
            return False
        if not sig.startswith("v0="):
            return False
        candidate = sig.split("=", 1)[1].strip()
        raw_body = getattr(request, "body", b"") or b""
        msg = f"v0:{ts}:".encode("utf-8") + raw_body
        expected = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(candidate.lower(), expected.lower())

    def check_health(self):
        """Check Zoom API health."""
        try:
            import requests

            response = requests.get(
                f"{self.api_url}/users/me",
                headers={"Authorization": f"Bearer {self.get_token()}"},
                timeout=5,
            )
            return response.status_code == 200
        except _COMMUNICATION_INTEGRATION_ERRORS as e:
            logger.debug(
                "Zoom health check failed: %s", e, extra={"integration": "zoom"}
            )
            return False


class CommunicationService:
    """Central service for managing all communications."""

    def __init__(self):
        self.whatsapp = WhatsAppIntegration()
        self.zoom = ZoomIntegration()
        self.providers = {
            "whatsapp": self.whatsapp,
            "zoom": self.zoom,
        }

    def send_message(self, provider, recipient, message, **kwargs):
        """Send message through specified provider."""
        if provider not in self.providers:
            return {"success": False, "error": f"Unknown provider: {provider}"}

        return self.providers[provider].send_message(recipient, message, **kwargs)

    def check_all_health(self):
        """Check health of all integrations."""
        results = {}
        for name, service in self.providers.items():
            try:
                results[name] = service.check_health()
            except _COMMUNICATION_INTEGRATION_ERRORS as e:
                logger.debug(
                    "Communication provider health check failed: %s",
                    e,
                    extra={"provider": name},
                )
                results[name] = False
        return results


# Singleton instance
_communication_service = None


def get_communication_service():
    """Get singleton communication service."""
    global _communication_service
    if _communication_service is None:
        _communication_service = CommunicationService()
    return _communication_service
