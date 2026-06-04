"""v3.57.x Wave 8 Agent C — Canonical email delivery surface.

Thin, additive reliability + observability layer in front of Django's
``django.core.mail``. Public API:

  * :func:`send_transactional` — verification, password reset,
    low-balance — retried, logged to :class:`EmailDeliveryEvent`,
    never raises.
  * :func:`send_bulk` — digest, newsletter — Celery-queued when
    available, synchronous fallback. Same logging contract.
  * :func:`smtp_probe` — synchronous "can we talk to SMTP" health
    check for the operator dashboard.
  * :func:`get_resolved_smtp_config` — merges env defaults + the
    operator-published ``SiteSettings.email_delivery`` override; SOT
    for the operator dashboard panel.
  * :func:`get_recent_delivery_stats` — aggregates the last N hours
    of :class:`EmailDeliveryEvent` rows for the health card.

Design contract
---------------

  * **Never crashes the caller.** ``fail_silently=True`` semantics
    are preserved: the existing signup-email callsite already wraps
    in a broad ``try/except``; this module mirrors that. On every
    permanent failure we log + persist an ``EmailDeliveryEvent`` row
    with ``ok=False`` and a coarse ``error_kind``, and return
    ``{"ok": False, ...}``. We do NOT raise.
  * **Retries on transient SMTP errors.** Backoff sequence configurable
    via ``settings.SCHOOLOPS_EMAIL_DELIVERY_RETRY_BACKOFF`` (default
    ``[1, 5, 30]`` seconds → 3 attempts total). Sleeps are
    ``time.sleep`` — fine for transactional sends, which are
    request-coupled but already exception-isolated.
  * **PII safety.** We hash the recipient (``sha256(to)[:12]``) for
    log + DB persistence. We never log the raw ``to``, ``from_email``,
    ``password``, or message body. Subjects are truncated to 64 chars
    before persistence; callers are encouraged to keep them PII-free.
  * **DKIM-friendly headers.** ``Message-ID`` is generated explicitly
    (``email.utils.make_msgid``) and ``Date`` is set via
    ``email.utils.formatdate(localtime=True)``. Some MTAs reject mail
    that omits these — Django sets them, but only when constructing
    via ``EmailMessage``, and the explicit set documents intent.

What is NOT in scope here
-------------------------

  * SPF/DKIM/DMARC record management — documented in
    ``docs/EMAIL_DELIVERABILITY.md`` (separate wave).
  * Bounce-rate tracking from DSN parsing or external services —
    requires an inbound mail listener or a 3rd-party API hookup.
  * Per-tenant or per-recipient rate-limiting — future wave.
"""
from __future__ import annotations

import base64
import datetime as _dt
import email.utils as _email_utils
import hashlib
import json
import logging
import re
import smtplib
import socket
import threading
import time
from typing import Any, Iterable, Optional, Union

from django.conf import settings
from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Constants — tunable via settings.
# ──────────────────────────────────────────────────────────────────────


_DEFAULT_BACKOFF_SECONDS = (1, 5, 30)
_DEFAULT_SMTP_PROBE_TIMEOUT = 5.0
_DEFAULT_CONNECTION_TIMEOUT = 10
# v3.58.x Wave 9 Agent K — when send_transactional is called from inside an
# HTTP request (sync path), we cap any single SMTP attempt's socket timeout
# at 5s so a hung SMTP server can never block the request lifecycle for the
# full EMAIL_TIMEOUT value.
_SYNC_PER_ATTEMPT_TIMEOUT_CEILING = 5
_DEFAULT_SYNC_BUDGET_SECONDS = 8
_SUBJECT_PREFIX_MAX = 64
_TO_HASH_LEN = 12

# Coarse error-kind labels persisted to EmailDeliveryEvent.error_kind.
_ERR_SMTP = "smtp_exception"
_ERR_OS = "os_error"
_ERR_CONN = "connection_error"
_ERR_VALUE = "value_error"
_ERR_RATE_LIMIT = "rate_limit_exceeded"
_ERR_SUPPRESSED = "suppressed"
_ERR_HEADER_INJECTION = "header_injection"
_ERR_OTHER = "other"
# Marker sentinel for the synchronous "queued" row written before an async
# dispatch (audit finding C2). A dropped daemon thread / un-drained Celery
# task therefore leaves a visible row instead of vanishing silently.
_ERR_QUEUED = "queued"

# v3.58.x Wave 9 Agent M — bounce taxonomy labels persisted to
# EmailDeliveryEvent.bounce_kind. Send-time labels prefix-free; webhook-
# reported bounces use the ``provider_<type>`` namespace (see
# views_email_webhook.EmailProviderWebhookView).
_BOUNCE_HARD_5XX = "hard_5xx"
_BOUNCE_SOFT_4XX = "soft_4xx"
_BOUNCE_SENDER_REFUSED = "senderrefused"
_BOUNCE_RECIPIENTS_REFUSED = "recipientsrefused"
_BOUNCE_UNKNOWN = "unknown"

# Per-tenant sliding-window rate-limit budget. Default cap is overridable
# via settings.SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP.
_DEFAULT_TENANT_HOURLY_CAP = 200
# In-memory bucket — module-global thread-safe sliding window. Keyed by
# tenant_hash; value is a list[float] of monotonic timestamps within the
# last 3600s. NEVER persists across process restarts — that's fine, the
# cap is a soft guard against runaway loops, not a billing-grade meter.
_RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_WINDOW_SECONDS = 3600

# Subjects can contain free-form text; before we persist the prefix we
# strip anything email-shaped just in case a caller put a recipient in
# the subject. Conservative regex — local-part + @ + dot-domain.
_EMAIL_SHAPED_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


# ──────────────────────────────────────────────────────────────────────
# Public dataclass-shaped return values are plain dicts (JSON-friendly).
# ──────────────────────────────────────────────────────────────────────


def _get_backoff() -> tuple[int, ...]:
    """Return the configured retry backoff in seconds."""
    raw = getattr(settings, "SCHOOLOPS_EMAIL_DELIVERY_RETRY_BACKOFF", None)
    if not raw:
        return tuple(_DEFAULT_BACKOFF_SECONDS)
    try:
        return tuple(int(x) for x in raw if int(x) >= 0)
    except (TypeError, ValueError):
        logger.warning(
            "schoolops.email_delivery.retry_backoff_misconfigured "
            "falling_back_to_default"
        )
        return tuple(_DEFAULT_BACKOFF_SECONDS)


def _hash_recipient(addr: str) -> str:
    """sha256(addr.lower())[:_TO_HASH_LEN] — stable per recipient."""
    if not addr:
        return "00000000" + "0" * (_TO_HASH_LEN - 8)
    norm = addr.strip().lower().encode("utf-8")
    return hashlib.sha256(norm).hexdigest()[:_TO_HASH_LEN]


def _redact_subject_for_log(subject: str) -> str:
    """Truncate + strip email-shaped strings from a subject snapshot."""
    if not subject:
        return ""
    redacted = _EMAIL_SHAPED_RE.sub("[email-redacted]", subject)
    return redacted[:_SUBJECT_PREFIX_MAX]


def _coerce_to_list(addrs: Union[str, Iterable[str]]) -> list[str]:
    """Coerce a single addr or iterable of addrs to a clean list[str]."""
    if addrs is None:
        return []
    if isinstance(addrs, str):
        return [addrs]
    out = []
    for a in addrs:
        if isinstance(a, str) and a.strip():
            out.append(a.strip())
    return out


def _strip_header_value(value: str) -> str:
    """Remove CR/LF (and surrounding whitespace) from a header value.

    Defense-in-depth against header / SMTP-command injection (audit finding,
    P2). Django's ``forbid_multi_line_headers`` raises on most of this at send
    time, but we sanitise caller-supplied headers / From / Reply-To *before*
    constructing the message so a crafted ``School.name`` or custom header can
    never smuggle a second header (e.g. an injected ``Bcc:``).
    """
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _has_crlf(value: Any) -> bool:
    """True if a string contains a CR or LF (raw injection attempt)."""
    return isinstance(value, str) and ("\r" in value or "\n" in value)


def _message_id_prefix(message_id: str) -> str:
    """Return the correlation prefix for a Message-ID header value.

    ``email.utils.make_msgid`` returns ``<local@domain>``; providers report
    the bounce with or without brackets and sometimes only the local-part.
    We persist the local-part (brackets + domain stripped) so the inbound
    bounce webhook can match deterministically. Returns "" on empty input.
    """
    if not message_id:
        return ""
    cleaned = str(message_id).strip().lstrip("<").rstrip(">").strip()
    if "@" in cleaned:
        cleaned = cleaned.split("@", 1)[0]
    return cleaned.strip()[:64]


def _coerce_to_int(value: Any, default: int) -> int:
    """Coerce a value to int, returning default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_to_bool(value: Any, default: bool = False) -> bool:
    """Coerce truthy strings ('true', '1', 'yes') / bools to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return default


# ──────────────────────────────────────────────────────────────────────
# Config resolution.
# ──────────────────────────────────────────────────────────────────────


