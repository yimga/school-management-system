"""
Plan VI: WhatsApp and Push notification channels.
Tenants configure credentials in API Center (integration_catalog: whatsapp, push).
Provider abstraction: WhatsAppProvider and PushProvider base classes for pluggable backends.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# FCM signals that mean "this device token is permanently invalid" — the
# device unregistered (app uninstalled / token rotated) or the token is
# malformed. When we see one of these we deactivate the MobileDevice so the
# dead token self-prunes (mirrors the web-push 404/410 deactivation pattern).
# HTTP statuses (HTTP v1 returns 404 NOT_FOUND for an unregistered token; the
# legacy API returned 410 GONE).
_FCM_DEAD_TOKEN_HTTP_STATUSES = frozenset({404, 410})
# FCM v1 canonical error codes (response JSON: error.details[].errorCode, or
# error.status) that indicate the token — not the request — is the problem.
_FCM_DEAD_TOKEN_ERROR_CODES = frozenset({"UNREGISTERED", "INVALID_ARGUMENT"})


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

    from apps.communication.secret_config import decrypt_config

    rec = resolve_active_integration(school, "whatsapp")
    if rec and rec.is_active and rec.config:
        return decrypt_config(rec.config)
    svc = resolve_service_integration(
        school,
        service_type=ServiceIntegration.ServiceType.WHATSAPP,
        name_hints=["whatsapp"],
    )
    if svc and svc.config:
        return decrypt_config(svc.config)
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

    from apps.communication.secret_config import decrypt_config

    rec = resolve_active_integration(school, "push")
    if rec and rec.is_active and rec.config:
        return decrypt_config(rec.config)
    svc = resolve_service_integration(
        school,
        service_type=ServiceIntegration.ServiceType.PUSH,
        name_hints=["push", "fcm"],
    )
    if svc and svc.config:
        return decrypt_config(svc.config)
    return None


def _fcm_v1_access_token(config: dict) -> str:
    """Resolve an OAuth2 bearer token for FCM HTTP v1.

    Order of preference:
      1. A caller-supplied short-lived ``access_token`` in config (the caller
         refreshes it out-of-band).
      2. A service-account JSON (``service_account_json`` / ``service_account``)
         minted into a token via ``google.oauth2.service_account`` when the
         ``google-auth`` library is installed.
    Returns "" when no token can be obtained (caller logs + returns False)."""
    token = (config.get("access_token") or "").strip()
    if token:
        return token
    sa = config.get("service_account_json") or config.get("service_account")
    if not sa:
        return ""
    try:
        import json as _json

        from google.oauth2 import service_account  # type: ignore
        from google.auth.transport.requests import Request as _GRequest  # type: ignore

        info = _json.loads(sa) if isinstance(sa, str) else sa
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )
        creds.refresh(_GRequest())
        return creds.token or ""
    except Exception as exc:  # noqa: BLE001 — missing lib / bad creds → no token
        logger.warning("Push(fcm): v1 token mint failed err_type=%s", type(exc).__name__)
        return ""


def _fcm_response_signals_dead_token(response) -> bool:
    """True when an FCM HTTP v1 error response indicates the *token* is dead.

    Distinguishes "this token is permanently invalid" (deactivate the device)
    from "the send failed for a transient/config reason" (leave the device
    alone). Reads the HTTP status first, then the canonical FCM error code in
    the JSON body (``error.status`` and ``error.details[].errorCode``)."""
    status = getattr(response, "status_code", None)
    if status in _FCM_DEAD_TOKEN_HTTP_STATUSES:
        return True
    try:
        err = (response.json() or {}).get("error") or {}
    except (ValueError, TypeError, AttributeError):
        return False
    if (err.get("status") or "") in _FCM_DEAD_TOKEN_ERROR_CODES:
        return True
    for detail in err.get("details") or []:
        if isinstance(detail, dict):
            code = detail.get("errorCode") or detail.get("error_code") or ""
            if code in _FCM_DEAD_TOKEN_ERROR_CODES:
                return True
    return False


def _send_push_to_token(
    config: dict,
    provider: str,
    device_token: str,
    title: str,
    body: str,
    data: dict | None,
) -> tuple[bool, bool]:
    """Deliver a single push to one device token.

    Returns ``(sent, dead_token)``:
      - ``sent`` True when the provider accepted the message.
      - ``dead_token`` True when the failure proves the token is permanently
        invalid (caller should deactivate the owning device)."""
    if not device_token:
        return (False, False)
    try:
        if provider == "fcm":
            # FCM HTTP v1 (audit H9). The legacy "/fcm/send" + "Authorization:
            # Key" API was shut down by Google in 2024, so all legacy sends
            # silently failed. v1 uses an OAuth2 bearer + per-project endpoint.
            project_id = config.get("project_id") or config.get("fcm_project_id")
            access_token = _fcm_v1_access_token(config)
            if project_id and access_token:
                import requests

                payload_data = {k: str(v) for k, v in (data or {}).items()}
                r = requests.post(
                    f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "message": {
                            "token": device_token,
                            "notification": {"title": title, "body": body},
                            "data": payload_data,
                        }
                    },
                    timeout=10,
                )
                if r.status_code == 200:
                    return (True, False)
                return (False, _fcm_response_signals_dead_token(r))
            # Explicit legacy opt-in only (deprecated; Google-disabled in 2024).
            server_key = config.get("server_key")
            if config.get("allow_legacy_fcm") and server_key:
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
                if r.status_code == 200:
                    return (True, False)
                return (False, r.status_code in _FCM_DEAD_TOKEN_HTTP_STATUSES)
            logger.warning(
                "Push(fcm): missing project_id/access_token for HTTP v1 "
                "(legacy API is disabled by Google)."
            )
            return (False, False)
        if provider == "web_push" or config.get("endpoint_url"):
            url = config.get("endpoint_url")
            if not url:
                return (False, False)
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
            if r.status_code in (200, 201, 204):
                return (True, False)
            return (False, r.status_code in _FCM_DEAD_TOKEN_HTTP_STATUSES)
        logger.warning("Push: unsupported provider %s", provider)
        return (False, False)
    except (OSError, ConnectionError, TimeoutError, ValueError, TypeError) as e:
        logger.exception("Push send failed: %s", e)
        return (False, False)


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

    ``token_or_user`` is either a raw device-token string (delivered directly)
    or a User. For a User we resolve every active registered device from the
    ``MobileDevice`` registry and multicast to all of them. A hard FCM failure
    that proves a token is invalid/expired (HTTP 404/410 or FCM error codes
    UNREGISTERED / INVALID_ARGUMENT) deactivates that device so dead tokens
    self-prune (mirrors the web-push deactivate-on-expiry convention).

    Returns True if the message reached at least one device, False otherwise
    (no integration, no token, no active devices, or every send failed).
    """
    config = _get_push_config(school)
    if not config:
        logger.debug("Push: no integration for school %s", getattr(school, "pk", None))
        return False
    provider = (config.get("provider") or "fcm").lower()

    # Raw-string token path: caller already resolved the token, send directly.
    if isinstance(token_or_user, str):
        if not token_or_user:
            logger.warning("Push: no device token")
            return False
        sent, _dead = _send_push_to_token(
            config, provider, token_or_user, title, body, data
        )
        return sent

    user = token_or_user
    if user is None or not getattr(user, "pk", None):
        logger.warning("Push: no device token")
        return False

    # User path: multicast to every active registered device. The token
    # registry lives in the mobile API; lazy-import it to avoid app-load
    # cycles (matches apps/sync_engine/services.py).
    from apps.api.mobile_api import MobileDevice

    # MobileDevice has no tenant/school FK — it is owned by the User via the
    # `user` FK, so filtering by `user=` is the correct isolation boundary.
    # tenant-isolation-allow: mobile-device-registry-is-user-scoped-no-school-fk
    devices = list(
        MobileDevice.objects.filter(user=user, is_active=True).exclude(push_token="")
    )
    if not devices:
        logger.info(
            "Push: no active devices for user %s (no-op)", getattr(user, "pk", None)
        )
        return False

    sent_count = 0
    for device in devices:
        sent, dead_token = _send_push_to_token(
            config, provider, device.push_token, title, body, data
        )
        if sent:
            sent_count += 1
        elif dead_token:
            device.is_active = False
            device.save(update_fields=["is_active"])
            logger.info(
                "Push: deactivated dead device %s for user %s",
                getattr(device, "device_id", device.pk),
                getattr(user, "pk", None),
            )
    return sent_count > 0
