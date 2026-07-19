"""Scoped, tenant-aware DRF throttles for the public ``apps.api`` REST surface.

These classes are **self-contained** — each owns its own rate in the
:data:`SCOPE_RATES` table rather than reading DRF's
``DEFAULT_THROTTLE_RATES`` from ``config/settings.py``. That keeps abuse +
fairness limits on the public API entirely inside ``apps/api`` (the
shared ``settings.py`` ``DEFAULT_THROTTLE_CLASSES`` is owned by the
Migration Cloud path-scoped throttle and is intentionally left untouched).

Design (mirrors the established pattern in
``apps/migration_cloud/api/rate_limiting.py``):

  * **Tenant-aware key.** The cache key is composed
    ``<scope>:<tenant>:<ident>`` so one tenant's burst can never exhaust
    another tenant's quota. ``tenant`` is the active ``request.school`` pk
    when set (the platform's tenant context), falling back to a stable
    ``global`` bucket for cross-tenant / pre-tenant surfaces. ``ident``
    is the user pk for authenticated callers, else the
    XFF-spoofing-resistant client IP.
  * **Read / write / public split.** Four scopes with sane rates so an
    interactive read flood and a write flood are budgeted independently,
    and the unauthenticated catalog surface (the open abuse surface) gets
    its own conservative per-IP budget.
  * **Soft-warn header.** When a caller crosses 80% of the scope's rate
    the throttle still allows the request but stamps
    ``request._rmc_api_rate_soft_warn`` + ``_rmc_api_rate_scope``; the
    companion :class:`ApiSoftWarnHeaderMixin` paints
    ``X-RateLimit-Soft-Warn: 1`` + ``X-RateLimit-Scope`` on the response
    so consumers can back off before they get a 429. The flag-then-paint
    split keeps DRF's ``wait()`` accounting clean (the throttle layer
    can't reach the response object).

No PII / secret material is ever logged: the soft-warn / reject log lines
carry the scope + numeric counts + an opaque ``sha1[:12]`` of the cache
key, never the raw key (which embeds the user pk / IP).
"""

from __future__ import annotations

import hashlib
import logging

from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


# ── Scope rates ─────────────────────────────────────────────────────────────
#
# Owned here on purpose — operators do NOT override the public-API abuse
# budget through generic ``settings.DEFAULT_THROTTLE_RATES``. Reads are
# generous (interactive dashboards page through cursor-paginated lists);
# writes are tighter (mutations are rarer + more expensive); the public
# unauthenticated catalog is the open abuse surface so it gets the most
# conservative per-IP budget.

#: Authenticated safe-method (GET/HEAD/OPTIONS) rate, per user per tenant.
API_READ_RATE = "600/min"

#: Authenticated unsafe-method (POST/PUT/PATCH/DELETE) rate.
API_WRITE_RATE = "120/min"

#: Unauthenticated public-catalog read rate, per client IP.
API_PUBLIC_READ_RATE = "60/min"

#: Authenticated marketplace-submission (publisher write) rate — deliberately
#: low; a publisher submitting hundreds of draft apps a minute is abuse.
API_SUBMISSION_RATE = "30/min"

#: Global BACKSTOP rates. These are not this API's real budget — the scoped
#: rates above are. They exist because ``DEFAULT_THROTTLE_CLASSES`` previously
#: held only the Migration Cloud path-scoped throttle, whose ``allow_request``
#: returns True for any path outside ``/migration/api/v1/``. The net effect: a
#: DRF view that forgot to declare ``throttle_classes`` was completely
#: UNTHROTTLED while the settings block looked like it had a blanket throttle.
#: These are deliberately generous — high enough that no legitimate caller ever
#: notices, low enough to blunt a runaway loop or a scripted abuser. A view with
#: explicit ``throttle_classes`` overrides these entirely (DRF replaces, not
#: merges), so the tighter scoped budgets above are never loosened by them.
API_BACKSTOP_USER_RATE = "1200/min"
API_BACKSTOP_ANON_RATE = "120/min"

#: Fraction of the rate at which the soft-warn header starts being emitted.
SOFT_WARN_FRACTION = 0.80

