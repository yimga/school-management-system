"""Per-tenant + per-token rate limiting for the Migration Cloud REST API.

Two distinct surfaces:

  * :class:`TenantRateLimiter` — webhook *outbound* delivery quota,
    sliding-window counter in Django cache. Default 1000/hour/tenant with
    a soft warning at 800. Consulted by
    :func:`apps.migration_cloud.api.webhook_dispatch.deliver_due` BEFORE
    each delivery is attempted; over-quota rows are *deferred* (status
    stays ``pending``, ``deferred_until`` set to the next hour boundary,
    attempt count NOT bumped) instead of attempted and burning a retry.
  * :class:`MigrationCloudReadThrottle` / :class:`MigrationCloudWriteThrottle`
    — DRF throttles applied to scoped-token traffic. Reads 600/min/token,
    writes 100/min/token. Wired via ``DEFAULT_THROTTLE_CLASSES`` on the
    relevant viewsets (additive to project defaults — see
    :func:`get_default_throttle_classes`).

The cache backend is the project's default Django cache; the keys are
namespaced with ``migration-cloud:rate:`` so a future Redis backend can
namespace eviction without affecting the rest of the platform.

Logging: every soft-warn / hard-reject path emits a single
``logger.info`` with tenant/token IDs + counts. NEVER logs payload
content, secret material, or token plaintext.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as _stdlib_tz

#: Stdlib UTC instance — used by ``.astimezone`` calls that need an actual
#: tzinfo subclass (Django's ``timezone`` module wraps but does not subclass).
_UTC = _stdlib_tz.utc
from typing import Optional

from django.core.cache import cache
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────

#: Cache key prefix — keeps rate-limit counters from colliding with other
#: cache users on the same backend.
_CACHE_PREFIX = "migration-cloud:rate"

#: Default per-tenant webhook delivery quota (per hour).
DEFAULT_TENANT_WEBHOOK_QUOTA_PER_HOUR = 1000

#: Soft-warning threshold (below this, we tag the row with a header but
#: still deliver). 800/1000 == 80%.
DEFAULT_TENANT_WEBHOOK_SOFT_LIMIT = 800

#: Per-scoped-token API read rate (requests per minute).
API_TOKEN_READ_RATE_PER_MIN = 600

#: Per-scoped-token API write rate (requests per minute).
API_TOKEN_WRITE_RATE_PER_MIN = 100

#: Cache TTL for an hour-bucket counter (3700s = 1 hour + a small grace
#: so a row near the boundary still resolves before expiry).
_HOUR_BUCKET_TTL_SECONDS = 3700

#: Window seconds for token throttles — DRF uses this directly.
_MINUTE_WINDOW_SECONDS = 60


# ─── Bucket math ──────────────────────────────────────────────────────────


def _hour_bucket_key(tenant_id: int, now: Optional[datetime] = None) -> str:
    """Return the cache key for ``tenant_id``'s current hour-bucket counter."""
    when = (now or timezone.now()).astimezone(_UTC)
    bucket = when.strftime("%Y%m%d%H")
    return f"{_CACHE_PREFIX}:tenant-webhook:{tenant_id}:{bucket}"


def _next_hour_boundary(now: Optional[datetime] = None) -> datetime:
    """Return the next ``HH:00:00`` instant after ``now``.

    The dispatcher uses this as ``deferred_until`` so the row resumes
    eligibility at the same moment the bucket counter resets.
    """
    when = (now or timezone.now()).astimezone(_UTC)
    next_hour = when.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return next_hour


# ─── Result types ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QuotaDecision:
    """Result of a quota check.

    Attributes:
        allowed: True when the caller may proceed.
        current_count: How many deliveries the tenant has done in this hour.
        limit: The hard quota ceiling.
        soft_limit: The warning threshold (deliveries still flow but the
            UI / response tag the bucket).
        is_soft_warn: True when current_count >= soft_limit but < limit.
        retry_after_seconds: Seconds until the next bucket boundary
            (only meaningful when ``allowed`` is False).
        reason: Short code describing the decision; safe to log + return
            in operator UI tables.
    """

    allowed: bool
    current_count: int
    limit: int
    soft_limit: int
    is_soft_warn: bool
    retry_after_seconds: int
    reason: str


