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

# Mirror RequireMFAMiddleware's MFA-setup bypass (apps/accounts/middleware.py):
# the canonical MFA enrollment surface is the studio wizard at
# /school/studio/wizards/mfa_setup/ — accounts:mfa_setup is only a redirect
# shim. EXEMPT_VIEW_NAMES exempts that shim's view name but NOT the wizard view
# (setup_studio:tenant_wizard_step, which serves every step), so without a path
# check the quarterly nag interrupts a no-device owner mid-enrollment and
# ping-pongs them wizard -> security-review -> mfa/setup -> wizard. Match on the
# specific mfa_setup/mfa_verify path fragments so every OTHER page still nags.
_MFA_SETUP_PATH_FRAGMENTS = (
    "/mfa/setup",
    "/mfa/verify",
    "wizards/mfa_setup",
    "wizards/mfa_verify",
)


def _is_mfa_setup_path(path: str) -> bool:
    p = path or ""
    return any(frag in p for frag in _MFA_SETUP_PATH_FRAGMENTS)


class SecurityPostureReviewMiddleware:
    """Prompt users to complete quarterly security review (soft redirect once per session)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        # Disabled under the test runner (settings flag) so this cross-cutting
        # quarterly nag does not hijack the first authenticated request of every
        # unrelated test to the review page. See SECURITY_POSTURE_REVIEW_NAG_ENABLED.
        if not getattr(settings, "SECURITY_POSTURE_REVIEW_NAG_ENABLED", True):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if (
            getattr(user, "is_authenticated", False)
            and getattr(user, "pk", None)
            and not request.session.get(SESSION_NAG_KEY)
        ):
            match = getattr(request, "resolver_match", None)
            view_name = getattr(match, "view_name", None) if match else None
            if view_name not in EXEMPT_VIEW_NAMES and not _is_mfa_setup_path(
                getattr(request, "path", "") or ""
            ):
                school = getattr(request, "school", None)
                try:
                    review_due = is_security_posture_review_due(user, school)
                except Exception:
                    # Policy resolver touches RuntimeDefaults; schema drift during deploy
                    # must not block login → dashboard with a 500.
                    review_due = False
                if review_due:
                    request.session[SESSION_NAG_KEY] = True
                    review_url = reverse("accounts:security_posture_review")
                    path = request.get_full_path()
                    if url_has_allowed_host_and_scheme(
                        path, allowed_hosts={request.get_host()}
                    ):
                        return redirect(f"{review_url}?next={path}")
                    return redirect(review_url)
        return self.get_response(request)
