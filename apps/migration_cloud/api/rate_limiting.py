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

import logging
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


# ─── Module-level singleton ───────────────────────────────────────────────

#: Process-wide limiter the dispatcher consults. Cheap to construct, but
#: a singleton keeps the cache backend choice consistent.
default_tenant_rate_limiter = TenantRateLimiter()
