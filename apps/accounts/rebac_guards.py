"""ReBAC enforcement helpers for sensitive tenant APIs."""

from __future__ import annotations

import functools

from django.core.exceptions import PermissionDenied


def require_rebac_permission(code: str):
    """
    Both colon RBAC and ReBAC ``can`` must pass when ``RMC_REBAC_ENFORCE_SENSITIVE`` is on.
    RBAC alone is sufficient when enforce flag is off (dual-run logs only via model method).
    """

    def decorator(view_fn):
        @functools.wraps(view_fn)
        def wrapped(request, *args, **kwargs):
            user = getattr(request, "user", None)
            school = getattr(request, "school", None)
            if user is None or not user.is_authenticated:
                raise PermissionDenied("authentication_required")
            from apps.accounts.drf_rebac import school_from_request
            from apps.accounts.rebac import enforce_permission_token

            if school is None:
                school = school_from_request(request)
            if not enforce_permission_token(user, code, school=school):
                raise PermissionDenied("rebac_permission_denied")
            return view_fn(request, *args, **kwargs)

        return wrapped

    return decorator
