from django.conf import settings
from django.utils.functional import cached_property


class RoleBasedSessionTimeoutMiddleware:
    """
    Adjust session expiry based on the authenticated user's role so
    sensitive dashboards time out faster than less privileged ones.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.role_timeouts = getattr(settings, "ROLE_SESSION_TIMEOUTS", {})

    def __call__(self, request):
        self.apply_timeout(request)
        return self.get_response(request)

    def apply_timeout(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return

        timeout = self.role_timeouts.get(user.role, settings.SESSION_COOKIE_AGE)
        request.session.set_expiry(timeout)

