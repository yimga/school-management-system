"""v3.40.0 Agent 12 — operator alert routing for Migration Cloud.

Email-only alerts (the v3.39 baseline) are not enough for production
on-call rotation. This module routes alerts to three channels with
severity-driven fan-out:

  * ``info``     → log only (structured)
  * ``warning``  → log + email + Slack webhook
  * ``critical`` → log + email + Slack + PagerDuty Events API v2

Public entry point:

    from apps.migration_cloud.alerts import alert

    alert(
        severity="critical",
        title="Migration Cloud: audit chain broken",
        body="Tenant <tenant_sha256_prefix> chain verifier reported a break.",
        dedupe_key="audit-chain-broken-global",
        links={"Command Center": "https://.../super/migration/command-center/"},
    )

Constraints (hard):
  * Stdlib-only HTTP — no ``requests`` / ``slack-sdk`` / ``pdpyras``.
  * 5 s timeout on every outbound HTTP call.
  * NEVER log webhook URL, integration key, or payload body text in clear
    — sha256-prefix only.
  * Channel failures NEVER cascade. ``alert()`` always returns ``None``.
  * Dry-run mode (``OPERATOR_ALERT_DRY_RUN=1``, the default) logs what
    *would* be sent without actually POST-ing. Operators flip to ``0``
    deliberately in production.

Settings (env-gated; all read via ``os.environ.get`` at module import):
  * ``OPERATOR_ALERT_SLACK_WEBHOOK_URL``           (default None)
  * ``OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY``   (default None)
  * ``OPERATOR_ALERT_DRY_RUN``                     (default "1")
  * ``OPERATOR_ALERT_RATE_LIMIT_PER_HOUR``         (default 50)
  * ``OPERATOR_ALERT_EMAIL``                       — reused from v3.39
    (``MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL``); kept fall-through.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"
_VALID_SEVERITIES = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL)

#: Outbound HTTP timeout for every channel — hard constraint.
_HTTP_TIMEOUT_SECONDS = 5

#: TTL on per-dedup-key suppression. 1 hour (matches PagerDuty's default
#: incident dedupe window).
_DEDUPE_TTL_SECONDS = 3600

#: PagerDuty Events API v2 endpoint.
_PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

#: Module-level in-memory dedupe store. Maps dedup_key -> first-seen
#: monotonic timestamp. Intentionally dies on worker restart — PagerDuty
#: handles upstream dedupe, so a worker bounce won't double-page in
#: practice.
_dedupe_lock = threading.Lock()
_dedupe_seen: dict[str, float] = {}

#: Module-level counter of distinct dedup_keys observed in the current
#: rolling hour window. Reset lazily when keys age out.
_rate_limit_warning_emitted: bool = False


# ── Settings access ───────────────────────────────────────────────────────


def _get_slack_webhook_url() -> Optional[str]:
    """Return the configured Slack webhook URL, or ``None`` when disabled.

    Prefers ``settings.OPERATOR_ALERT_SLACK_WEBHOOK_URL`` (so tests can
    override via ``@override_settings``); falls back to the env var.
    """
    try:
        from django.conf import settings
        v = getattr(settings, "OPERATOR_ALERT_SLACK_WEBHOOK_URL", None)
        if v:
            return str(v).strip() or None
    except Exception:  # pragma: no cover - django absent in some lanes
        pass
    raw = (os.environ.get("OPERATOR_ALERT_SLACK_WEBHOOK_URL", "") or "").strip()
    return raw or None


def _get_pagerduty_key() -> Optional[str]:
    try:
        from django.conf import settings
        v = getattr(settings, "OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY", None)
        if v:
            return str(v).strip() or None
    except Exception:  # pragma: no cover
        pass
    raw = (os.environ.get("OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY", "") or "").strip()
    return raw or None


def _get_email_recipient() -> Optional[str]:
    """Return the operator alert email, or ``None`` when unset.

    Reuses ``settings.OPERATOR_ALERT_EMAIL`` (v3.40 alias) and falls back
    to v3.39's ``MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL``.
    """
    try:
        from django.conf import settings
        for attr in ("OPERATOR_ALERT_EMAIL", "MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL"):
            v = getattr(settings, attr, None)
            if v:
                return str(v).strip() or None
    except Exception:  # pragma: no cover
        pass
    return None


def _is_dry_run() -> bool:
    """Return True when alerts should be logged-only (no outbound HTTP)."""
    try:
        from django.conf import settings
        v = getattr(settings, "OPERATOR_ALERT_DRY_RUN", None)
        if v is not None:
            return str(v).strip() not in ("0", "false", "False", "")
    except Exception:  # pragma: no cover
        pass
    return (os.environ.get("OPERATOR_ALERT_DRY_RUN", "1") or "1").strip() not in ("0", "false", "False", "")


def _get_rate_limit_per_hour() -> int:
    try:
        from django.conf import settings
        v = getattr(settings, "OPERATOR_ALERT_RATE_LIMIT_PER_HOUR", None)
        if v is not None:
            return max(1, int(v))
    except Exception:  # pragma: no cover
        pass
    try:
        return max(1, int(os.environ.get("OPERATOR_ALERT_RATE_LIMIT_PER_HOUR", "50")))
    except (TypeError, ValueError):
        return 50


# ── Dedupe + rate limit ───────────────────────────────────────────────────


def _sha256_prefix(value: str, n: int = 12) -> str:
    """Return a short sha256 hex prefix — used to log webhook URLs safely."""
    h = hashlib.sha256((value or "").encode("utf-8", errors="replace")).hexdigest()
    return h[:n]


def _evict_aged(now: float) -> None:
    """Remove dedupe entries older than the TTL. Caller holds the lock."""
    cutoff = now - _DEDUPE_TTL_SECONDS
    stale = [k for k, t in _dedupe_seen.items() if t < cutoff]
    for k in stale:
        _dedupe_seen.pop(k, None)


def _should_emit(dedupe_key: str) -> tuple[bool, str]:
    """Check the dedupe / rate-limit table.

    Returns ``(allowed, reason)``. Reason is a stable short code suitable
    for logging.
    """
    global _rate_limit_warning_emitted
    now = time.monotonic()
    rate_limit = _get_rate_limit_per_hour()
    with _dedupe_lock:
        _evict_aged(now)
        first_seen = _dedupe_seen.get(dedupe_key)
        if first_seen is not None:
            # Already fired within the TTL — let the caller decide whether
            # to actually send. PagerDuty handles upstream dedupe via
            # ``dedup_key`` so a re-emit is acceptable; we still mark it.
            return True, "dedupe-repeat"
        if len(_dedupe_seen) >= rate_limit:
            # Above the per-hour ceiling — drop.
            if not _rate_limit_warning_emitted:
                logger.warning(
                    "operator_alert_rate_limit_reached limit=%s dedupe_key_sha=%s",
                    rate_limit, _sha256_prefix(dedupe_key),
                )
                _rate_limit_warning_emitted = True
            return False, "rate-limit-reached"
        _dedupe_seen[dedupe_key] = now
        # New key admitted — reset the once-per-window warning flag.
        _rate_limit_warning_emitted = False
        return True, "fresh"


# ── Channel: log ─────────────────────────────────────────────────────────


def _emit_log(*, severity: str, title: str, dedupe_key: str, links: dict | None) -> None:
    payload = {
        "severity": severity,
        "title": title,
        "dedupe_key_sha": _sha256_prefix(dedupe_key),
        "links": sorted((links or {}).keys()),
    }
    # Use a structured-style message; severity drives log level.
    msg = "operator_alert " + " ".join(f"{k}={v}" for k, v in payload.items())
    if severity == SEVERITY_CRITICAL:
        logger.error(msg)
    elif severity == SEVERITY_WARNING:
        logger.warning(msg)
    else:
        logger.info(msg)


# ── Channel: email ───────────────────────────────────────────────────────


def _emit_email(*, severity: str, title: str, body: str, links: dict | None) -> None:
    recipient = _get_email_recipient()
    if not recipient:
        return
    if _is_dry_run():
        logger.info(
            "operator_alert_email_dry_run severity=%s recipient_sha=%s",
            severity, _sha256_prefix(recipient),
        )
        return
    try:
        from django.conf import settings
        from apps.schoolops.email_compat import send_mail
    except Exception:  # pragma: no cover
        return
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "noreply@runmycampus.com"
    rendered_links = ""
    if links:
        rendered_links = "\n\nLinks:\n" + "\n".join(
            f"  - {label}: {url}" for label, url in sorted(links.items())
        )
    subject = f"[Migration Cloud][{severity.upper()}] {title}"[:200]
    try:
        send_mail(
            subject=subject,
            message=(body or "") + rendered_links,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=True,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "operator_alert_email_failed err_type=%s severity=%s",
            type(exc).__name__, severity,
        )


# ── Channel: Slack ───────────────────────────────────────────────────────


def _build_slack_payload(*, severity: str, title: str, body: str, links: dict | None) -> dict:
    severity_emoji = {
        SEVERITY_INFO: ":information_source:",
        SEVERITY_WARNING: ":warning:",
        SEVERITY_CRITICAL: ":rotating_light:",
    }.get(severity, ":bell:")
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{severity_emoji} {title}"[:150],
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": (body or "_(no body)_")[:2900]},
        },
    ]
    if links:
        link_md = " | ".join(
            f"<{url}|{label}>" for label, url in sorted(links.items())
        )
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": link_md}],
        })
    return {"text": title, "blocks": blocks}


def _emit_slack(*, severity: str, title: str, body: str, links: dict | None) -> None:
    webhook = _get_slack_webhook_url()
    if not webhook:
        return
    payload = _build_slack_payload(
        severity=severity, title=title, body=body, links=links
    )
    if _is_dry_run():
        logger.info(
            "operator_alert_slack_dry_run severity=%s webhook_sha=%s blocks=%s",
            severity, _sha256_prefix(webhook), len(payload["blocks"]),
        )
        return
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
            # Slack returns "ok" body with 200 on success; we only check
            # status, never read response body (avoid logging anything).
            status = getattr(resp, "status", None) or resp.getcode()
            if status and int(status) >= 400:
                logger.warning(
                    "operator_alert_slack_non_ok status=%s webhook_sha=%s",
                    status, _sha256_prefix(webhook),
                )
    except urllib.error.URLError as exc:
        logger.warning(
            "operator_alert_slack_failed err_type=%s reason=%s webhook_sha=%s",
            type(exc).__name__,
            getattr(exc, "reason", "?"),
            _sha256_prefix(webhook),
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "operator_alert_slack_failed err_type=%s webhook_sha=%s",
            type(exc).__name__, _sha256_prefix(webhook),
        )


# ── Channel: PagerDuty ───────────────────────────────────────────────────


def _build_pagerduty_payload(
    *,
    routing_key: str,
    severity: str,
    title: str,
    body: str,
    dedupe_key: str,
    links: dict | None,
) -> dict:
    # PagerDuty Events v2 accepts ``info`` / ``warning`` / ``error`` /
    # ``critical``. We map ours straight through with ``info`` → ``info``.
    pd_severity = {
        SEVERITY_INFO: "info",
        SEVERITY_WARNING: "warning",
        SEVERITY_CRITICAL: "critical",
    }.get(severity, "error")
    custom_details: dict = {}
    if body:
        # Cap to 1024 chars; the markdown body never contains PII per the
        # alert() contract, but keep the bound for safety.
        custom_details["body"] = body[:1024]
    if links:
        custom_details["links"] = links
    payload: dict = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "dedup_key": dedupe_key[:255],
        "payload": {
            "summary": title[:1024],
            "severity": pd_severity,
            "source": "migration-cloud",
            "custom_details": custom_details,
        },
    }
    if links:
        # PagerDuty also supports a top-level ``links`` array.
        payload["links"] = [
            {"href": url, "text": label}
            for label, url in sorted(links.items())
        ]
    return payload


def _emit_pagerduty(
    *, severity: str, title: str, body: str, dedupe_key: str, links: dict | None
) -> None:
    key = _get_pagerduty_key()
    if not key:
        return
    payload = _build_pagerduty_payload(
        routing_key=key,
        severity=severity,
        title=title,
        body=body,
        dedupe_key=dedupe_key,
        links=links,
    )
    if _is_dry_run():
        logger.info(
            "operator_alert_pagerduty_dry_run severity=%s integration_key_sha=%s dedup_key_sha=%s",
            severity, _sha256_prefix(key), _sha256_prefix(dedupe_key),
        )
        return
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _PAGERDUTY_EVENTS_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            if status and int(status) >= 400:
                logger.warning(
                    "operator_alert_pagerduty_non_ok status=%s integration_key_sha=%s",
                    status, _sha256_prefix(key),
                )
    except urllib.error.URLError as exc:
        logger.warning(
            "operator_alert_pagerduty_failed err_type=%s reason=%s integration_key_sha=%s",
            type(exc).__name__,
            getattr(exc, "reason", "?"),
            _sha256_prefix(key),
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "operator_alert_pagerduty_failed err_type=%s integration_key_sha=%s",
            type(exc).__name__, _sha256_prefix(key),
        )


# ── Public entry point ──────────────────────────────────────────────────


def alert(
    *,
    severity: str,
    title: str,
    body: str,
    dedupe_key: str,
    links: dict | None = None,
) -> None:
    """Dispatch an operator alert across the configured channels.

    Severity routing:
      * ``info``     → log only
      * ``warning``  → log + email + Slack
      * ``critical`` → log + email + Slack + PagerDuty

    ``title`` MUST be <=140 chars and PII-free. ``body`` is markdown and
    MUST be PII-free (sha256-prefix only for any identifier).

    Channel failures NEVER cascade — this function always returns
    ``None``. The dedupe table suppresses ``rate-limit-reached`` events
    silently after the first warning log per hour.
    """
    if severity not in _VALID_SEVERITIES:
        # An unknown severity is itself a bug; log + downgrade to warning
        # so the operator still sees the alert.
        logger.warning(
            "operator_alert_unknown_severity severity=%r downgrading_to=warning",
            severity,
        )
        severity = SEVERITY_WARNING

    safe_title = (title or "").strip()[:140]
    safe_body = body or ""
    safe_dedupe = (dedupe_key or "no-key")[:255]

    allowed, reason = _should_emit(safe_dedupe)
    if not allowed:
        # Rate-limit reached — the helper already logged the once-per-
        # window warning. Drop silently.
        return

    try:
        _emit_log(
            severity=severity,
            title=safe_title,
            dedupe_key=safe_dedupe,
            links=links,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "operator_alert_log_failed err_type=%s", type(exc).__name__,
        )

    if severity == SEVERITY_INFO:
        return

    # warning + critical: email + Slack
    try:
        _emit_email(
            severity=severity, title=safe_title, body=safe_body, links=links,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "operator_alert_email_unexpected err_type=%s", type(exc).__name__,
        )
    try:
        _emit_slack(
            severity=severity, title=safe_title, body=safe_body, links=links,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "operator_alert_slack_unexpected err_type=%s", type(exc).__name__,
        )

    if severity == SEVERITY_CRITICAL:
        try:
            _emit_pagerduty(
                severity=severity,
                title=safe_title,
                body=safe_body,
                dedupe_key=safe_dedupe,
                links=links,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "operator_alert_pagerduty_unexpected err_type=%s",
                type(exc).__name__,
            )
    # reason tagged for caller debug via log; suppress repeats noisily.
    if reason == "dedupe-repeat":
        logger.info(
            "operator_alert_dedupe_repeat dedupe_key_sha=%s severity=%s",
            _sha256_prefix(safe_dedupe), severity,
        )


# ── Introspection (for the command center status summary) ────────────────


def _snapshot_dedupe_state() -> tuple[int, Optional[float]]:
    """Return ``(active_dedup_keys, oldest_monotonic)``."""
    with _dedupe_lock:
        now = time.monotonic()
        _evict_aged(now)
        if not _dedupe_seen:
            return 0, None
        oldest = min(_dedupe_seen.values())
        return len(_dedupe_seen), oldest


def _channels_enabled() -> list[str]:
    out: list[str] = ["log"]
    if _get_email_recipient():
        out.append("email")
    if _get_slack_webhook_url():
        out.append("slack")
    if _get_pagerduty_key():
        out.append("pagerduty")
    return out


# Test-only hook: wipe the dedupe table between tests.
def _reset_state_for_tests() -> None:
    global _rate_limit_warning_emitted
    with _dedupe_lock:
        _dedupe_seen.clear()
        _rate_limit_warning_emitted = False


__all__ = [
    "alert",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "SEVERITY_CRITICAL",
]
