"""
Session pinning middleware: bind a logged-in session to the (IP, User-Agent)
pair captured at login time. If a subsequent request from the SAME session
arrives with a different (IP, UA-hash) pair, kill the session and write a
CRITICAL audit log entry — this catches session-token theft + replay from a
different network/device.

Pillar 1 (Identity) anti-fraud follow-up. Mirrors the structure of
``RequireMFAMiddleware`` in ``apps.accounts.middleware``.

Per-tenant override:
    A future ``SiteSettings.session_pinning_enabled`` field can turn pinning
    off per-tenant. Today no such field exists on ``apps.siteconfig.models``,
    so we gate on the global ``SESSION_PINNING_ENABLED`` setting only. The
    per-tenant override is tracked as a follow-up.
"""

from __future__ import annotations

import hashlib
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


# Bypass static / media / admin-jsi18n paths — these never carry a fresh
# auth signal and shouldn't trigger a session flush on a CDN edge change.
BYPASS_PREFIXES: tuple[str, ...] = (
    "/static/",
    "/media/",
    "/admin/jsi18n/",
)


def _get_client_ip(request) -> str:
    """Mirror of ``apps.schools.super_views_impersonation._get_client_ip``.

    Trust the first IP in ``X-Forwarded-For``; fall back to ``REMOTE_ADDR``.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return (xff.split(",")[0] or "").strip()
    return (request.META.get("REMOTE_ADDR") or "").strip()


def _hash_user_agent(ua: str) -> str:
    """SHA-256 of UA, truncated to 16 hex chars (64 bits — enough for pinning)."""
    return hashlib.sha256((ua or "").encode("utf-8", errors="replace")).hexdigest()[:16]


def _write_pin_mismatch_audit(
    user, *, ip: str, ua_hash: str, pinned_ip: str, pinned_ua: str
) -> None:
    """Write a CRITICAL ACCESS_DENIED audit entry. Failures here MUST NOT
    propagate (audit is best-effort; security action already happened)."""
    try:
        from apps.compliance.models_audit import AuditLog

        reason = (
            f"session-pin mismatch: pinned=({pinned_ip},{pinned_ua}) "
            f"observed=({ip},{ua_hash})"
        )
        AuditLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            ip_address=ip or None,
            user_agent="",
            action=AuditLog.Action.ACCESS_DENIED,
            model_name="Session",
            object_id=str(getattr(user, "pk", "") or ""),
            object_repr="session-pin mismatch",
            sensitivity=AuditLog.Sensitivity.CRITICAL,
            app_label="accounts",
            reason=reason[:255],
            new_values={
                "pinned_ip": pinned_ip,
                "pinned_ua_hash": pinned_ua,
                "observed_ip": ip,
                "observed_ua_hash": ua_hash,
            },
        )
    except Exception:  # noqa: BLE001 — audit is best-effort
        logger.exception("SessionPinningMiddleware: failed to write audit entry")


class SessionPinningMiddleware:
    """
    On every authenticated request, compute ``(ip, ua_hash)``.

    First-time-seen for the session: store ``_pin_ip`` + ``_pin_ua`` in
    ``request.session``.

    Subsequent requests: if the pair differs from the stored values, flush
    the session, write a CRITICAL audit log, and let the request continue
    (downstream LoginRequiredMiddleware / view decorators handle the now-
    anonymous user).

    Allowlist: ``/static/``, ``/media/``, ``/admin/jsi18n/`` skip the check.

    Opt-out: if ``settings.SESSION_PINNING_ENABLED`` is False, the middleware
    is a no-op.
    """

    SESSION_PIN_IP_KEY = "_pin_ip"
    SESSION_PIN_UA_KEY = "_pin_ua"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._enforce(request)
        return self.get_response(request)

    # ------------------------------------------------------------------ helpers

    def _enabled(self, request) -> bool:
        if not getattr(settings, "SESSION_PINNING_ENABLED", True):
            return False
        # Per-tenant opt-out hook: SiteSettings.session_pinning_enabled is not
        # yet a real field; if it ever lands, honor it here. Until then, the
        # global gate above is authoritative.
        try:
            from apps.siteconfig.config_service import get_effective_site_settings

            site = get_effective_site_settings(request=request)
            if site is not None and getattr(site, "session_pinning_enabled", True) is False:
                return False
        except Exception:  # noqa: BLE001 — never fail-open on config errors
            pass
        return True

    def _is_allowlisted(self, path: str) -> bool:
        path = path or ""
        return any(path.startswith(prefix) for prefix in BYPASS_PREFIXES)

    def _enforce(self, request) -> None:
        path = request.path or ""
        if self._is_allowlisted(path):
            return

        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return

        if not self._enabled(request):
            return

        session = getattr(request, "session", None)
        if session is None:
            return

        ip = _get_client_ip(request)
        ua_hash = _hash_user_agent(request.META.get("HTTP_USER_AGENT", "") or "")

        pinned_ip = session.get(self.SESSION_PIN_IP_KEY)
        pinned_ua = session.get(self.SESSION_PIN_UA_KEY)

        if pinned_ip is None and pinned_ua is None:
            # First-time-seen for this session.
            session[self.SESSION_PIN_IP_KEY] = ip
            session[self.SESSION_PIN_UA_KEY] = ua_hash
            return

        if pinned_ip == ip and pinned_ua == ua_hash:
            return

        # Mismatch — possible session-token theft. Kill the session.
        logger.warning(
            "SessionPinningMiddleware: pin mismatch for user_id=%s "
            "(pinned_ip=%s pinned_ua=%s observed_ip=%s observed_ua=%s) — flushing session",
            getattr(user, "pk", None),
            pinned_ip,
            pinned_ua,
            ip,
            ua_hash,
        )
        _write_pin_mismatch_audit(
            user, ip=ip, ua_hash=ua_hash, pinned_ip=pinned_ip or "", pinned_ua=pinned_ua or ""
        )
        try:
            session.flush()
        except Exception:  # noqa: BLE001 — flushing failures shouldn't crash the request
            logger.exception("SessionPinningMiddleware: session.flush() failed")