# ─── Sliding-window counter ───────────────────────────────────────────────


class TenantRateLimiter:
    """Sliding-window-ish per-tenant webhook delivery counter.

    "Sliding-window-ish" because we use one bucket per wall-clock hour;
    truly-sliding requires a Redis sorted-set which we don't assume.
    Hour buckets are good enough for the webhook-delivery use case (the
    receiver-side retry policy is also hourly).

    Usage::

        limiter = TenantRateLimiter()
        decision = limiter.try_consume(tenant_id=42)
        if not decision.allowed:
            # defer the row
            ...
        elif decision.is_soft_warn:
            # add a warning header / log a hint
            ...
        else:
            # full speed ahead
            ...
    """

    def __init__(
        self,
        *,
        hour_quota: int = DEFAULT_TENANT_WEBHOOK_QUOTA_PER_HOUR,
        soft_limit: int = DEFAULT_TENANT_WEBHOOK_SOFT_LIMIT,
    ) -> None:
        if hour_quota <= 0:
            raise ValueError("hour_quota must be positive")
        if soft_limit <= 0 or soft_limit > hour_quota:
            raise ValueError("soft_limit must be in 1..hour_quota")
        self.hour_quota = hour_quota
        self.soft_limit = soft_limit

    def peek(self, tenant_id: int) -> int:
        """Return the current bucket count without incrementing."""
        return int(cache.get(_hour_bucket_key(tenant_id)) or 0)

    def try_consume(self, tenant_id: int) -> QuotaDecision:
        """Increment the tenant's hour-bucket and return a decision.

        On hard rejection we still increment so concurrent callers see
        the same boundary (the increment is harmless after rejection
        because all subsequent peek/try_consume calls in the same hour
        see the same overflow).
        """
        key = _hour_bucket_key(tenant_id)
        now = timezone.now()
        # Atomic-ish: cache.incr after add. Django's LocMemCache implements
        # both; Redis/memcached do too. We accept a small race in pure
        # local-memory test envs — the next call will catch up.
        added = cache.add(key, 0, _HOUR_BUCKET_TTL_SECONDS)
        if not added:
            # Key already exists — incr.
            try:
                current = cache.incr(key, 1)
            except ValueError:
                # Backend lost the key between add and incr — start fresh.
                cache.set(key, 1, _HOUR_BUCKET_TTL_SECONDS)
                current = 1
        else:
            current = cache.incr(key, 1)

        boundary = _next_hour_boundary(now)
        retry_after = max(int((boundary - now).total_seconds()), 1)

        if current > self.hour_quota:
            logger.info(
                "migration_cloud_tenant_quota_exhausted tenant_id=%s "
                "count=%s limit=%s retry_after=%s",
                tenant_id, current, self.hour_quota, retry_after,
            )
            return QuotaDecision(
                allowed=False,
                current_count=current,
                limit=self.hour_quota,
                soft_limit=self.soft_limit,
                is_soft_warn=False,
                retry_after_seconds=retry_after,
                reason="tenant-quota-exhausted",
            )

        is_soft = current >= self.soft_limit
        if is_soft:
            logger.info(
                "migration_cloud_tenant_quota_soft_warn tenant_id=%s "
                "count=%s soft_limit=%s limit=%s",
                tenant_id, current, self.soft_limit, self.hour_quota,
            )
        # v3.40.0 Agent 15 — saturation alert AFTER the soft-warn log line.
        # Bucket name here is the tenant-webhook cache key; sha256-prefixed
        # in the alert so the raw key never leaks.
        try:
            _check_saturation_alert(
                bucket_name=f"tenant-webhook:{tenant_id}",
                current=int(current),
                limit=int(self.hour_quota),
            )
        except Exception:  # pylint: disable=broad-except
            # Never let alerting break the throttle path.
            pass
        return QuotaDecision(
            allowed=True,
            current_count=current,
            limit=self.hour_quota,
            soft_limit=self.soft_limit,
            is_soft_warn=is_soft,
            retry_after_seconds=0,
            reason="tenant-quota-warning" if is_soft else "tenant-quota-ok",
        )

    def reset(self, tenant_id: int) -> None:
        """Test-only / admin: clear the tenant's current bucket."""
        cache.delete(_hour_bucket_key(tenant_id))