#: Response headers (mirror the migration_cloud soft-warn contract names).
SOFT_WARN_HEADER = "X-RateLimit-Soft-Warn"
SCOPE_HEADER = "X-RateLimit-Scope"


def _key_digest(key: str) -> str:
    """Opaque, PII-free fingerprint of a cache key for log lines."""
    # Log fingerprint only — not auth/crypto material.
    return hashlib.sha1(
        (key or "").encode("utf-8", "replace"),
        usedforsecurity=False,
    ).hexdigest()[:12]


def _tenant_bucket(request) -> str:
    """Stable per-tenant bucket fragment for the cache key.

    Uses the active tenant (``request.school``) pk when the platform's
    tenant middleware has resolved one, so one school's traffic is
    budgeted independently of another's. Cross-tenant / pre-tenant
    surfaces share a single ``global`` bucket — acceptable because those
    are also keyed by ``ident`` (user pk / IP) below.
    """
    school = getattr(request, "school", None)
    pk = getattr(school, "pk", None)
    if pk:
        return f"t{pk}"
    return "global"


class _ApiScopedThrottleBase(SimpleRateThrottle):
    """Base for the apps.api scoped throttles.

    Subclasses set :attr:`scope` and :attr:`rate`. The base owns the
    tenant-aware cache key + the soft-warn flagging, and short-circuits to
    "allow" when it cannot resolve an identity (defense-in-depth — never
    hard-fail a request because the throttle couldn't key it).
    """

    cache_format = "throttle_api_%(scope)s_%(ident)s"

    #: Set to True on subclasses that should only throttle ANONYMOUS
    #: callers (the public catalog). Authenticated traffic on those
    #: endpoints is then governed by the per-user read throttle instead.
    anon_only = False

    #: Set to True on subclasses that should only throttle AUTHENTICATED
    #: callers. Lets a public endpoint pair a per-IP anon throttle with a
    #: per-user authenticated throttle without double-counting anon hits.
    auth_only = False

    def __init__(self):
        # ``rate`` is a class attribute on every concrete subclass, so the
        # parent ``__init__`` parses it without consulting settings.
        super().__init__()

    def get_rate(self):
        # Defensive: every concrete subclass sets ``rate`` directly, so the
        # parent never falls through to the settings-driven lookup. This
        # override means a misconfigured subclass returns ``None`` (allow)
        # instead of raising ImproperlyConfigured at request time.
        return getattr(self, "rate", None)

    def _ident(self, request) -> str | None:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return f"u{user.pk}"
        ip = self.get_ident(request)
        return f"ip{ip}" if ip else None

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        is_auth = user is not None and getattr(user, "is_authenticated", False)
        if self.anon_only and is_auth:
            return None  # only throttle anonymous callers on this scope
        if self.auth_only and not is_auth:
            return None  # only throttle authenticated callers on this scope
        ident = self._ident(request)
        if ident is None:  # pragma: no cover — defensive; allow request
            return None
        composite = f"{_tenant_bucket(request)}:{ident}"
        return self.cache_format % {"scope": self.scope, "ident": composite}

    def allow_request(self, request, view):
        if self.rate is None:  # pragma: no cover — misconfigured subclass
            return True

        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True

        self.history = self.cache.get(self.key, [])
        self.now = self.timer()

        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()

        if len(self.history) >= self.num_requests:
            logger.info(
                "api_throttle_reject scope=%s key_sha=%s count=%s limit=%s",
                self.scope, _key_digest(self.key), len(self.history),
                self.num_requests,
            )
            return self.throttle_failure()

        # Soft-warn: flag the request for the response mixin BEFORE we add
        # this request to the history so the threshold is measured against
        # already-consumed budget.
        try:
            soft_threshold = max(1, int(self.num_requests * SOFT_WARN_FRACTION))
            if len(self.history) + 1 >= soft_threshold:
                setattr(request, "_rmc_api_rate_soft_warn", True)
                setattr(request, "_rmc_api_rate_scope", self.scope)
                logger.info(
                    "api_throttle_soft_warn scope=%s key_sha=%s count=%s "
                    "limit=%s",
                    self.scope, _key_digest(self.key), len(self.history) + 1,
                    self.num_requests,
                )
        except (TypeError, ValueError):  # pragma: no cover — defensive
            pass

        return self.throttle_success()


