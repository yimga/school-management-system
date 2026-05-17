"""
v2.79 — request-lifecycle binding of the active tenant for the per-tenant
email backend.

`PerTenantEmailBackend` reads the active tenant from
`apps.integrations_marketplace.email_backend._active_school(...)`, which in
turn checks (in order):

    1. explicit `school=...` kwarg passed to the backend constructor
    2. thread-local set by this middleware
    3. None  (falls back to global Anymail / Django EMAIL_BACKEND)

Without this middleware step 2 never fires, so every email sent inside a
request still goes through the global provider, even when the tenant has
its own connector row configured. That's the bug v2.79 closed for the
*plumbing* but not for the *runtime* — this middleware closes the runtime
side.

Placement contract:
- Must run **after** `apps.schools.middleware.TenantMiddleware` (which sets
  `request.school`).
- Must run **before** any view that may send mail synchronously (so before
  any view middleware).
- The unbind in `process_response` is a belt-and-braces: thread pools in
  the dev server reuse threads, so a stale binding from request N would
  poison request N+1 if we didn't clear it.

Celery sends use a parallel hook in `celery_tenant_binding.py` (signal-based,
not middleware-based).
"""

from __future__ import annotations

from typing import Any

from apps.integrations_marketplace.email_backend import (
    bind_tenant_for_email,
    clear_tenant_for_email,
)


class TenantEmailBindingMiddleware:
    """Bind `request.school` into the email-backend thread-local for the life
    of the request. Always clears in `process_response` (and on exception via
    `process_exception`) so workers don't leak tenants across requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        school = getattr(request, "school", None)
        if school is not None:
            bind_tenant_for_email(school)
        try:
            response = self.get_response(request)
        finally:
            # Always clear — even on exception — so the next request on this
            # worker thread starts clean. The fallback resolver returns None
            # if nothing is bound, which is the safe default.
            clear_tenant_for_email()
        return response

    def process_exception(self, request, exception) -> Any:
        # Defense in depth — `__call__`'s try/finally already covers this,
        # but if a middleware *above* us re-raises after we've bound the
        # tenant, Django will skip our finally. process_exception is the
        # documented hook for that case.
        clear_tenant_for_email()
        return None


__all__ = ["TenantEmailBindingMiddleware"]