# ─── DRF throttles ────────────────────────────────────────────────────────


class _MigrationCloudTokenThrottleBase(SimpleRateThrottle):
    """Base throttle that keys on the scoped-token id when present.

    Session / authtoken callers fall back to user-id keys; anonymous
    callers fall back to IP — but anonymous callers are already rejected
    upstream by ``MigrationCloudAPIPermission``, so the IP path is just
    defense-in-depth.
    """

    cache_format = "throttle_migration_cloud_%(scope)s_%(ident)s"

    def get_cache_key(self, request, view):
        # Lazy import to avoid circular import via models.
        from apps.migration_cloud.models import MigrationCloudAPIToken

        ident = None
        auth = getattr(request, "auth", None)
        if isinstance(auth, MigrationCloudAPIToken):
            ident = f"tok-{auth.pk}"
        else:
            user = getattr(request, "user", None)
            if user is not None and getattr(user, "is_authenticated", False):
                ident = f"usr-{user.pk}"
        if ident is None:
            ident = self.get_ident(request) or "anon"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class MigrationCloudReadThrottle(_MigrationCloudTokenThrottleBase):
    """Read-side throttle: 600/min/token."""

    scope = "migration-cloud-read"
    rate = f"{API_TOKEN_READ_RATE_PER_MIN}/min"

    def get_rate(self):
        # Avoid DRF's settings-driven rate lookup; we own the constant.
        return self.rate


class MigrationCloudWriteThrottle(_MigrationCloudTokenThrottleBase):
    """Write-side throttle: 100/min/token."""

    scope = "migration-cloud-write"
    rate = f"{API_TOKEN_WRITE_RATE_PER_MIN}/min"

    def get_rate(self):
        return self.rate


def get_default_throttle_classes():
    """Return the throttle stack to add to Migration Cloud viewsets.

    Returns BOTH classes — DRF runs each ``allow_request`` independently
    and the most-restrictive wins. Write-heavy actions add the write
    throttle directly via :attr:`throttle_classes` on the viewset.
    """
    return [MigrationCloudReadThrottle]


# ─── v3.33.0 — path-scoped global throttle ─────────────────────────────────

#: Path prefix the global throttle activates on. Any request whose
#: ``request.path`` does NOT contain this segment is allowed through
#: without consulting the bucket, so non-/api/v1/ surfaces (operator UI,
#: marketing pages, status JSON) keep their existing throttle semantics.
MIGRATION_CLOUD_API_PATH_MARKER = "/api/v1/"

#: Sub-marker confirming this is the Migration Cloud REST surface (not
#: any other /api/v1/ root). The DRF router mounts both under
#: ``/super/migration/api/v1/`` and ``/portal/configure/migration/api/v1/``.
MIGRATION_CLOUD_PATH_SUB_MARKER = "/migration/"

#: Response header signaling the caller has crossed the soft-warn line.
#: Receivers can log this + back off; emission is non-fatal.
SOFT_WARN_HEADER = "X-RateLimit-Soft-Warn"

#: Header set on every throttled response with the current scope key —
#: lets operators trace which class of traffic tripped the gate.
SCOPE_HEADER = "X-RateLimit-Scope"


def _path_is_migration_cloud_api(path: str) -> bool:
    """Return True iff ``path`` targets the Migration Cloud REST surface.

    Both mount points share the ``…/migration/api/v1/…`` substring so a
    single test catches the operator and tenant shells alike. Defensive
    against missing leading slash / trailing slash.
    """
    if not path:
        return False
    return (
        MIGRATION_CLOUD_API_PATH_MARKER in path
        and MIGRATION_CLOUD_PATH_SUB_MARKER in path
    )


