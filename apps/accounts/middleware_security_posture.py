"""
Quarterly security posture review — one redirect per login session when review is due.
"""

from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.profile_security_evaluation import is_security_posture_review_due

SESSION_NAG_KEY = "security_posture_review_nagged"
EXEMPT_VIEW_NAMES = frozenset(
    {
        "accounts:security_posture_review",
        "accounts:logout",
        "accounts:login",
        "accounts:mfa_verify",
        "accounts:mfa_setup",
        "accounts:password_change",
        "accounts:password_change_done",
    }
)


class SecurityPostureReviewMiddleware:
    """Prompt users to complete quarterly security review (soft redirect once per session)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            getattr(user, "is_authenticated", False)
            and getattr(user, "pk", None)
            and not request.session.get(SESSION_NAG_KEY)
        ):
            match = getattr(request, "resolver_match", None)
            view_name = getattr(match, "view_name", None) if match else None
            if view_name not in EXEMPT_VIEW_NAMES:
                school = getattr(request, "school", None)
                if is_security_posture_review_due(user, school):
                    request.session[SESSION_NAG_KEY] = True
                    review_url = reverse("accounts:security_posture_review")
                    path = request.get_full_path()
                    if url_has_allowed_host_and_scheme(
                        path, allowed_hosts={request.get_host()}
                    ):
                        return redirect(f"{review_url}?next={path}")
                    return redirect(review_url)
        return self.get_response(request)