def _decrypt_password_b64(encrypted_b64: str) -> str:
    """Decrypt the Fernet-wrapped password from its base64 storage form.

    Returns plaintext on success, "" on any failure (never raises into
    the send hot path — a bad password just means SMTP auth fails,
    which the retry path already handles).
    """
    if not encrypted_b64:
        return ""
    try:
        from apps.accounts.legacy_hashes.encryption import _get_fernet

        token = encrypted_b64.encode("utf-8")
        # The stored value IS the Fernet token (already url-safe-base64);
        # the "b64" suffix in the field name is documentary only.
        plaintext = _get_fernet().decrypt(token).decode("utf-8")
        return plaintext
    except Exception as exc:  # broad-by-design — never break the hot path
        logger.warning(
            "schoolops.email_delivery.password_decrypt_failed err_type=%s",
            type(exc).__name__,
        )
        return ""


_ALLOWED_SMTP_PORTS = frozenset({25, 465, 587, 2525})


def _is_safe_smtp_host(host: str, port: int) -> bool:
    """Reject tenant-supplied SMTP targets that point at private/internal hosts.

    SSRF guard (audit P2-low): a tenant BYO-SMTP override can set host/port,
    and the platform would otherwise open a connection (with platform
    credentials in the From header) to anything — including internal hosts
    (port scan / SSRF) or an open relay. We block private / loopback / link-
    local / reserved ranges and constrain the port to known SMTP ports.
    Operators can widen via ``settings.SCHOOLOPS_EMAIL_SMTP_HOST_ALLOWLIST``.
    """
    import ipaddress
    import socket as _socket

    h = (host or "").strip().lower()
    if not h:
        return False
    if int(port or 0) not in _ALLOWED_SMTP_PORTS:
        logger.warning(
            "schoolops.email_delivery.tenant_smtp_port_rejected port=%s", port,
        )
        return False
    allowlist = getattr(settings, "SCHOOLOPS_EMAIL_SMTP_HOST_ALLOWLIST", None) or []
    if h in {str(a).strip().lower() for a in allowlist}:
        return True
    # Resolve and check every returned address against blocked ranges.
    try:
        infos = _socket.getaddrinfo(h, int(port), proto=_socket.IPPROTO_TCP)
    except Exception:  # noqa: BLE001 — DNS failure → treat as unsafe
        logger.warning("schoolops.email_delivery.tenant_smtp_dns_failed")
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            logger.warning(
                "schoolops.email_delivery.tenant_smtp_blocked_range",
            )
            return False
    return True


def get_resolved_smtp_config(*, school=None) -> dict:
    """Return the resolved SMTP config dict.

    Cascade (SODP batch 1407): tenant ``School.settings["email_delivery"]``
    when enabled and allowed → operator ``SiteSettings.email_delivery`` → env.

    Returned dict is safe to render EXCEPT ``host_password`` (never serialize).

    Keys::

        {
          "host": str,
          "port": int,
          "use_tls": bool,
          "host_user": str,
          "host_password": str,        # plaintext — NEVER render
          "default_from_email": str,
          "default_from_name": str,
          "default_reply_to": str,
          "connection_timeout_seconds": int,
          "source": "env" | "site_settings_override" | "tenant_school_settings",
          "enabled": bool,
        }
    """
    env_cfg = {
        "host": getattr(settings, "EMAIL_HOST", "") or "",
        "port": _coerce_to_int(getattr(settings, "EMAIL_PORT", 587), 587),
        "use_tls": _coerce_to_bool(
            getattr(settings, "EMAIL_USE_TLS", True), True,
        ),
        "host_user": getattr(settings, "EMAIL_HOST_USER", "") or "",
        "host_password": getattr(settings, "EMAIL_HOST_PASSWORD", "") or "",
        "default_from_email": (
            getattr(settings, "DEFAULT_FROM_EMAIL", "")
            or "noreply@runmycampus.com"
        ),
        "default_from_name": "",
        "default_reply_to": "",
        "connection_timeout_seconds": _coerce_to_int(
            getattr(settings, "EMAIL_TIMEOUT", _DEFAULT_CONNECTION_TIMEOUT),
            _DEFAULT_CONNECTION_TIMEOUT,
        ),
        "source": "env",
        "enabled": True,
    }

    tenant_cfg = _load_tenant_school_override(school)
    if tenant_cfg:
        return tenant_cfg

    override = _load_site_settings_override()
    if not override or not _coerce_to_bool(override.get("enabled"), False):
        return env_cfg

    merged = dict(env_cfg)
    merged["host"] = override.get("host") or env_cfg["host"]
    merged["port"] = _coerce_to_int(override.get("port"), env_cfg["port"])
    merged["use_tls"] = _coerce_to_bool(
        override.get("use_tls"), env_cfg["use_tls"],
    )
    merged["host_user"] = override.get("host_user") or env_cfg["host_user"]
    pwd_b64 = override.get("host_password_encrypted_b64") or ""
    if pwd_b64:
        merged["host_password"] = _decrypt_password_b64(pwd_b64)
    merged["default_from_email"] = (
        override.get("default_from_email") or env_cfg["default_from_email"]
    )
    merged["default_from_name"] = override.get("default_from_name") or ""
    merged["default_reply_to"] = override.get("default_reply_to") or ""
    merged["connection_timeout_seconds"] = _coerce_to_int(
        override.get("connection_timeout_seconds"),
        env_cfg["connection_timeout_seconds"],
    )
    merged["source"] = "site_settings_override"
    merged["enabled"] = True
    return merged


def _load_tenant_school_override(school) -> dict | None:
    """Tenant BYO-SMTP from ``School.settings['email_delivery']`` when enabled."""
    if school is None:
        return None
    try:
        from apps.schools.email_delivery_settings import (
            get_email_delivery_payload,
            tenant_email_override_allowed,
        )
        from apps.platform_runtime.helpers import get_platform_site_settings_record

        # tenant-isolation-allow: platform-email-policy-row-no-tenant-scope
        site_row = get_platform_site_settings_record(create=False)
        if site_row is not None and not tenant_email_override_allowed(site_row):
            return None
        payload = get_email_delivery_payload(school)
        if not payload.get("enabled"):
            return None
        settings_json = getattr(school, "settings", None) or {}
        raw = settings_json.get("email_delivery") if isinstance(settings_json, dict) else {}
        if not isinstance(raw, dict):
            return None
        env_cfg = {
            "host": getattr(settings, "EMAIL_HOST", "") or "",
            "port": _coerce_to_int(getattr(settings, "EMAIL_PORT", 587), 587),
            "use_tls": _coerce_to_bool(getattr(settings, "EMAIL_USE_TLS", True), True),
            "host_user": getattr(settings, "EMAIL_HOST_USER", "") or "",
            "host_password": getattr(settings, "EMAIL_HOST_PASSWORD", "") or "",
            "default_from_email": (
                getattr(settings, "DEFAULT_FROM_EMAIL", "") or "noreply@runmycampus.com"
            ),
            "default_from_name": "",
            "default_reply_to": "",
            "connection_timeout_seconds": _coerce_to_int(
                getattr(settings, "EMAIL_TIMEOUT", _DEFAULT_CONNECTION_TIMEOUT),
                _DEFAULT_CONNECTION_TIMEOUT,
            ),
            "source": "tenant_school_settings",
            "enabled": True,
        }
        merged = dict(env_cfg)
        merged["host"] = raw.get("host") or env_cfg["host"]
        merged["port"] = _coerce_to_int(raw.get("port"), env_cfg["port"])
        # SSRF guard (audit P2): if the tenant set a custom host, validate it
        # against private/internal ranges + allowed ports before we ever
        # connect with platform credentials. On rejection, fall back to the
        # platform env SMTP (ignore the unsafe override) rather than failing.
        if raw.get("host") and not _is_safe_smtp_host(merged["host"], merged["port"]):
            logger.warning(
                "schoolops.email_delivery.tenant_smtp_override_rejected_unsafe_host"
            )
            return None
        merged["use_tls"] = _coerce_to_bool(raw.get("use_tls"), env_cfg["use_tls"])
        merged["host_user"] = raw.get("host_user") or env_cfg["host_user"]
        pwd_b64 = raw.get("host_password_encrypted_b64") or ""
        if pwd_b64:
            merged["host_password"] = _decrypt_password_b64(pwd_b64)
        merged["default_from_email"] = raw.get("default_from_email") or env_cfg["default_from_email"]
        merged["default_from_name"] = raw.get("default_from_name") or ""
        merged["default_reply_to"] = raw.get("default_reply_to") or ""
        merged["connection_timeout_seconds"] = _coerce_to_int(
            raw.get("connection_timeout_seconds"),
            env_cfg["connection_timeout_seconds"],
        )
        return merged
    except Exception as exc:  # broad-by-design — never break the hot path
        logger.warning(
            "schoolops.email_delivery.tenant_override_load_failed err_type=%s",
            type(exc).__name__,
        )
        return None


def _load_site_settings_override() -> dict:
    """Read ``SiteSettings.email_delivery`` defensively. Returns {} on any error."""
    try:
        from apps.platform_runtime.helpers import get_platform_site_settings_record

        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        row = get_platform_site_settings_record(create=False)
        if row is None:
            return {}
        payload = getattr(row, "email_delivery", None)
        if isinstance(payload, dict):
            return payload
        return {}
    except Exception as exc:  # broad-by-design — never break the hot path
        logger.warning(
            "schoolops.email_delivery.site_settings_load_failed err_type=%s",
            type(exc).__name__,
        )
        return {}


