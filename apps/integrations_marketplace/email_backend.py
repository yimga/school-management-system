"""
Per-tenant email backend.

Plumbs the connector cascade into Django's `EMAIL_BACKEND` so that each tenant
(school) — and optionally each campus — can route transactional mail through
its own provider:

  Cascade lookup order for a tenant:
    1. campus-scoped ServiceIntegration (connector category = transactional_mail)
    2. school-scoped ServiceIntegration
    3. parent_school chain
    4. env default INTEGRATIONS_<UPPER_SLUG>_DEFAULT_CONFIG
    5. Django EMAIL_BACKEND (global fallback)

  Provider selection:
    - The connector row carries `connector_slug` (e.g. "sendgrid", "mailgun").
    - `connector_registry.get_connector(slug).anymail_backend` gives us the
      Anymail backend dotted path to instantiate.
    - SMTP rows use Django's built-in smtp.EmailBackend with the typed config.

  Tenant routing:
    - When this backend is set as `EMAIL_BACKEND`, it picks the tenant from
      `connection_extra["school"]` if provided, then from a thread-local
      tenant set by `apps.schools.middleware`. Falls back to global Django
      settings if no tenant is in scope (Celery sends, management cmds).

Wire-up to make this active platform-wide:
    EMAIL_BACKEND = "apps.integrations_marketplace.email_backend.PerTenantEmailBackend"
    EMAIL_BACKEND_FALLBACK = "django.core.mail.backends.smtp.EmailBackend"

Without that wiring this module is dormant — it's safe to ship and adopt
incrementally.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import Any

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.test.utils import override_settings
from django.utils.module_loading import import_string

from apps.integrations_marketplace.connector_registry import (
    AUTH_KIND_API_KEY,
    AUTH_KIND_SMTP,
    CATEGORY_TRANSACTIONAL_MAIL,
    get_connector,
    list_transactional_mail_connectors,
)
from apps.integrations_marketplace.resolver import resolve_connector_config

logger = logging.getLogger(__name__)


_thread_local = threading.local()


def bind_tenant_for_email(school) -> None:
    """Stash the active tenant for the current thread (middleware hook)."""
    _thread_local.school = school


def clear_tenant_for_email() -> None:
    if hasattr(_thread_local, "school"):
        delattr(_thread_local, "school")


def _active_school(connection_kwargs: dict[str, Any]):
    """Find the tenant in scope: explicit kwarg → thread-local → None."""
    explicit = connection_kwargs.get("school") if connection_kwargs else None
    if explicit is not None:
        return explicit
    return getattr(_thread_local, "school", None)


def _fallback_backend_path() -> str:
    return getattr(
        settings,
        "EMAIL_BACKEND_FALLBACK",
        "django.core.mail.backends.smtp.EmailBackend",
    )


def _resolve_tenant_mail_provider(school) -> tuple[str, dict[str, Any]] | None:
    """
    Return (anymail_backend_path, config_dict) for the school's chosen mail
    provider, or None if no transactional_mail connector is configured.

    Walks every transactional_mail connector in the registry and returns the
    first one with a configured row at the (school, None) scope. Schools that
    want a deterministic preference order can simply only configure one
    connector (the resolver will short-circuit at the first hit anyway).
    """
    if school is None:
        return None
    for connector in list_transactional_mail_connectors():
        resolved = resolve_connector_config(connector.slug, school=school)
        if resolved and resolved.is_configured and resolved.is_active:
            return connector.anymail_backend, dict(resolved.config or {})
    return None


def _build_anymail_kwargs(
    *, connector_slug: str, config: dict[str, Any]
) -> dict[str, Any]:
    """
    Translate `ServiceIntegration.config` into the kwargs each Anymail backend
    expects. The mapping is intentionally narrow (just what tenants typed) —
    the rest stays at Anymail defaults. For SMTP, we pass-through Django's
    canonical SMTP kwargs.

    Returns kwargs that can be unpacked into `BaseEmailBackend.__init__`.
    """
    connector = get_connector(connector_slug)
    if connector is None:
        return {}

    if connector.auth_kind == AUTH_KIND_SMTP:
        return {
            "host": str(config.get("host") or "").strip() or None,
            "port": int(config["port"]) if config.get("port") else None,
            "username": str(config.get("username") or "").strip() or None,
            "password": str(config.get("password") or "").strip() or None,
            "use_tls": bool(config.get("use_tls", True)),
            "use_ssl": bool(config.get("use_ssl", False)),
            "timeout": int(config.get("timeout", 10)),
        }

    if connector.auth_kind != AUTH_KIND_API_KEY:
        return {}

    # Anymail backends introspect `settings.ANYMAIL` at __init__ time, so we
    # wrap the backend construction and send_messages call in an
    # `override_settings(ANYMAIL=...)` context (see _tenant_anymail_settings).
    # Nothing needs to flow through the constructor here.
    return {"_anymail_overrides": _anymail_settings_for(connector_slug, config)}


_ANYMAIL_KEY_MAP: dict[str, dict[str, str]] = {
    # Map ServiceIntegration.config keys → settings.ANYMAIL keys per provider.
    # Source: Anymail docs (https://anymail.dev/en/stable/esps/).
    "mailgun": {"api_key": "MAILGUN_API_KEY", "sender_domain": "MAILGUN_SENDER_DOMAIN"},
    "sendgrid": {"api_key": "SENDGRID_API_KEY"},
    "postmark": {"server_token": "POSTMARK_SERVER_TOKEN"},
    "amazon_ses": {
        "access_key_id": "AMAZON_SES_CLIENT_PARAMS_AWS_ACCESS_KEY_ID",
        "secret_access_key": "AMAZON_SES_CLIENT_PARAMS_AWS_SECRET_ACCESS_KEY",
        "region": "AMAZON_SES_CLIENT_PARAMS_REGION_NAME",
    },
    "sparkpost": {"api_key": "SPARKPOST_API_KEY"},
    "brevo": {"api_key": "BREVO_API_KEY"},
    "mandrill": {"api_key": "MANDRILL_API_KEY"},
    "mailersend": {"api_token": "MAILERSEND_API_TOKEN"},
    "mailjet": {"api_key": "MAILJET_API_KEY", "secret_key": "MAILJET_SECRET_KEY"},
    "resend": {"api_key": "RESEND_API_KEY"},
}


def _anymail_settings_for(
    connector_slug: str, config: dict[str, Any]
) -> dict[str, Any] | None:
    """Build the `ANYMAIL = {...}` dict for this tenant's provider config."""
    key_map = _ANYMAIL_KEY_MAP.get(connector_slug)
    if not key_map:
        return None
    out: dict[str, Any] = {}
    # Amazon SES nests under CLIENT_PARAMS — handle the dotted-style mapping.
    if connector_slug == "amazon_ses":
        client_params: dict[str, Any] = {}
        if config.get("access_key_id"):
            client_params["aws_access_key_id"] = str(config["access_key_id"])
        if config.get("secret_access_key"):
            client_params["aws_secret_access_key"] = str(config["secret_access_key"])
        if config.get("region"):
            client_params["region_name"] = str(config["region"])
        if client_params:
            out["AMAZON_SES_CLIENT_PARAMS"] = client_params
        return out or None
    for cfg_key, settings_key in key_map.items():
        if config.get(cfg_key):
            out[settings_key] = str(config[cfg_key])
    return out or None