class ApiReadThrottle(_ApiScopedThrottleBase):
    """Authenticated safe-method read throttle (per user, per tenant).

    Only counts authenticated callers, so it can be safely paired with
    :class:`ApiPublicReadThrottle` on a public endpoint (anon hits go to
    the per-IP public throttle; authenticated hits go here) without
    double-counting.
    """

    scope = "api-v1-read"
    rate = API_READ_RATE
    auth_only = True


class ApiWriteThrottle(_ApiScopedThrottleBase):
    """Authenticated unsafe-method write throttle (per user, per tenant)."""

    scope = "api-v1-write"
    rate = API_WRITE_RATE


class ApiReadWriteThrottle(_ApiScopedThrottleBase):
    """Method-aware throttle for viewsets that mix reads + writes.

    A single class so a ModelViewSet can list ONE throttle and still have
    its writes budgeted separately from its reads — it switches scope +
    rate per request based on the HTTP method's safety.
    """

    scope = "api-v1-read"
    rate = API_READ_RATE

    def allow_request(self, request, view):
        method = (getattr(request, "method", "") or "").upper()
        if method in ("GET", "HEAD", "OPTIONS"):
            self.scope = ApiReadThrottle.scope
            self.rate = ApiReadThrottle.rate
        else:
            self.scope = ApiWriteThrottle.scope
            self.rate = ApiWriteThrottle.rate
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)


class ApiPublicReadThrottle(_ApiScopedThrottleBase):
    """Per-IP throttle for unauthenticated public catalog endpoints.

    Only anonymous callers are throttled here; authenticated traffic on
    the same endpoints falls under :class:`ApiReadThrottle` instead so a
    logged-in user is not double-counted.
    """

    scope = "api-v1-public-read"
    rate = API_PUBLIC_READ_RATE
    anon_only = True


class ApiSubmissionThrottle(_ApiScopedThrottleBase):
    """Tight throttle for the authenticated publisher-submission write."""

    scope = "api-v1-submission"
    rate = API_SUBMISSION_RATE


class DefaultBackstopUserThrottle(_ApiScopedThrottleBase):
    """Global backstop for AUTHENTICATED DRF views with no explicit throttle.

    Paired with :class:`DefaultBackstopAnonThrottle` in
    ``settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]``. ``auth_only`` keeps
    the two from double-counting the same request.
    """

    scope = "rmc-backstop-user"
    rate = API_BACKSTOP_USER_RATE
    auth_only = True


class DefaultBackstopAnonThrottle(_ApiScopedThrottleBase):
    """Global backstop for ANONYMOUS DRF traffic (per client IP, per tenant).

    The open abuse surface, so a tighter budget than the authenticated backstop.
    """

    scope = "rmc-backstop-anon"
    rate = API_BACKSTOP_ANON_RATE
    anon_only = True


class ApiSoftWarnHeaderMixin:
    """View mixin that paints the soft-warn headers set by the throttles.

    Mix into any APIView / ViewSet whose throttles can set
    ``request._rmc_api_rate_soft_warn`` so consumers see
    ``X-RateLimit-Soft-Warn: 1`` + ``X-RateLimit-Scope`` once they cross
    80% of a scope's budget — and can back off before the 429.

    Implemented via DRF's ``finalize_response`` (the throttle layer can't
    reach the response object). Never raises into the response cycle.
    """

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        try:
            raw = getattr(request, "_request", request)
            flagged = getattr(request, "_rmc_api_rate_soft_warn", False) or getattr(
                raw, "_rmc_api_rate_soft_warn", False
            )
            if flagged:
                response[SOFT_WARN_HEADER] = "1"
                scope = getattr(request, "_rmc_api_rate_scope", None) or getattr(
                    raw, "_rmc_api_rate_scope", None
                )
                if scope:
                    response[SCOPE_HEADER] = scope
        except (AttributeError, TypeError):  # pragma: no cover — defensive
            pass
        return response