def _build_from_header(cfg: dict, override_from: Optional[str]) -> str:
    """Return the assembled From header (RFC 5322).

    Override wins; otherwise use ``default_from_name <default_from_email>``.
    """
    if override_from:
        return override_from
    email_addr = cfg.get("default_from_email") or "noreply@runmycampus.com"
    name = (cfg.get("default_from_name") or "").strip()
    if name:
        return _email_utils.formataddr((name, email_addr))
    return email_addr


# ──────────────────────────────────────────────────────────────────────
# Connection management.
# ──────────────────────────────────────────────────────────────────────


def _get_connection_for_send(cfg: dict):
    """Return a django.core.mail connection seeded with the resolved config.

    Uses ``mail.get_connection`` so the active ``EMAIL_BACKEND`` is
    honored (console in dev, SMTP in prod, locmem in tests).
    """
    return mail.get_connection(
        backend=getattr(settings, "EMAIL_BACKEND", None),
        host=cfg.get("host") or None,
        port=cfg.get("port") or None,
        username=cfg.get("host_user") or None,
        password=cfg.get("host_password") or None,
        use_tls=cfg.get("use_tls"),
        timeout=cfg.get("connection_timeout_seconds") or None,
        fail_silently=False,
    )


# ──────────────────────────────────────────────────────────────────────
# Persistence helper.
# ──────────────────────────────────────────────────────────────────────


def _find_idempotent_delivery_event(idempotency_key: str) -> Optional[str]:
    """Return existing event UUID when the same idempotency key was already sent."""
    key = (idempotency_key or "").strip()[:128]
    if not key:
        return None
    try:
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        row = (
            EmailDeliveryEvent.objects.filter(idempotency_key=key)
            .order_by("-created_at")
            .only("pk")
            .first()
        )
        return str(row.pk) if row else None
    except Exception:
        return None


def _persist_event(
    *,
    to_hash: str,
    subject_prefix: str,
    priority: str,
    attempts: int,
    ok: bool,
    error_kind: str,
    bounced: bool = False,
    bounce_kind: str = "",
    idempotency_key: str = "",
    message_id_prefix: str = "",
) -> Optional[str]:
    """Best-effort write of an EmailDeliveryEvent row. Returns its UUID str.

    v3.58.x Wave 9 Agent M extends the contract with two optional kwargs:
    ``bounced`` and ``bounce_kind``. When the SMTP send raised an
    SMTPSenderRefused / SMTPRecipientsRefused / 5xx, the caller passes
    ``bounced=True`` so the row is bookmarked as a bounce at send time.
    Provider-webhook-reported bounces use the dedicated UPDATE path in
    :mod:`apps.schoolops.views_email_webhook` rather than this writer.
    """
    try:
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        row = EmailDeliveryEvent.objects.create(
            to_hash=to_hash,
            subject_prefix=subject_prefix,
            priority=priority,
            attempts=attempts,
            ok=ok,
            error_kind=error_kind,
            bounced=bool(bounced),
            bounce_kind=(bounce_kind or "")[:32],
            idempotency_key=(idempotency_key or "")[:128],
            message_id_prefix=(message_id_prefix or "")[:64],
        )
        return str(row.pk)
    except Exception as exc:  # broad-by-design — log persistence is never load-bearing
        logger.warning(
            "schoolops.email_delivery.persist_event_failed err_type=%s",
            type(exc).__name__,
        )
        return None


# ──────────────────────────────────────────────────────────────────────
# v3.58.x Wave 9 Agent M — bounce classification + per-tenant rate limit.
# ──────────────────────────────────────────────────────────────────────


def _classify_bounce(exc: BaseException) -> str:
    """Return a coarse bounce-kind label for an SMTP exception, or ``""``.

    Only SMTPSenderRefused / SMTPRecipientsRefused / 5xx-coded
    SMTPResponseException are treated as bounces. Generic connection /
    socket / TLS issues are retry-eligible failures, NOT bounces — they
    return ``""`` (caller leaves ``bounced=False``).
    """
    # Conservative isinstance checks — sklearn-style ordering: most-
    # specific first.
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return _BOUNCE_SENDER_REFUSED
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return _BOUNCE_RECIPIENTS_REFUSED
    if isinstance(exc, smtplib.SMTPResponseException):
        try:
            code = int(getattr(exc, "smtp_code", 0) or 0)
        except (TypeError, ValueError):
            code = 0
        if 500 <= code <= 599:
            return _BOUNCE_HARD_5XX
        if 400 <= code <= 499:
            return _BOUNCE_SOFT_4XX
        return _BOUNCE_UNKNOWN
    return ""


def _resolve_tenant_hourly_cap() -> int:
    """Resolve ``settings.SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP``.

    Returns the default when the setting is missing or non-positive.
    """
    raw = getattr(
        settings, "SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP", None,
    )
    try:
        val = int(raw) if raw is not None else _DEFAULT_TENANT_HOURLY_CAP
    except (TypeError, ValueError):
        return _DEFAULT_TENANT_HOURLY_CAP
    if val <= 0:
        return _DEFAULT_TENANT_HOURLY_CAP
    return val


def _check_per_tenant_rate_limit(
    tenant_hash: str,
    limit_per_hour: int = _DEFAULT_TENANT_HOURLY_CAP,
) -> bool:
    """Return True when within budget; False when the tenant exceeded.

    Sliding window: the bucket holds monotonic timestamps from the last
    3600 seconds. On every call we prune entries older than the window
    boundary, then compare ``len(bucket)`` to ``limit_per_hour``. When
    over the budget we DO NOT append (the rejected attempt should not
    eat budget); when under the budget we append then return True.

    The bucket lives in process memory — gunicorn workers each see their
    own slice. That is intentional: per-worker visibility keeps the
    hot-path lock-free except for the bucket itself, and the cap is a
    safety guard for runaway loops (signup spam, broken Celery task,
    template regression), not a billing-grade meter.
    """
    if not tenant_hash:
        # Caller didn't (or couldn't) derive a tenant hash — skip the
        # limit. The caller may still pass ``tenant_hash=None`` from
        # platform-level sends (operator test email, no SchoolEntity).
        return True

    # Shared (cross-worker) fixed-window counter via the cache (Redis in prod)
    # so the cap is real across gunicorn workers, not per-process (audit P2).
    # Falls back to the in-memory sliding window below on any cache trouble.
    cap = max(1, int(limit_per_hour))
    try:
        from django.core.cache import cache

        window = int(time.time()) // _RATE_LIMIT_WINDOW_SECONDS
        key = f"em:rl:{tenant_hash}:{window}"
        # add() seeds the counter+TTL atomically; incr() bumps it.
        if cache.add(key, 1, _RATE_LIMIT_WINDOW_SECONDS):
            return True
        try:
            current = cache.incr(key)
        except ValueError:
            # Key expired between add() and incr(); re-seed.
            cache.add(key, 1, _RATE_LIMIT_WINDOW_SECONDS)
            return True
        return current <= cap
    except Exception:  # noqa: BLE001 — cache down → fall back to in-memory
        pass

    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    cap = max(1, int(limit_per_hour))
    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_BUCKETS.get(tenant_hash, [])
        # Prune in place — list is small (≤cap), linear scan is fine.
        bucket = [t for t in bucket if t > cutoff]
        if len(bucket) >= cap:
            _RATE_LIMIT_BUCKETS[tenant_hash] = bucket
            return False
        bucket.append(now)
        _RATE_LIMIT_BUCKETS[tenant_hash] = bucket
    return True


def _hash_tenant(tenant_id: Optional[str]) -> str:
    """sha256(tenant_id.lower())[:_TO_HASH_LEN] — stable per tenant.

    Mirrors :func:`_hash_recipient` so a bucket key is never the raw
    ``school.slug`` (logs would expose tenant identity).
    """
    if not tenant_id:
        return ""
    norm = str(tenant_id).strip().lower().encode("utf-8")
    return hashlib.sha256(norm).hexdigest()[:_TO_HASH_LEN]


# ──────────────────────────────────────────────────────────────────────
# Suppression list (audit finding H3) — bounce/complaint/unsubscribe.
# ──────────────────────────────────────────────────────────────────────


def is_recipient_suppressed(to: str) -> bool:
    """True when the address is on the active suppression list.

    Hashed-key lookup (``to_hash`` = sha256[:12]); never reads the raw
    address. Best-effort — returns False on any error so a transient DB
    blip never blocks legitimate mail (fail-open is correct here: the
    cost of a missed suppression is one extra send, not a lockout).
    """
    addr = (to or "").strip()
    if not addr:
        return False
    try:
        from apps.schoolops.models_email_suppression import SuppressedRecipient

        to_hash = _hash_recipient(addr)
        # Only address-is-undeliverable / complained / operator-blocked reasons
        # gate transactional mail. A *marketing* unsubscribe must NEVER block
        # transactional sends (password reset, invoices) — that opt-out is
        # enforced separately by the email-matrix ``is_unsubscribed`` gate.
        _blocking = ("hard_bounce", "complaint", "manual")
        # tenant-isolation-allow: platform-email-suppression-no-tenant-scope
        return SuppressedRecipient.objects.filter(
            to_hash=to_hash, active=True, reason__in=_blocking,
        ).exists()
    except Exception as exc:  # broad-by-design — never block the hot path
        logger.warning(
            "schoolops.email_delivery.suppression_check_failed err_type=%s",
            type(exc).__name__,
        )
        return False


