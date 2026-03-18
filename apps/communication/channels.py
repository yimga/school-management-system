"""
Plan VI: WhatsApp and Push notification channels.
Tenants configure credentials in API Center (integration_catalog: whatsapp, push).
Provider abstraction: WhatsAppProvider and PushProvider base classes for pluggable backends.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class WhatsAppProvider(ABC):
    """Abstract base for WhatsApp Business API backends (Meta, Twilio, etc.)."""

    @abstractmethod
    def send(
        self,
        to_phone: str,
        body: str,
        *,
        template_name: str | None = None,
        template_params: list[str] | None = None,
    ) -> bool:
        """Send message; return True if sent or queued."""
        pass

    def health_check(self) -> bool:
        """Optional: verify credentials/connectivity."""
        return True


class PushProvider(ABC):
    """Abstract base for push backends (FCM, WebPush, APNS)."""

    @abstractmethod
    def send(
        self, token: str, title: str, body: str, *, data: dict | None = None
    ) -> bool:
        """Send to one device token; return True if sent."""
        pass

    def health_check(self) -> bool:
        """Optional: verify credentials."""
        return True


def _get_whatsapp_config(school) -> dict | None:
    from apps.siteconfig.integration_registry import (
        resolve_active_integration,
        resolve_service_integration,
    )
    from apps.integrations_marketplace.models import ServiceIntegration

    rec = resolve_active_integration(school, "whatsapp")
    if rec and rec.is_active and rec.config:
        return rec.config
    svc = resolve_service_integration(
        school,
        service_type=ServiceIntegration.ServiceType.WHATSAPP,
        name_hints=["whatsapp"],
    )
    if svc and svc.config:
        return svc.config
    return None


def send_whatsapp(
    school,
    to_phone: str,
    *,
    template_name: str | None = None,
    template_params: list[str] | None = None,
    body: str | None = None,
) -> bool:
    """
    Send WhatsApp message via tenant-configured WhatsApp Business API.
    Either template_name + template_params (approved template) or body (session message).
    Returns True if sent (or queued), False if no integration or failed.
    """
    config = _get_whatsapp_config(school)
    if not config:
        logger.debug(
            "WhatsApp: no integration for school %s", getattr(school, "pk", None)
        )
        return False
    phone_number_id = config.get("phone_number_id")
    access_token = config.get("access_token")
    if not phone_number_id or not access_token:
        logger.warning(
            "WhatsApp: missing phone_number_id or access_token for school %s",
            getattr(school, "pk", None),
        )
        return False
    to_phone = (to_phone or "").strip().replace(" ", "")
    if not to_phone.startswith("+"):
        to_phone = "+" + to_phone
    try:
        import requests

        url = f"https://graph.facebook.com/{(config.get('api_version') or 'v18.0')}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        if template_name and template_params is not None:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone[1:],
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": "en"},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": p} for p in template_params
                            ],
                        }
                    ],
                },
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone[1:],
                "type": "text",
                "text": {"body": (body or "")[:4096]},
            }
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code in (200, 201):
            return True
        logger.warning("WhatsApp API error %s: %s", r.status_code, r.text[:500])
        return False
    except (requests.RequestException, OSError, ValueError, TypeError) as e:
        logger.exception("WhatsApp send failed: %s", e)
        return False


def _get_push_config(school) -> dict | None:
    from apps.siteconfig.integration_registry import (
        resolve_active_integration,
        resolve_service_integration,
    )
    from apps.integrations_marketplace.models import ServiceIntegration

    rec = resolve_active_integration(school, "push")
    if rec and rec.is_active and rec.config:
        return rec.config
    svc = resolve_service_integration(
        school,
        service_type=ServiceIntegration.ServiceType.PUSH,
        name_hints=["push", "fcm"],
    )
    if svc and svc.config:
        return svc.config
    return None


def send_push(
    school,
    token_or_user,
    title: str,
    body: str,
    *,
    data: dict | None = None,
) -> bool:
    """
    Send push notification via tenant-configured FCM/APNS or webhook.
    token_or_user: FCM device token (str) or User (we look up device token from a hypothetical PushDevice model or config).
    Returns True if sent, False if no integration or failed.
    """
    config = _get_push_config(school)
    if not config:
        logger.debug("Push: no integration for school %s", getattr(school, "pk", None))
        return False
    provider = (config.get("provider") or "fcm").lower()
    device_token = (
        token_or_user
        if isinstance(token_or_user, str)
        else getattr(token_or_user, "fcm_token", None)
        or getattr(token_or_user, "device_token", None)
    )
    if not device_token:
        logger.warning("Push: no device token")
        return False
    try:
        if provider == "fcm":
            server_key = config.get("server_key")
            if not server_key:
                return False
            import requests

            r = requests.post(
                "https://fcm.googleapis.com/fcm/send",
                headers={
                    "Authorization": f"Key {server_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "to": device_token,
                    "notification": {"title": title, "body": body},
                    "data": data or {},
                },
                timeout=10,
            )
            return r.status_code == 200
        if provider == "web_push" or config.get("endpoint_url"):
            url = config.get("endpoint_url")
            if not url:
                return False
            import requests

            r = requests.post(
                url,
                json={
                    "to": device_token,
                    "title": title,
                    "body": body,
                    "data": data or {},
                },
                timeout=10,
            )
            return r.status_code in (200, 201, 204)
        logger.warning("Push: unsupported provider %s", provider)
        return False
    except (OSError, ConnectionError, TimeoutError, ValueError, TypeError) as e:
        logger.exception("Push send failed: %s", e)
        return False
