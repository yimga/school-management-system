"""Rate-limited JWT auth views for public API authentication endpoints."""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.api.rate_limit import throttle_ip_request


class _RateLimitedJwtMixin:
    rate_limit_scope = "api_auth"
    rate_limit_max = 20
    rate_limit_window = 60

    def _rate_limit_denied_response(self, retry_after: int):
        return Response(
            {
                "detail": "Too many authentication requests. Try again later.",
                "retry_after": int(retry_after),
            },
            status=429,
        )

    def _check_rate_limit(self, request):
        raw_request = getattr(request, "_request", request)
        return throttle_ip_request(
            raw_request,
            scope=self.rate_limit_scope,
            max_count=self.rate_limit_max,
            window_seconds=self.rate_limit_window,
        )


class RateLimitedTokenObtainPairView(_RateLimitedJwtMixin, TokenObtainPairView):
    rate_limit_scope = "api_auth:token_obtain"
    rate_limit_max = 20
    rate_limit_window = 60

    def post(self, request, *args, **kwargs):
        allowed, retry_after = self._check_rate_limit(request)
        if not allowed:
            return self._rate_limit_denied_response(retry_after)
        return super().post(request, *args, **kwargs)


class RateLimitedTokenRefreshView(_RateLimitedJwtMixin, TokenRefreshView):
    rate_limit_scope = "api_auth:token_refresh"
    rate_limit_max = 60
    rate_limit_window = 60

    def post(self, request, *args, **kwargs):
        allowed, retry_after = self._check_rate_limit(request)
        if not allowed:
            return self._rate_limit_denied_response(retry_after)
        return super().post(request, *args, **kwargs)