def suppress_recipient(
    to: str,
    *,
    reason: str = "hard_bounce",
    source: str = "",
    detail: str = "",
) -> bool:
    """Add (or refresh) an address on the suppression list. Idempotent.

    Returns True on success. Never raises into the caller. Re-activates a
    previously-lifted row so a fresh bounce after a re-subscribe re-blocks.
    """
    addr = (to or "").strip()
    if not addr:
        return False
    try:
        from apps.schoolops.models_email_suppression import SuppressedRecipient

        to_hash = _hash_recipient(addr)
        # tenant-isolation-allow: platform-email-suppression-no-tenant-scope
        SuppressedRecipient.objects.update_or_create(
            to_hash=to_hash,
            defaults={
                "reason": (reason or "hard_bounce")[:24],
                "source": (source or "")[:48],
                "detail": (detail or "")[:120],
                "active": True,
            },
        )
        logger.info(
            "schoolops.email_delivery.recipient_suppressed "
            "to_hash=%s reason=%s source=%s",
            to_hash, reason, source,
        )
        return True
    except Exception as exc:  # broad-by-design
        logger.warning(
            "schoolops.email_delivery.suppress_failed err_type=%s",
            type(exc).__name__,
        )
        return False


def lift_suppression(to: str) -> bool:
    """Lift suppression for an address (re-subscribe / operator clear).

    Sets ``active=False`` (retains the row for audit). Returns True if a
    row was updated.
    """
    addr = (to or "").strip()
    if not addr:
        return False
    try:
        from apps.schoolops.models_email_suppression import SuppressedRecipient

        to_hash = _hash_recipient(addr)
        # tenant-isolation-allow: platform-email-suppression-no-tenant-scope
        updated = SuppressedRecipient.objects.filter(
            to_hash=to_hash, active=True,
        ).update(active=False)
        return bool(updated)
    except Exception as exc:  # broad-by-design
        logger.warning(
            "schoolops.email_delivery.lift_suppression_failed err_type=%s",
            type(exc).__name__,
        )
        return False


# ──────────────────────────────────────────────────────────────────────
# Dead-letter queue (audit residual) — park + redrive failed sends.
# ──────────────────────────────────────────────────────────────────────


_DEFAULT_DLQ_MAX_REDRIVES = 5


def _dlq_enabled() -> bool:
    """True when the operator has opted into the dead-letter queue."""
    return _coerce_to_bool(
        getattr(settings, "SCHOOLOPS_EMAIL_DLQ_ENABLED", False), False,
    )


def _dlq_max_redrives() -> int:
    """Resolve the per-row redrive ceiling (default 5)."""
    raw = getattr(settings, "SCHOOLOPS_EMAIL_DLQ_MAX_REDRIVES", None)
    try:
        val = int(raw) if raw is not None else _DEFAULT_DLQ_MAX_REDRIVES
    except (TypeError, ValueError):
        return _DEFAULT_DLQ_MAX_REDRIVES
    return val if val > 0 else _DEFAULT_DLQ_MAX_REDRIVES


def _maybe_enqueue_dead_letter(
    *,
    subject: str,
    body: str,
    to: list,
    html_body: Optional[str],
    reply_to: Optional[Union[str, Iterable[str]]],
    from_email: Optional[str],
    headers: Optional[dict],
    priority: str,
    school: Any,
    idempotency_key: str,
    to_hash: str,
    subject_prefix: str,
    error_kind: str,
    attempts: int,
    delivery_event_id: Optional[str],
) -> None:
    """Park a permanently-failed retry-eligible send for later redrive.

    No-op unless ``SCHOOLOPS_EMAIL_DLQ_ENABLED`` is set. The full resend
    payload is Fernet-encrypted before storage so no plaintext body lands at
    rest. Best-effort — never raises into the send hot path.
    """
    if not _dlq_enabled():
        return
    try:
        from apps.accounts.legacy_hashes.encryption import _get_fernet
        from apps.schoolops.models_email_deadletter import EmailDeadLetter

        payload = {
            "subject": subject,
            "body": body,
            "html_body": html_body,
            "to": list(to or []),
            "reply_to": list(_coerce_to_list(reply_to)) if reply_to else None,
            "from_email": from_email,
            "headers": headers or None,
            "priority": priority,
            "school_id": getattr(school, "id", None) or getattr(school, "pk", None),
            "idempotency_key": idempotency_key or "",
        }
        token = _get_fernet().encrypt(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ).decode("utf-8")
        # tenant-isolation-allow: platform-email-dead-letter-no-tenant-scope
        EmailDeadLetter.objects.create(
            to_hash=to_hash,
            subject_prefix=subject_prefix,
            priority=priority,
            payload_encrypted=token,
            error_kind=(error_kind or "")[:64],
            attempts=int(attempts or 0),
            delivery_event_id=(delivery_event_id or "")[:64],
        )
        logger.info(
            "schoolops.email_delivery.dead_letter_enqueued to_hash=%s error_kind=%s",
            to_hash, error_kind,
        )
    except Exception as exc:  # broad-by-design — DLQ enqueue never breaks a send
        logger.warning(
            "schoolops.email_delivery.dead_letter_enqueue_failed err_type=%s",
            type(exc).__name__,
        )


def redrive_dead_letters(limit: int = 50) -> dict:
    """Re-attempt parked dead-letter sends. Returns a summary dict.

    Worked by ``python manage.py redrive_email_dead_letters``. Each pending row
    is decrypted, re-sent with a FRESH idempotency key (so it never dedupes back
    to the original failure row), and transitioned: success → ``redriven``;
    failure with attempts left → stays ``pending`` (count bumped); failure at
    the ceiling → ``exhausted``. Suppression is honoured (a recipient that
    bounced/complained meanwhile is skipped → ``abandoned``). NEVER raises.
    """
    summary = {
        "scanned": 0, "redriven": 0, "still_pending": 0,
        "exhausted": 0, "abandoned": 0, "enabled": _dlq_enabled(),
    }
    try:
        from django.utils import timezone

        from apps.accounts.legacy_hashes.encryption import _get_fernet
        from apps.schoolops.models_email_deadletter import (
            DeadLetterStatus,
            EmailDeadLetter,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "schoolops.email_delivery.redrive_import_failed err_type=%s",
            type(exc).__name__,
        )
        return summary

    max_redrives = _dlq_max_redrives()
    try:
        # tenant-isolation-allow: platform-email-dead-letter-no-tenant-scope
        rows = list(
            EmailDeadLetter.objects.filter(status=DeadLetterStatus.PENDING)
            .order_by("created_at")[: max(1, int(limit))]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "schoolops.email_delivery.redrive_query_failed err_type=%s",
            type(exc).__name__,
        )
        return summary

    for row in rows:
        summary["scanned"] += 1
        try:
            payload = json.loads(
                _get_fernet().decrypt(row.payload_encrypted.encode("utf-8"))
            )
        except Exception as exc:  # noqa: BLE001 — undecryptable row → abandon
            logger.warning(
                "schoolops.email_delivery.redrive_decrypt_failed err_type=%s",
                type(exc).__name__,
            )
            row.status = DeadLetterStatus.ABANDONED
            row.last_error_kind = "decrypt_failed"
            row.redriven_at = timezone.now()
            row.save(update_fields=["status", "last_error_kind", "redriven_at", "updated_at"])
            summary["abandoned"] += 1
            continue

        to_list = payload.get("to") or []
        if to_list and is_recipient_suppressed(to_list[0]):
            row.status = DeadLetterStatus.ABANDONED
            row.last_error_kind = "suppressed"
            row.redriven_at = timezone.now()
            row.save(update_fields=["status", "last_error_kind", "redriven_at", "updated_at"])
            summary["abandoned"] += 1
            continue

        school = None
        sid = payload.get("school_id")
        if sid:
            try:
                from apps.schools.models import School

                # tenant-isolation-allow: redrive re-resolves the original send's school by id
                school = School.objects.filter(pk=sid).first()
            except Exception:  # noqa: BLE001
                school = None

        attempt_no = int(row.redrive_count or 0) + 1
        base_idem = payload.get("idempotency_key") or f"dlq:{row.id}"
        result = send_transactional(
            subject=payload.get("subject") or "",
            body=payload.get("body") or "",
            to=to_list,
            html_body=payload.get("html_body"),
            reply_to=payload.get("reply_to"),
            from_email=payload.get("from_email"),
            headers=payload.get("headers"),
            priority=payload.get("priority") or "transactional",
            school=school,
            idempotency_key=f"{base_idem}:redrive:{attempt_no}",
        )
        row.redrive_count = attempt_no
        if result.get("ok"):
            row.status = DeadLetterStatus.REDRIVEN
            row.last_error_kind = ""
            row.redriven_at = timezone.now()
            row.save(update_fields=["status", "redrive_count", "last_error_kind", "redriven_at", "updated_at"])
            summary["redriven"] += 1
            continue
        row.last_error_kind = (result.get("error_kind") or "unknown")[:64]
        if attempt_no >= max_redrives:
            row.status = DeadLetterStatus.EXHAUSTED
            row.redriven_at = timezone.now()
            row.save(update_fields=["status", "redrive_count", "last_error_kind", "redriven_at", "updated_at"])
            summary["exhausted"] += 1
        else:
            row.save(update_fields=["redrive_count", "last_error_kind", "updated_at"])
            summary["still_pending"] += 1

    logger.info(
        "schoolops.email_delivery.redrive_complete scanned=%d redriven=%d "
        "exhausted=%d abandoned=%d",
        summary["scanned"], summary["redriven"], summary["exhausted"],
        summary["abandoned"],
    )
    return summary


