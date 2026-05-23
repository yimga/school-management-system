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
_ERR_OTHER = "other"

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
        from apps.siteconfig.models import SiteSettings

        # tenant-isolation-allow: platform-email-policy-row-no-tenant-scope
        site_row = SiteSettings.objects.first()
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
        from apps.siteconfig.models import SiteSettings

        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        row = SiteSettings.objects.first()
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

    from_header = _build_from_header(cfg, from_email)
    reply_to_list = _coerce_to_list(reply_to) if reply_to else (
        [cfg["default_reply_to"]] if cfg.get("default_reply_to") else []
    )

    # DKIM-friendly headers — explicit Message-ID + Date.
    domain_hint = (cfg.get("default_from_email") or "runmycampus.com").split(
        "@",
    )[-1] or "runmycampus.com"
    msg_headers = dict(headers or {})
    msg_headers.setdefault("Message-ID", _email_utils.make_msgid(domain=domain_hint))
    msg_headers.setdefault("Date", _email_utils.formatdate(localtime=True))
    msg_headers.setdefault("X-RMC-Email-Priority", priority)

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
        thread = threading.Thread(
            target=_async_send_worker,
            kwargs={
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
            },
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
                "delivery_event_id": None,
                "error_kind": "thread_start_failed",
                "queued": False,
            }
        return {
            "ok": True,
            "attempts": 0,
            "delivery_event_id": None,
            "error_kind": None,
            "queued": True,
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
    )


# ──────────────────────────────────────────────────────────────────────
# Public sender — bulk.
# ──────────────────────────────────────────────────────────────────────


def send_bulk(
    *,
    subject: str,
    body: str,
    to: Union[str, Iterable[str]],
    html_body: Optional[str] = None,
    reply_to: Optional[Union[str, Iterable[str]]] = None,
    from_email: Optional[str] = None,
    headers: Optional[dict] = None,
) -> dict:
    """Queue a bulk send via Celery when available, fall back to inline.

    Returns the same dict shape as :func:`send_transactional`. When the
    Celery path is taken, ``attempts`` is reported as 0 and
    ``delivery_event_id`` is None — the real attempt + persistence
    happens when the worker runs ``send_transactional``.
    """
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
            to=list(_coerce_to_list(to)),
            html_body=html_body,
            reply_to=list(_coerce_to_list(reply_to)) if reply_to else None,
            from_email=from_email,
            headers=headers,
        )
        return {
            "ok": True,
            "attempts": 0,
            "delivery_event_id": None,
            "error_kind": "",
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
        to=to,
        html_body=html_body,
        reply_to=reply_to,
        from_email=from_email,
        headers=headers,
        priority="bulk",
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
        else:
            sock = smtplib.SMTP(host=host, port=port, timeout=timeout)
            if use_tls:
                try:
                    sock.starttls()
                except smtplib.SMTPException:
                    # STARTTLS unsupported is a real config issue but
                    # the bare connection works — surface it as a warning.
                    pass
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
        "last_failure_iso": None,
        "last_failure_reason_kind": None,
        "window_hours": int(window_hours),
    }
    try:
        from django.utils import timezone

        from apps.schoolops.models_email_delivery import EmailDeliveryEvent

        cutoff = timezone.now() - _dt.timedelta(hours=int(window_hours))
        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        qs = EmailDeliveryEvent.objects.filter(created_at__gte=cutoff)
        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        out["sent_count"] = qs.filter(ok=True).count()
        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        out["failed_count"] = qs.filter(ok=False).count()
        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        last_fail = (
            qs.filter(ok=False)
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
    # v3.58.x Wave 9 Agent M — bounce + rate-limit + tenant hashing.
    "_check_per_tenant_rate_limit",
    "_hash_tenant",
]