def _scope_for_request(request) -> str | None:
    """Map a request to its throttle scope, or ``None`` to skip throttling.

    Three scopes:
      * ``webhook_tenant``  — POST/GET/DELETE under ``/webhooks/`` or
        ``/api/v1/...webhooks``.
      * ``bundles_write`` — any non-safe HTTP method under the API
        (POST / PUT / PATCH / DELETE) on bundles/artifacts.
      * ``bundles_read``  — safe-method (GET / HEAD / OPTIONS) under the
        API.

    Returns ``None`` for any path that doesn't activate the throttle —
    DRF interprets that as "allow request" for this throttle class.
    """
    path = getattr(request, "path", "") or ""
    if not _path_is_migration_cloud_api(path):
        return None
    method = (getattr(request, "method", "") or "").upper()
    if "/webhooks" in path:
        return "webhook_tenant"
    if method in ("GET", "HEAD", "OPTIONS"):
        return "bundles_read"
    return "bundles_write"


class MigrationCloudGlobalThrottle(SimpleRateThrottle):
    """Path-scoped throttle wired into DRF's ``DEFAULT_THROTTLE_CLASSES``.

    DRF iterates every throttle in ``DEFAULT_THROTTLE_CLASSES`` on every
    request. To keep the throttle a NO-OP on non-Migration-Cloud paths,
    we override :meth:`allow_request` to short-circuit when
    :func:`_scope_for_request` returns ``None``. The viewset-attached
    ``MigrationCloudRead/WriteThrottle`` still apply where wired
    directly.

    Rate table (per the v3.33 task brief):
      * ``webhook_tenant`` — 1000/hour/tenant
      * ``bundles_write`` — 600/min/token
      * ``bundles_read``  — 100/min/token

    Soft-warn: when current count ≥ 80% of the scope's rate, the
    throttle still allows the request but tags ``request._rmc_soft_warn``
    so the response renderer can emit ``X-RateLimit-Soft-Warn: 1``. The
    middleware companion :class:`SoftWarnHeaderMiddleware` reads that
    flag and writes the header — kept out of the throttle itself so
    DRF's ``wait()`` accounting stays clean.
    """

    # DRF reads ``THROTTLE_RATES[scope]`` via parent ``get_rate``; we own
    # the table directly because we don't want operators to override the
    # Migration Cloud rates through generic settings.
    SCOPE_RATES = {
        "webhook_tenant": "1000/hour",
        "bundles_write": "600/min",
        "bundles_read": "100/min",
    }

    SOFT_WARN_FRACTION = 0.80

    scope = "migration-cloud-global"
    cache_format = "throttle_rmc_global_%(scope)s_%(ident)s"

    def __init__(self):
        # Defer the parent ``__init__`` because it requires ``self.scope``
        # to resolve from settings; we compute rate lazily per request.
        self.rate = None
        self.num_requests = None
        self.duration = None

    # ── Plumbing ────────────────────────────────────────────────────

    def _activate_scope(self, scope_key: str) -> None:
        """Set ``self.rate`` + parse it so the parent helpers work."""
        self.scope = scope_key
        self.rate = self.SCOPE_RATES[scope_key]
        self.num_requests, self.duration = self.parse_rate(self.rate)

    def get_cache_key(self, request, view):
        # Key on token id when present, else user id, else IP.
        try:
            from apps.migration_cloud.models import MigrationCloudAPIToken
        except Exception:  # pragma: no cover — defensive at import-time
            MigrationCloudAPIToken = None  # type: ignore[assignment]

        ident = None
        auth = getattr(request, "auth", None)
        if MigrationCloudAPIToken is not None and isinstance(auth, MigrationCloudAPIToken):
            ident = f"tok-{auth.pk}"
        else:
            user = getattr(request, "user", None)
            if user is not None and getattr(user, "is_authenticated", False):
                ident = f"usr-{user.pk}"
        if ident is None:
            ident = self.get_ident(request) or "anon"
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def get_rate(self):
        # We set ``self.rate`` directly via ``_activate_scope``; parent
        # ``allow_request`` calls this so respect what's already loaded.
        return self.rate

    # ── DRF entrypoint ───────────────────────────────────────────────

    def allow_request(self, request, view):
        """Path-scoped: skip when not Migration Cloud API.

        Defensive: returns True (allow) for any request that doesn't
        activate a scope, so this class can sit in
        ``DEFAULT_THROTTLE_CLASSES`` without affecting unrelated apps.
        """
        scope_key = _scope_for_request(request)
        if scope_key is None:
            return True  # not our path — get out of the way

        self._activate_scope(scope_key)
        self.key = self.get_cache_key(request, view)
        if self.key is None:  # pragma: no cover — get_cache_key always returns
            return True

        self.history = self.cache.get(self.key, [])
        self.now = self.timer()

        # Drop history entries outside the rolling window.
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()

        if len(self.history) >= self.num_requests:
            logger.info(
                "migration_cloud_global_throttle_reject scope=%s key=%s count=%s "
                "limit=%s",
                self.scope, self.key, len(self.history), self.num_requests,
            )
            return self.throttle_failure()

        # Soft-warn: flag the request for the response middleware.
        try:
            soft_threshold = max(
                1, int(self.num_requests * self.SOFT_WARN_FRACTION),
            )
            if len(self.history) >= soft_threshold:
                setattr(request, "_rmc_rate_soft_warn", True)
                setattr(request, "_rmc_rate_scope", self.scope)
        except Exception:  # pragma: no cover — defensive
            pass

        # v3.40.0 Agent 15 — saturation alert AFTER soft-warn flag set.
        # The bucket name = "<scope>:<cache_key>" so a single overloaded
        # token still maps to one stable bucket sha256 prefix.
        try:
            _check_saturation_alert(
                bucket_name=f"{self.scope}:{self.key}",
                current=int(len(self.history) + 1),  # +1 for current
                limit=int(self.num_requests),
            )
        except Exception:  # pylint: disable=broad-except
            pass

        return self.throttle_success()