# ──────────────────────────────────────────────────────────────────────
# Public sender — transactional.
# ──────────────────────────────────────────────────────────────────────


def _classify_exception(exc: BaseException) -> str:
    """Coarse-grained ``error_kind`` label for the persisted event."""
    if isinstance(exc, smtplib.SMTPException):
        return _ERR_SMTP
    if isinstance(exc, ConnectionError):
        return _ERR_CONN
    if isinstance(exc, OSError):
        return _ERR_OS
    if isinstance(exc, ValueError):
        return _ERR_VALUE
    return _ERR_OTHER


def _send_transactional_sync_core(
    *,
    subject: str,
    body: str,
    to: Union[str, Iterable[str]],
    html_body: Optional[str] = None,
    reply_to: Optional[Union[str, Iterable[str]]] = None,
    from_email: Optional[str] = None,
    headers: Optional[dict] = None,
    priority: str = "transactional",
    enforce_sync_budget: bool = True,
    school=None,
    idempotency_key: str = "",
    attachments: Optional[list] = None,
) -> dict:
    """Internal synchronous send implementation.

    When ``enforce_sync_budget=True``, the retry loop is bounded by a
    wall-clock budget (``SCHOOLOPS_EMAIL_DELIVERY_SYNC_BUDGET_SECONDS``,
    default 8s) AND each attempt's socket timeout is capped at 5s. This
    is the request-lifetime guard: a non-async caller can never block
    longer than the budget regardless of how the BACKOFF list is shaped.

    When ``enforce_sync_budget=False`` (only used by the async-thread
    path), the unrestricted retry sequence runs and exceptions are
    swallowed silently.
    """
    to_list = _coerce_to_list(to)
    if not to_list:
        logger.info(
            "schoolops.email_delivery.skip_no_recipient priority=%s",
            priority,
        )
        return {
            "ok": False,
            "attempts": 0,
            "delivery_event_id": None,
            "error_kind": _ERR_VALUE,
        }

    cfg = get_resolved_smtp_config(school=school)
    if enforce_sync_budget:
        # Cap the connection-level socket timeout so a single hung
        # SMTP attempt cannot block the request for the full
        # EMAIL_TIMEOUT value (default 10s) — we want fail-fast.
        try:
            existing_timeout = int(
                cfg.get("connection_timeout_seconds")
                or _DEFAULT_CONNECTION_TIMEOUT
            )
        except (TypeError, ValueError):
            existing_timeout = _DEFAULT_CONNECTION_TIMEOUT
        cfg = dict(cfg)
        cfg["connection_timeout_seconds"] = min(
            existing_timeout, _SYNC_PER_ATTEMPT_TIMEOUT_CEILING,
        )

    backoff = _get_backoff()
    if not backoff:
        backoff = (0,)  # at least one attempt

    sync_budget_seconds = _DEFAULT_SYNC_BUDGET_SECONDS
    if enforce_sync_budget:
        try:
            sync_budget_seconds = int(
                getattr(
                    settings,
                    "SCHOOLOPS_EMAIL_DELIVERY_SYNC_BUDGET_SECONDS",
                    _DEFAULT_SYNC_BUDGET_SECONDS,
                )
            )
        except (TypeError, ValueError):
            sync_budget_seconds = _DEFAULT_SYNC_BUDGET_SECONDS

    to_hash = _hash_recipient(to_list[0])
    subject_prefix = _redact_subject_for_log(subject or "")

    # CRLF / header-injection guard (audit P2). Reject the send outright if
    # a caller-supplied From / Reply-To / header value carries a raw CR/LF —
    # that's an injection attempt, not a transient error, so we do not retry.
    injection_detected = (
        _has_crlf(from_email)
        or any(_has_crlf(r) for r in _coerce_to_list(reply_to))
        or any(_has_crlf(k) or _has_crlf(v) for k, v in (headers or {}).items())
    )
    if injection_detected:
        logger.error(
            "schoolops.email_delivery.header_injection_blocked "
            "to_hash=%s priority=%s",
            to_hash, priority,
        )
        delivery_event_id = _persist_event(
            to_hash=to_hash,
            subject_prefix=subject_prefix,
            priority=priority,
            attempts=0,
            ok=False,
            error_kind=_ERR_HEADER_INJECTION,
            idempotency_key=idempotency_key,
        )
        return {
            "ok": False,
            "attempts": 0,
            "delivery_event_id": delivery_event_id,
            "error_kind": _ERR_HEADER_INJECTION,
            "bounced": False,
            "bounce_kind": "",
        }

    from_header = _strip_header_value(_build_from_header(cfg, from_email))
    reply_to_list = [
        _strip_header_value(r)
        for r in (
            _coerce_to_list(reply_to) if reply_to else (
                [cfg["default_reply_to"]] if cfg.get("default_reply_to") else []
            )
        )
        if _strip_header_value(r)
    ]

    # DKIM-friendly headers — explicit Message-ID + Date. Strip CR/LF from
    # every caller-supplied header value defensively (belt-and-braces with
    # the injection gate above).
    domain_hint = (cfg.get("default_from_email") or "runmycampus.com").split(
        "@",
    )[-1] or "runmycampus.com"
    msg_headers = {
        str(k): _strip_header_value(v) for k, v in (headers or {}).items()
    }
    msg_headers.setdefault("Message-ID", _email_utils.make_msgid(domain=domain_hint))
    # UTC Date (audit P3 — localtime leaked the host timezone).
    msg_headers.setdefault("Date", _email_utils.formatdate(usegmt=True))
    msg_headers.setdefault("X-RMC-Email-Priority", priority)
    # Persist the Message-ID local-part so a later provider bounce webhook can
    # correlate the bounce to this exact row (audit residual closeout).
    message_id_prefix_value = _message_id_prefix(msg_headers.get("Message-ID", ""))

    last_exc_kind = ""
    last_bounce_kind = ""  # v3.58.x Wave 9 Agent M — set when the FINAL attempt raises a bounce-class exception
    attempts_made = 0
    ok = False
    started = time.monotonic()
    budget_exhausted = False

    for attempt_index, delay in enumerate(backoff, start=1):
        # Wall-clock budget check BEFORE each attempt (other than the first).
        if enforce_sync_budget and attempt_index > 1:
            if (time.monotonic() - started) >= sync_budget_seconds:
                budget_exhausted = True
                break
        attempts_made = attempt_index
        try:
            connection = _get_connection_for_send(cfg)
            if html_body:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=body,
                    from_email=from_header,
                    to=to_list,
                    reply_to=reply_to_list or None,
                    headers=msg_headers,
                    connection=connection,
                )
                msg.attach_alternative(html_body, "text/html")
            else:
                msg = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=from_header,
                    to=to_list,
                    reply_to=reply_to_list or None,
                    headers=msg_headers,
                    connection=connection,
                )
            # Optional attachments — each is (filename, content, mimetype) or a
            # MIMEBase, mirroring Django's EmailMessage.attach contract. Lets
            # report/finance senders (PDF/CSV) migrate off raw EmailMessage.
            for att in (attachments or []):
                try:
                    if isinstance(att, (tuple, list)) and len(att) == 3:
                        msg.attach(att[0], att[1], att[2])
                    else:
                        msg.attach(att)
                except Exception:  # noqa: BLE001 — a bad attachment never blocks the send
                    logger.warning(
                        "schoolops.email_delivery.attachment_skipped to_hash=%s",
                        to_hash,
                    )
            msg.send(fail_silently=False)
            ok = True
            last_exc_kind = ""
            last_bounce_kind = ""
            break
        except (
            smtplib.SMTPException,
            ConnectionError,
            OSError,
            ValueError,
        ) as exc:
            last_exc_kind = _classify_exception(exc)
            # v3.58.x Wave 9 Agent M — capture bounce class for the
            # latest attempt. Only sticks to the persisted row if the
            # send ultimately fails AND the LAST exception was bounce-
            # classed (a transient ConnectionError after an earlier
            # SMTPSenderRefused legitimately resets this).
            last_bounce_kind = _classify_bounce(exc)
            logger.warning(
                "schoolops.email_delivery.attempt_failed "
                "to_hash=%s priority=%s attempt=%d error_kind=%s err_type=%s",
                to_hash, priority, attempt_index, last_exc_kind,
                type(exc).__name__,
            )
            # Sleep between attempts UNLESS we just used the final
            # entry of the backoff sequence OR the sync budget would
            # be exhausted by the sleep itself.
            if attempt_index < len(backoff) and delay > 0:
                if enforce_sync_budget:
                    elapsed = time.monotonic() - started
                    remaining = sync_budget_seconds - elapsed
                    if remaining <= 0:
                        budget_exhausted = True
                        break
                    # Don't sleep past the budget; trim the delay.
                    bounded_delay = min(delay, remaining)
                    try:
                        time.sleep(bounded_delay)
                    except Exception:  # noqa: BLE001 — sleep never hard-fails
                        pass
                else:
                    try:
                        time.sleep(delay)
                    except Exception:  # noqa: BLE001 — sleep never hard-fails
                        pass
            continue
        except Exception as exc:  # broad-by-design  — never raise out
            last_exc_kind = _ERR_OTHER
            last_bounce_kind = ""  # unknown-shape failure — not a classified bounce
            logger.warning(
                "schoolops.email_delivery.attempt_failed_unexpected "
                "to_hash=%s priority=%s attempt=%d err_type=%s",
                to_hash, priority, attempt_index, type(exc).__name__,
            )
            if attempt_index < len(backoff) and delay > 0:
                if enforce_sync_budget:
                    elapsed = time.monotonic() - started
                    remaining = sync_budget_seconds - elapsed
                    if remaining <= 0:
                        budget_exhausted = True
                        break
                    bounded_delay = min(delay, remaining)
                    try:
                        time.sleep(bounded_delay)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    try:
                        time.sleep(delay)
                    except Exception:  # noqa: BLE001
                        pass
            continue

    if budget_exhausted and not ok:
        # We bailed out of the retry loop because the sync budget ran
        # out. Surface this distinctly so operators reading the
        # delivery log know WHY we stopped retrying.
        last_exc_kind = last_exc_kind or "sync_budget_exhausted"
        logger.warning(
            "schoolops.email_delivery.sync_budget_exhausted "
            "to_hash=%s priority=%s attempts=%d budget_seconds=%d",
            to_hash, priority, attempts_made, sync_budget_seconds,
        )

    # v3.58.x Wave 9 Agent M — propagate send-time bounce classification.
    # Only mark as bounced when the send permanently failed AND the last
    # exception was classified as a bounce.
    bounced_flag = bool(not ok and last_bounce_kind)
    delivery_event_id = _persist_event(
        to_hash=to_hash,
        subject_prefix=subject_prefix,
        priority=priority,
        attempts=attempts_made,
        ok=ok,
        error_kind="" if ok else last_exc_kind,
        bounced=bounced_flag,
        bounce_kind=last_bounce_kind if bounced_flag else "",
        idempotency_key=idempotency_key,
        message_id_prefix=message_id_prefix_value,
    )

    # Dead-letter queue (audit residual). When a transactional send permanently
    # fails for a RETRY-eligible reason (transient SMTP/connection exhaustion —
    # NOT a hard bounce, suppression, or header-injection) we optionally park
    # the full payload (encrypted) so an operator can redrive it once the relay
    # recovers. Opt-in via SCHOOLOPS_EMAIL_DLQ_ENABLED (default off) so we never
    # store message bodies unless the operator wants the DLQ.
    if (not ok) and (not bounced_flag) and last_exc_kind not in (
        _ERR_HEADER_INJECTION, _ERR_SUPPRESSED, _ERR_RATE_LIMIT, _ERR_QUEUED,
    ):
        _maybe_enqueue_dead_letter(
            subject=subject,
            body=body,
            to=to_list,
            html_body=html_body,
            reply_to=reply_to,
            from_email=from_email,
            headers=headers,
            priority=priority,
            school=school,
            idempotency_key=idempotency_key,
            to_hash=to_hash,
            subject_prefix=subject_prefix,
            error_kind=last_exc_kind,
            attempts=attempts_made,
            delivery_event_id=delivery_event_id,
        )

    # Auto-suppress on a hard send-time bounce (audit H3). Only the hard
    # classes (sender/recipients refused, 5xx) — soft/transient bounces stay
    # retry-eligible and are NOT suppressed. First recipient only (the hash
    # we persisted); multi-recipient transactional sends are rare.
    if bounced_flag and last_bounce_kind in (
        _BOUNCE_HARD_5XX, _BOUNCE_SENDER_REFUSED, _BOUNCE_RECIPIENTS_REFUSED,
    ):
        suppress_recipient(
            to_list[0],
            reason="hard_bounce",
            source="send_time",
            detail=last_bounce_kind,
        )

    if ok:
        logger.info(
            "schoolops.email_delivery.sent "
            "to_hash=%s priority=%s attempts=%d event_id=%s",
            to_hash, priority, attempts_made, delivery_event_id or "n/a",
        )
    else:
        logger.error(
            "schoolops.email_delivery.permanent_failure "
            "to_hash=%s priority=%s attempts=%d error_kind=%s "
            "bounced=%s bounce_kind=%s event_id=%s",
            to_hash, priority, attempts_made, last_exc_kind,
            bounced_flag, last_bounce_kind or "n/a",
            delivery_event_id or "n/a",
        )

    return {
        "ok": ok,
        "attempts": attempts_made,
        "delivery_event_id": delivery_event_id,
        "error_kind": "" if ok else last_exc_kind,
        "bounced": bounced_flag,
        "bounce_kind": last_bounce_kind if bounced_flag else "",
    }