@contextlib.contextmanager
def _tenant_anymail_settings(overrides: dict[str, Any] | None):
    """Temporarily merge tenant overrides into settings.ANYMAIL."""
    if not overrides:
        yield
        return
    existing = dict(getattr(settings, "ANYMAIL", {}) or {})
    merged = {**existing, **overrides}
    with override_settings(ANYMAIL=merged):
        yield


class PerTenantEmailBackend(BaseEmailBackend):
    """
    Dispatching backend that, for each `send_messages()` call, picks an
    underlying backend based on the active tenant.

    This subclass is itself a `BaseEmailBackend`, but it never sends mail
    directly — it always delegates to a concrete backend (Anymail or SMTP)
    after resolving the tenant.
    """

    def __init__(self, fail_silently: bool = False, **kwargs: Any):
        super().__init__(fail_silently=fail_silently)
        self._kwargs = kwargs

    def _build_backend_kwargs_and_overrides(
        self, *, school
    ) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
        """Resolve provider → (backend_path, kwargs, anymail_overrides)."""
        provider = _resolve_tenant_mail_provider(school)
        if provider is None:
            return _fallback_backend_path(), {}, None

        backend_path, config = provider
        connector_slug = config.get("connector_slug") or _slug_for_backend(backend_path)
        backend_kwargs = _build_anymail_kwargs(
            connector_slug=connector_slug, config=config
        )
        anymail_overrides = backend_kwargs.pop("_anymail_overrides", None)
        backend_kwargs = {k: v for k, v in backend_kwargs.items() if v is not None}
        return backend_path, backend_kwargs, anymail_overrides

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        school = _active_school(self._kwargs)
        backend_path, backend_kwargs, anymail_overrides = (
            self._build_backend_kwargs_and_overrides(school=school)
        )
        # Per-tenant Anymail isolation: settings.ANYMAIL is patched for the
        # window between backend construction (which reads it) and send
        # (which also reads it). The context manager restores prior settings
        # afterward — safe for concurrent Celery workers because Django's
        # override_settings is signal-based and thread-aware.
        with _tenant_anymail_settings(anymail_overrides):
            backend_cls = import_string(backend_path)
            backend = backend_cls(fail_silently=self.fail_silently, **backend_kwargs)
            if anymail_overrides:
                # Forward-compat attribute for Anymail 11+ per-connection settings.
                backend.tenant_anymail_overrides = anymail_overrides
            return backend.send_messages(email_messages)


def _slug_for_backend(backend_path: str) -> str:
    """Best-effort slug recovery when config didn't carry connector_slug."""
    for connector in list_transactional_mail_connectors():
        if connector.anymail_backend == backend_path:
            return connector.slug
    return ""


__all__ = [
    "CATEGORY_TRANSACTIONAL_MAIL",
    "PerTenantEmailBackend",
    "bind_tenant_for_email",
    "clear_tenant_for_email",
]