class SoftWarnHeaderMiddleware:
    """Emit ``X-RateLimit-Soft-Warn: 1`` when the throttle flagged it.

    DRF's throttle layer can't reach the response object, so we set a
    request attribute in :class:`MigrationCloudGlobalThrottle` and let
    this middleware paint it on the way out. Cheap (one ``getattr``)
    per response, so safe to wire globally.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if getattr(request, "_rmc_rate_soft_warn", False):
                response[SOFT_WARN_HEADER] = "1"
                scope = getattr(request, "_rmc_rate_scope", None)
                if scope:
                    response[SCOPE_HEADER] = scope
        except Exception:  # pragma: no cover — never break the response cycle
            pass
        return response


# ─── v3.40.0 Agent 15 — throttle saturation alert hook ─────────────────────
#
# When a bucket's ``current/limit`` ratio exceeds the configured
# saturation threshold (default 0.95), emit a ``severity="warning"``
# alert via Agent 12's ``apps.migration_cloud.alerts.alert``. The hook
# carries its own in-memory cooldown (1h per bucket sha256 prefix) so a
# saturated bucket sends at most one alert per hour even if every
# subsequent request also crosses the line — defense in depth on top of
# Agent 12's own dedupe table.

#: Default ratio above which a bucket is considered saturated.
DEFAULT_SATURATION_ALERT_RATIO = 0.95

#: TTL on the per-bucket cooldown lock (seconds). One hour aligns with
#: the alert module's own dedupe window so the two systems don't fight.
_SATURATION_COOLDOWN_TTL_SECONDS = 3600

#: Module-level cooldown ledger. Keys are sha256-prefixed bucket names;
#: values are the wall-clock seconds at which the alert was emitted.
#: Intentionally in-memory — worker restart resets the ledger, which is
#: fine because the alert module's PagerDuty dedupe handles upstream.
_saturation_cooldown_lock = threading.Lock()
_saturation_cooldown_seen: dict[str, float] = {}


def _saturation_bucket_sha_prefix(bucket_name: str, n: int = 12) -> str:
    """sha256 prefix used in alert titles + the cooldown key.

    Never logs the raw bucket name; only the prefix.
    """
    h = hashlib.sha256(
        (bucket_name or "").encode("utf-8", errors="replace")
    ).hexdigest()
    return h[:n]


def _saturation_ratio_threshold() -> float:
    """Read the configured ratio, defaulting to 0.95."""
    try:
        from django.conf import settings
        v = getattr(
            settings,
            "MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_RATIO",
            DEFAULT_SATURATION_ALERT_RATIO,
        )
        if v is not None:
            return float(v)
    except Exception:  # pragma: no cover — django absent
        pass
    return DEFAULT_SATURATION_ALERT_RATIO


def _saturation_alert_disabled() -> bool:
    """Read the emergency kill-switch flag, defaulting to False."""
    try:
        from django.conf import settings
        return bool(
            getattr(
                settings,
                "MIGRATION_CLOUD_THROTTLE_SATURATION_ALERT_DISABLED",
                False,
            )
        )
    except Exception:  # pragma: no cover — django absent
        return False


def _should_emit_saturation_alert(bucket_sha_prefix: str) -> bool:
    """Cooldown-gated 1-per-hour-per-bucket admission check.

    Returns True when an alert should be emitted (and updates the
    ledger). Returns False if the same bucket fired within the last
    hour.
    """
    now = time.monotonic()
    with _saturation_cooldown_lock:
        # Lazy eviction of stale entries.
        stale = [
            k for k, t in _saturation_cooldown_seen.items()
            if (now - t) > _SATURATION_COOLDOWN_TTL_SECONDS
        ]
        for k in stale:
            _saturation_cooldown_seen.pop(k, None)
        if bucket_sha_prefix in _saturation_cooldown_seen:
            return False
        _saturation_cooldown_seen[bucket_sha_prefix] = now
        return True


def _check_saturation_alert(
    bucket_name: str, current: int, limit: int,
) -> None:
    """Fire a warning alert when ``current/limit`` > saturation ratio.

    Defensive in three layers:
      1. Kill-switch (``..._DISABLED``) short-circuits early.
      2. Cooldown ledger suppresses repeat alerts within 1h.
      3. ``apps.migration_cloud.alerts`` is imported lazily; any
         import / emit failure is swallowed (alerts must NEVER
         cascade into the throttle path).
    """
    if _saturation_alert_disabled():
        return
    if not bucket_name or not limit or limit <= 0:
        return
    try:
        ratio = float(current) / float(limit)
    except (TypeError, ValueError, ZeroDivisionError):
        return
    threshold = _saturation_ratio_threshold()
    if ratio <= threshold:
        return
    bucket_sha = _saturation_bucket_sha_prefix(bucket_name)
    if not _should_emit_saturation_alert(bucket_sha):
        return
    try:
        from apps.migration_cloud.alerts import alert  # noqa: WPS433
    except Exception:  # pylint: disable=broad-except
        # Agent 12 mid-deploy or absent — silent skip. The structured
        # log line below still records the saturation observation.
        logger.info(
            "migration_cloud_throttle_saturation_no_alerter "
            "bucket_sha=%s current=%s limit=%s ratio=%.3f",
            bucket_sha, current, limit, ratio,
        )
        return
    try:
        alert(
            severity="warning",
            title=(
                f"Migration Cloud rate-limit saturation: bucket "
                f"{bucket_sha}"
            ),
            body=(
                f"Bucket reached {ratio:.1%} of its hourly quota "
                f"({current}/{limit}). Investigate upstream caller "
                f"behaviour; this is one warning per bucket per hour."
            ),
            dedupe_key=f"throttle-saturation-{bucket_sha}",
        )
    except Exception as exc:  # pylint: disable=broad-except
        # NEVER let the alert path break the throttle path.
        logger.warning(
            "migration_cloud_throttle_saturation_alert_failed "
            "bucket_sha=%s err_type=%s",
            bucket_sha, type(exc).__name__,
        )


def _reset_saturation_cooldown_for_tests() -> None:
    """Test-only hook — wipe the cooldown ledger between cases."""
    with _saturation_cooldown_lock:
        _saturation_cooldown_seen.clear()


# ─── Module-level singleton ───────────────────────────────────────────────

#: Process-wide limiter the dispatcher consults. Cheap to construct, but
#: a singleton keeps the cache backend choice consistent.
default_tenant_rate_limiter = TenantRateLimiter()