def _async_send_worker(**kwargs: Any) -> None:
    """Daemon-thread target for ``async_send=True`` callers.

    Runs the full unrestricted retry sequence (no sync budget) and
    swallows ALL exceptions silently into the EmailDeliveryEvent
    audit row. NEVER re-raises — a daemon thread exception would
    only land in the thread's own context anyway.
    """
    try:
        _send_transactional_sync_core(
            enforce_sync_budget=False,
            **kwargs,
        )
    except Exception as exc:  # broad-by-design — async path never raises
        try:
            logger.warning(
                "schoolops.email_delivery.async_worker_crashed err_type=%s",
                type(exc).__name__,
            )
        except Exception:  # noqa: BLE001 — logging itself must never crash the thread
            pass


def send_transactional(
    *,
    subject: str,
    body: str,
    to: Union[str, Iterable[str]],
    html_body: Optional[str] = None,
    reply_to: Optional[Union[str, Iterable[str]]] = None,
    from_email: Optional[str] = None,
    headers: Optional[dict] = None,
    priority: str = "transactional",
    async_send: bool = False,
    tenant_hash: Optional[str] = None,
    school=None,
    idempotency_key: str = "",
    allow_suppressed: bool = False,
    attachments: Optional[list] = None,
) -> dict:
    """Send a transactional message with retries + audit logging.

    Returns ``{"ok": bool, "attempts": int, "delivery_event_id": str|None,
    "error_kind": str|None, "queued": bool|None, "bounced": bool,
    "bounce_kind": str}``. NEVER raises — mirrors the existing
    ``fail_silently=True`` semantics at every callsite.

    v3.58.x Wave 9 Agent M extends the signature with two opt-in concerns:

    * ``tenant_hash`` — when supplied, the per-tenant sliding-window
      rate limit (default 200 sends/hr per tenant, override via
      ``settings.SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP``) is
      consulted. On exceed: NO send is attempted, an EmailDeliveryEvent
      row is written with ``error_kind='rate_limit_exceeded'``, and the
      return dict carries ``ok=False, queued=False,
      error_kind='rate_limit_exceeded'``. Caller is expected to derive
      ``tenant_hash`` from ``school.slug`` via :func:`_hash_tenant`
      before calling. Pass ``None`` (the default) to skip the rate-
      limit gate — platform-level sends like the operator test email
      do this.
    * Hard-bounce classification — when an SMTP send permanently fails
      because of an ``SMTPSenderRefused`` / ``SMTPRecipientsRefused`` /
      5xx response exception on the FINAL attempt, the resulting
      EmailDeliveryEvent row is marked ``bounced=True`` with a coarse
      ``bounce_kind``. Retry-eligible transient failures (connection
      errors, socket timeouts, generic SMTPException without a 5xx
      code) leave ``bounced=False`` — they are not bounces.

    The caller's email body, recipient address, and full subject line
    are NEVER logged. We persist only ``to_hash`` (sha256[:12]) and a
    redacted 64-char subject prefix.

  * ``idempotency_key`` — when non-empty, a prior successful or failed
    send with the same key returns immediately with the existing
    ``delivery_event_id`` and ``ok`` from that row (no second SMTP).

    v3.58.x Wave 9 Agent K — ``async_send=True``:
        Schedule the send in a daemon thread and return IMMEDIATELY
        with ``{"ok": True, "queued": True, "attempts": 0,
        "delivery_event_id": None, "error_kind": None}``. The thread
        runs the full unrestricted retry sequence and logs an
        EmailDeliveryEvent audit row when it completes. NEVER re-raises
        out of the async path. This is the path the signup view uses
        so a dead SMTP host can never time out the HTTP request.

    When ``async_send=False`` (default — preserved for non-request callers),
    a synchronous wall-clock budget (``SCHOOLOPS_EMAIL_DELIVERY_SYNC_BUDGET_SECONDS``,
    default 8s) bounds the retry loop AND each attempt's socket timeout
    is capped at 5s. A single sync caller can never block longer than
    the budget regardless of how BACKOFF is configured.
    """
    idem = (idempotency_key or "").strip()[:128]
    if idem:
        existing_id = _find_idempotent_delivery_event(idem)
        if existing_id:
            try:
                from apps.schoolops.models_email_delivery import EmailDeliveryEvent

                # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
                row = EmailDeliveryEvent.objects.filter(pk=existing_id).only(
                    "ok", "attempts", "error_kind", "bounced", "bounce_kind"
                ).first()
            except Exception:
                row = None
            if row is not None:
                return {
                    "ok": bool(row.ok),
                    "attempts": int(row.attempts or 0),
                    "delivery_event_id": existing_id,
                    "error_kind": row.error_kind or None,
                    "queued": False,
                    "bounced": bool(row.bounced),
                    "bounce_kind": row.bounce_kind or "",
                    "deduplicated": True,
                }

    # ── Suppression gate (audit H3) ──────────────────────────────────
    # Before any send, consult the bounce/complaint/unsubscribe list.
    # ``allow_suppressed=True`` lets a caller bypass it for a re-opt-in
    # confirmation mail (e.g. newsletter re-subscribe) — but transactional
    # callers never set it. Suppression applies to the FIRST recipient.
    to_list_sup = _coerce_to_list(to)
    if not allow_suppressed and to_list_sup and is_recipient_suppressed(to_list_sup[0]):
        to_hash_sup = _hash_recipient(to_list_sup[0])
        delivery_event_id_sup = _persist_event(
            to_hash=to_hash_sup,
            subject_prefix=_redact_subject_for_log(subject or ""),
            priority=priority,
            attempts=0,
            ok=False,
            error_kind=_ERR_SUPPRESSED,
            idempotency_key=idempotency_key,
        )
        logger.info(
            "schoolops.email_delivery.send_skipped_suppressed "
            "to_hash=%s priority=%s event_id=%s",
            to_hash_sup, priority, delivery_event_id_sup or "n/a",
        )
        return {
            "ok": False,
            "queued": False,
            "attempts": 0,
            "delivery_event_id": delivery_event_id_sup,
            "error_kind": _ERR_SUPPRESSED,
            "suppressed": True,
            "bounced": False,
            "bounce_kind": "",
        }

    # ── v3.58.x Wave 9 Agent M — per-tenant rate-limit gate ──────────
    # Gate at the outer entry so both sync AND async paths share one
    # bucket. When tenant_hash is None (platform-level sends) the gate
    # is bypassed entirely — _check_per_tenant_rate_limit returns True
    # for empty input.
    if tenant_hash:
        cap = _resolve_tenant_hourly_cap()
        if not _check_per_tenant_rate_limit(tenant_hash, limit_per_hour=cap):
            to_list_rl = _coerce_to_list(to)
            to_hash_rl = _hash_recipient(to_list_rl[0]) if to_list_rl else ""
            subject_prefix_rl = _redact_subject_for_log(subject or "")
            delivery_event_id_rl = _persist_event(
                to_hash=to_hash_rl,
                subject_prefix=subject_prefix_rl,
                priority=priority,
                attempts=0,
                ok=False,
                error_kind=_ERR_RATE_LIMIT,
                bounced=False,
                bounce_kind="",
            )
            logger.warning(
                "schoolops.email_delivery.rate_limit_exceeded "
                "tenant_hash=%s to_hash=%s priority=%s cap_per_hour=%d "
                "event_id=%s",
                tenant_hash, to_hash_rl, priority, cap,
                delivery_event_id_rl or "n/a",
            )
            return {
                "ok": False,
                "queued": False,
                "attempts": 0,
                "delivery_event_id": delivery_event_id_rl,
                "error_kind": _ERR_RATE_LIMIT,
                "bounced": False,
                "bounce_kind": "",
            }

    if async_send:
        # Audit C2 — write a synchronous "queued" marker row BEFORE we hand
        # off. If the daemon thread dies on a worker restart (the live
        # "no activation email" failure class) or a Celery task is never
        # drained, this row remains visible on the health dashboard as a
        # stuck/queued send instead of vanishing without a trace. The marker
        # carries NO idempotency_key (so it never dedupes against the real
        # terminal row the worker writes).
        to_list_q = _coerce_to_list(to)
        queued_event_id = _persist_event(
            to_hash=_hash_recipient(to_list_q[0]) if to_list_q else "",
            subject_prefix=_redact_subject_for_log(subject or ""),
            priority=priority,
            attempts=0,
            ok=False,
            error_kind=_ERR_QUEUED,
        )

        worker_kwargs = {
            "subject": subject,
            "body": body,
            "to": to,
            "html_body": html_body,
            "reply_to": reply_to,
            "from_email": from_email,
            "headers": headers,
            "priority": priority,
            "school": school,
            "idempotency_key": idempotency_key,
        }

        # Durable path (opt-in): when an always-on Celery worker is available
        # and SCHOOLOPS_EMAIL_ASYNC_USE_CELERY is set, dispatch the send as a
        # task so it survives a web-worker restart. Default stays the daemon
        # thread (free-tier reality: the worker may be asleep, and a hung
        # thread is still bounded by the per-attempt socket cap).
        if getattr(settings, "SCHOOLOPS_EMAIL_ASYNC_USE_CELERY", False):
            try:
                from apps.schoolops.tasks import dispatch_transactional_email

                dispatch_transactional_email.delay(**worker_kwargs)
                return {
                    "ok": True,
                    "attempts": 0,
                    "delivery_event_id": queued_event_id,
                    "error_kind": None,
                    "queued": True,
                    "transport": "celery",
                }
            except Exception as exc:  # broad-by-design — fall back to thread
                logger.warning(
                    "schoolops.email_delivery.async_celery_dispatch_failed "
                    "err_type=%s falling_back_to_thread",
                    type(exc).__name__,
                )

        thread = threading.Thread(
            target=_async_send_worker,
            kwargs=worker_kwargs,
            name="schoolops-email-async-send",
            daemon=True,
        )
        try:
            thread.start()
        except RuntimeError as exc:
            # Worker startup failures (e.g. interpreter shutdown) are
            # surfaced as a non-fatal queued=False result. NEVER raises.
            logger.warning(
                "schoolops.email_delivery.async_thread_start_failed err_type=%s",
                type(exc).__name__,
            )
            return {
                "ok": False,
                "attempts": 0,
                "delivery_event_id": queued_event_id,
                "error_kind": "thread_start_failed",
                "queued": False,
            }
        return {
            "ok": True,
            "attempts": 0,
            "delivery_event_id": queued_event_id,
            "error_kind": None,
            "queued": True,
            "transport": "thread",
        }

    return _send_transactional_sync_core(
        subject=subject,
        body=body,
        to=to,
        html_body=html_body,
        reply_to=reply_to,
        from_email=from_email,
        headers=headers,
        priority=priority,
        enforce_sync_budget=True,
        school=school,
        idempotency_key=idempotency_key,
        attachments=attachments,
    )


