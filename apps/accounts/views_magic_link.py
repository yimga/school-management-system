"""Passwordless sign-in views: request a link, and consume it."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "POST"])
def magic_link_request(request):
    # rbac-allow: passwordless sign-in request page must be anonymous-reachable
    from apps.accounts.magic_link import request_magic_link

    if request.user.is_authenticated:
        return redirect("accounts:backend_dashboard")
    if request.method == "POST":
        request_magic_link(
            request.POST.get("email") or "",
            school=getattr(request, "school", None),
            request=request,
        )
        # Always generic — never reveal whether the account exists.
        messages.success(
            request,
            _(
                "If an account matches that email, we've sent a sign-in link. "
                "Check your inbox — it expires shortly."
            ),
        )
        return redirect("accounts:magic_link_request")
    return render(request, "accounts/magic_link_request.html", {})


@require_http_methods(["GET"])
def magic_link_login(request, token):
    # rbac-allow: passwordless sign-in consume link must be anonymous-reachable
    from apps.accounts.magic_link import consume_magic_link

    user = consume_magic_link(token, school=getattr(request, "school", None))
    if user is None:
        messages.error(
            request,
            _("That sign-in link is invalid or has expired. Request a new one."),
        )
        return redirect("accounts:magic_link_request")
    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    # RequireMFAMiddleware does NOT cover an enrolled user: resolve_mfa_enforcement
    # returns "none" the moment the account has a confirmed device, and the
    # middleware never inspects session["mfa_verified"]. So a bursar with TOTP who
    # arrived through the mailbox got a fully privileged session with no code ever
    # requested. resolve_post_login_mfa_redirect is the only thing that issues the
    # challenge — call it here exactly as login_view does.
    from apps.accounts.post_login_mfa import resolve_post_login_mfa_redirect

    mfa_resp = resolve_post_login_mfa_redirect(request, user)
    if mfa_resp is not None:
        return mfa_resp
    messages.success(request, _("You're signed in."))
    return redirect("accounts:backend_dashboard")
