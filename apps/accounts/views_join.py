"""Public self-service school join — redeem a SchoolJoinCode and register.

Anonymous-reachable on the tenant host: a prospective parent/teacher/staff member
enters a code the school shared, provides their name + email + password, and lands
signed in. Distinct from the admin invite/provisioning flows (those are staff-gated).
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "POST"])
def join_school(request):
    # rbac-allow: public self-service school join by a shareable, revocable code
    from apps.accounts.join_codes import (
        JoinCodeError,
        redeem_join_code,
        resolve_join_code,
    )

    school = getattr(request, "school", None)

    if request.method == "POST":
        code = (request.POST.get("code") or "").strip().upper()
        password = request.POST.get("password") or ""
        ctx = {
            "school": school,
            "prefill_code": code,
            "form_email": (request.POST.get("email") or "").strip(),
            "form_first": (request.POST.get("first_name") or "").strip(),
            "form_last": (request.POST.get("last_name") or "").strip(),
        }
        try:
            user = redeem_join_code(
                code=code,
                email=request.POST.get("email") or "",
                password=password,
                first_name=request.POST.get("first_name") or "",
                last_name=request.POST.get("last_name") or "",
                school=school,
            )
        except JoinCodeError as exc:
            messages.error(request, str(exc))
            return render(request, "accounts/join_school.html", ctx)

        auth_user = authenticate(request, username=user.username, password=password)
        if auth_user is not None:
            login(request, auth_user)
            # Same contract as login_view: the MFA decision belongs to
            # resolve_post_login_mfa_redirect, not to whichever view happened to
            # call login(). RequireMFAMiddleware only walls users with NO device,
            # so leaving it to the middleware makes the policy depend on the
            # sign-in door.
            from apps.accounts.post_login_mfa import resolve_post_login_mfa_redirect

            mfa_resp = resolve_post_login_mfa_redirect(request, auth_user)
            if mfa_resp is not None:
                return mfa_resp
            messages.success(request, _("Welcome! Your account is ready."))
            return redirect("accounts:backend_dashboard")
        # Account created but auto-login unavailable — send them to sign in.
        messages.success(
            request, _("Your account is ready — please sign in with your new password.")
        )
        return redirect("accounts:login")

    prefill_code = (request.GET.get("code") or "").strip().upper()
    resolved = resolve_join_code(prefill_code, school=school) if prefill_code else None
    return render(
        request,
        "accounts/join_school.html",
        {"school": school, "prefill_code": prefill_code, "resolved": resolved},
    )