# ──────────────────────────────────────────────────────────────────────
# Public sender — bulk.
# ──────────────────────────────────────────────────────────────────────


def send_bulk(
    *,
    subject: str,
    body: str,
    to: Optional[Union[str, Iterable[str]]] = None,
    recipients: Optional[Union[str, Iterable[str]]] = None,
    html_body: Optional[str] = None,
    reply_to: Optional[Union[str, Iterable[str]]] = None,
    from_email: Optional[str] = None,
    headers: Optional[dict] = None,
    priority: str = "bulk",
    idempotency_key: str = "",
) -> dict:
    """Queue a bulk send via Celery when available, fall back to inline.

    Returns the same dict shape as :func:`send_transactional`. When the
    Celery path is taken, ``attempts`` is reported as 0 and
    ``delivery_event_id`` is None — the real attempt + persistence
    happens when the worker runs ``send_transactional``.

    Audit H2 — ``recipients`` is accepted as an alias for ``to`` (some
    callers, incl. ``test_email_health --bulk``, used it), and ``priority``
    / ``idempotency_key`` are forwarded so the bulk path has feature parity
    with :func:`send_transactional`. Previously these kwargs raised
    ``TypeError`` and the ``--bulk`` health probe always failed.
    """
    resolved_to = to if to is not None else recipients
    to_list = list(_coerce_to_list(resolved_to))
    try:
        # Lazy import — celery is optional in dev / tests.
        from apps.schoolops.tasks import dispatch_bulk_email  # type: ignore[attr-defined]

        # Apply async; never block the caller. If Celery isn't running
        # the broker enqueue still succeeds; the worker picks it up
        # later. If the broker itself is unreachable we fall through
        # to the inline path below.
        dispatch_bulk_email.delay(  # type: ignore[union-attr]
            subject=subject,
            body=body,
            to=to_list,
            html_body=html_body,
            reply_to=list(_coerce_to_list(reply_to)) if reply_to else None,
            from_email=from_email,
            headers=headers,
            priority=priority,
            idempotency_key=idempotency_key,
        )
        return {
            "ok": True,
            "attempts": 0,
            "delivery_event_id": None,
            "error_kind": "",
            "queued": True,
        }
    except (ImportError, AttributeError):
        # No Celery task wired — fall through to inline send.
        logger.info(
            "schoolops.email_delivery.bulk_celery_unavailable_falling_inline"
        )
    except Exception as exc:  # broad-by-design  — broker / serializer issues
        logger.warning(
            "schoolops.email_delivery.bulk_celery_dispatch_failed "
            "err_type=%s falling_inline",
            type(exc).__name__,
        )

    return send_transactional(
        subject=subject,
        body=body,
        to=to_list,
        html_body=html_body,
        reply_to=reply_to,
        from_email=from_email,
        headers=headers,
        priority=priority or "bulk",
        idempotency_key=idempotency_key,
    )


# ──────────────────────────────────────────────────────────────────────
# Operator dashboard helpers.
# ──────────────────────────────────────────────────────────────────────


def smtp_probe(timeout: float = _DEFAULT_SMTP_PROBE_TIMEOUT) -> dict:
    """Synchronous "can we open an SMTP connection?" check.

    Used by the operator email-health dashboard's "Test SMTP" button.
    Returns ``{"ok": bool, "latency_ms": int, "error": str|None, "host",
    "port", "use_tls"}``. NEVER raises.

    For the ``console`` backend (dev) the probe short-circuits to
    ``ok=True`` with a synthetic latency of 0 — no SMTP roundtrip
    happens in dev.
    """
    cfg = get_resolved_smtp_config()
    host = cfg.get("host") or ""
    port = int(cfg.get("port") or 587)
    use_tls = bool(cfg.get("use_tls"))

    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    if "console" in backend or "locmem" in backend or "dummy" in backend:
        return {
            "ok": True,
            "latency_ms": 0,
            "error": None,
            "host": host or "(dev backend — no SMTP roundtrip)",
            "port": port,
            "use_tls": use_tls,
            "backend": backend,
        }

    if not host:
        return {
            "ok": False,
            "latency_ms": 0,
            "error": "EMAIL_HOST is empty",
            "host": "",
            "port": port,
            "use_tls": use_tls,
            "backend": backend,
        }

    started = time.monotonic()
    try:
        # smtplib.SMTP() does the connect + EHLO; we don't need to auth
        # to know whether the server is reachable. STARTTLS is exercised
        # only on the dedicated TLS port (465) or via explicit ``starttls()``.
        if port == 465:
            sock = smtplib.SMTP_SSL(host=host, port=port, timeout=timeout)
        tls_warning = None
        if port == 465:
            sock = smtplib.SMTP_SSL(host=host, port=port, timeout=timeout)
        else:
            sock = smtplib.SMTP(host=host, port=port, timeout=timeout)
            if use_tls:
                try:
                    sock.starttls()
                except smtplib.SMTPException as tls_exc:
                    # STARTTLS unsupported is a real config issue (mail would
                    # go in cleartext) — surface it loudly instead of the
                    # previous silent ``pass`` so a green dashboard can't hide
                    # a relay that quietly dropped TLS (audit P2).
                    tls_warning = (
                        f"STARTTLS_failed:{type(tls_exc).__name__}"
                    )
                    logger.warning(
                        "schoolops.email_delivery.smtp_probe_starttls_failed "
                        "host=%s port=%d err_type=%s",
                        host, port, type(tls_exc).__name__,
                    )
        try:
            sock.ehlo_or_helo_if_needed()
        finally:
            try:
                sock.quit()
            except smtplib.SMTPException:
                pass
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": True,
            "latency_ms": elapsed_ms,
            "error": None,
            "tls_warning": tls_warning,
            "host": host,
            "port": port,
            "use_tls": use_tls,
            "backend": backend,
        }
    except (smtplib.SMTPException, OSError, socket.timeout, ConnectionError) as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "latency_ms": elapsed_ms,
            "error": type(exc).__name__,
            "host": host,
            "port": port,
            "use_tls": use_tls,
            "backend": backend,
        }
    except Exception as exc:  # broad-by-design — never raise
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "latency_ms": elapsed_ms,
            "error": type(exc).__name__,
            "host": host,
            "port": port,
            "use_tls": use_tls,
            "backend": backend,
        }


def get_recent_delivery_stats(window_hours: int = 24) -> dict:
    """Return aggregate counts from EmailDeliveryEvent over a recent window.

    Returns::

        {
          "sent_count": int,
          "failed_count": int,
          "last_failure_iso": str | None,
          "last_failure_reason_kind": str | None,
          "window_hours": int,
        }

    Best-effort: returns zeros on any error.
    """
    out = {
        "sent_count": 0,
        "failed_count": 0,
        "queued_count": 0,
        "suppressed_count": 0,
        "rate_limited_count": 0,
        "stuck_queued_count": 0,
        "last_failure_iso": None,
        "last_failure_reason_kind": None,
        "window_hours": int(window_hours),
    }
    try:
        from django.utils import timezone

        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        now = timezone.now()
        cutoff = now - _dt.timedelta(hours=int(window_hours))
        # Intentional-non-send sentinels are reported separately so the
        # genuine-failure count is not polluted by queued markers (C2),
        # suppression skips (H3), or rate-limit rejections.
        _sentinels = (_ERR_QUEUED, _ERR_SUPPRESSED, _ERR_RATE_LIMIT)
        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        qs = EmailDeliveryEvent.objects.filter(created_at__gte=cutoff)
        out["sent_count"] = qs.filter(ok=True).count()
        out["failed_count"] = qs.filter(ok=False).exclude(
            error_kind__in=_sentinels
        ).count()
        out["queued_count"] = qs.filter(error_kind=_ERR_QUEUED).count()
        out["suppressed_count"] = qs.filter(error_kind=_ERR_SUPPRESSED).count()
        out["rate_limited_count"] = qs.filter(error_kind=_ERR_RATE_LIMIT).count()
        # Stuck = a queued marker older than the stuck threshold (default
        # 15 min) that was never followed by delivery → a dropped async send.
        stuck_minutes = _coerce_to_int(
            getattr(settings, "SCHOOLOPS_EMAIL_STUCK_QUEUED_MINUTES", 15), 15,
        )
        stuck_cutoff = now - _dt.timedelta(minutes=max(1, stuck_minutes))
        out["stuck_queued_count"] = (
            EmailDeliveryEvent.objects.filter(  # noqa: E501
                # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
                error_kind=_ERR_QUEUED, created_at__lt=stuck_cutoff,
                created_at__gte=cutoff,
            ).count()
        )
        last_fail = (
            qs.filter(ok=False)
            .exclude(error_kind__in=_sentinels)
            .order_by("-created_at")
            .only("created_at", "error_kind")
            .first()
        )
        if last_fail is not None:
            out["last_failure_iso"] = last_fail.created_at.isoformat()
            out["last_failure_reason_kind"] = last_fail.error_kind or "unknown"
    except Exception as exc:  # broad-by-design — dashboard reader, never raise
        logger.warning(
            "schoolops.email_delivery.stats_read_failed err_type=%s",
            type(exc).__name__,
        )
    return out


def get_recent_failures(limit: int = 5) -> list[dict]:
    """Return the N most-recent failures for the operator dashboard panel.

    Each entry::

        {
          "to_hash": str,
          "subject_prefix": str,
          "error_kind": str,
          "attempts": int,
          "created_at_iso": str,
          "priority": str,
        }

    NEVER returns raw recipient addresses.
    """
    out: list[dict] = []
    try:
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        rows = (
            EmailDeliveryEvent.objects.filter(ok=False)
            .exclude(error_kind__in=(_ERR_QUEUED, _ERR_SUPPRESSED, _ERR_RATE_LIMIT))
            .order_by("-created_at")[: max(1, int(limit))]
        )
        for r in rows:
            out.append({
                "to_hash": r.to_hash,
                "subject_prefix": r.subject_prefix,
                "error_kind": r.error_kind or "unknown",
                "attempts": int(r.attempts or 0),
                "created_at_iso": r.created_at.isoformat(),
                "priority": r.priority,
            })
    except Exception as exc:  # broad-by-design — dashboard reader
        logger.warning(
            "schoolops.email_delivery.failures_read_failed err_type=%s",
            type(exc).__name__,
        )
    return out


# ──────────────────────────────────────────────────────────────────────
# Form-side helper: encrypt a freshly-entered SMTP password.
# ──────────────────────────────────────────────────────────────────────


def encrypt_password_for_storage(plaintext: str) -> str:
    """Fernet-wrap a plaintext SMTP password for storage in the JSON blob.

    Returns the url-safe-base64-encoded ciphertext as a str. The
    operator form layer calls this in ``save()``; the stored bytes are
    only ever decrypted via :func:`_decrypt_password_b64` on the
    send-hot-path.

    Empty input returns empty string — the resolver treats an empty
    encrypted blob as "no override password configured".
    """
    if not plaintext:
        return ""
    try:
        from apps.accounts.legacy_hashes.encryption import _get_fernet

        token = _get_fernet().encrypt(plaintext.encode("utf-8"))
        # Fernet output is already url-safe-base64. Decode for JSON storage.
        return token.decode("utf-8")
    except Exception as exc:  # broad-by-design — form layer handles
        logger.error(
            "schoolops.email_delivery.password_encrypt_failed err_type=%s",
            type(exc).__name__,
        )
        # Don't fall back to plaintext under ANY circumstance.
        raise


# Defensive import-time check — fail loudly if base64 disappears.
_ = base64


__all__ = [
    "send_transactional",
    "send_bulk",
    "smtp_probe",
    "get_resolved_smtp_config",
    "get_recent_delivery_stats",
    "get_recent_failures",
    "encrypt_password_for_storage",
    # Suppression list (audit H3).
    "is_recipient_suppressed",
    "suppress_recipient",
    "lift_suppression",
    # Dead-letter queue (audit residual).
    "redrive_dead_letters",
    # v3.58.x Wave 9 Agent M — bounce + rate-limit + tenant hashing.
    "_check_per_tenant_rate_limit",
    "_hash_tenant",
]
