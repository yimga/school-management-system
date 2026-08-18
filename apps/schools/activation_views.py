"""
First-login activation landing: links to operational surfaces until first value is recorded.
Bypass-only dismissal removed — completion is via explicit domain signals (conversion_lock_state).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User


# v4.00.2 audit — canonical SOT for the activation landing path. Both
# ``config/urls.py`` and ``config/tenant_urls.py`` register this exact path
# under name ``activation_first_action``; the activation gate and
# conversion lock middleware import it as a literal fallback for any
# request where ``reverse("activation_first_action")`` can't resolve
# (worker loaded URL resolver pre-deploy, override_settings(ROOT_URLCONF=...)
# in tests, etc.). Change here propagates to every reference site.
ACTIVATION_FIRST_ACTION_PATH = "/activation/first-action/"
ACTIVATION_FIRST_ACTION_URL_NAME = "activation_first_action"


def _reachable(url: str) -> bool:
    """Would the conversion lock let this landing page's own CTA through?

    This page exists BECAUSE the lock is on, so any CTA it renders that the lock
    refuses is a guaranteed 302 straight back here — the operator clicks, the page
    "buffers", and nothing happens. Every candidate below is filtered through the
    same allowlist the middleware enforces, so the advertised action and the gate
    can never disagree again.
    """
    if not url or url == "/":
        return False
    try:
        from apps.schools.conversion_lock_paths import conversion_allows_path
    except ImportError:
        return True
    return conversion_allows_path(url)


def _first_reachable(*candidates: str) -> str:
    for candidate in candidates:
        if _reachable(candidate):
            return candidate
    return ""


def _primary_action_url(
    request: HttpRequest, portal_take_url: str, marks_url: str, backend_url: str
) -> str:
    role = getattr(request.user, "role", None)
    role_first = ""
    try:
        if role == User.Role.TEACHER:
            role_first = reverse("portal:teacher_attendance")
        elif role == User.Role.PARENT:
            role_first = reverse("portal:parent_dashboard")
    except NoReverseMatch:
        role_first = ""

    chosen = _first_reachable(role_first, portal_take_url, marks_url, backend_url)
    if chosen:
        return chosen
    # Nothing on the allowlist resolved — keep the legacy ordering rather than
    # rendering an empty href, so the page still degrades to a real link.
    if role_first:
        return role_first
    if portal_take_url and portal_take_url != "/":
        return portal_take_url
    if marks_url and marks_url != "/":
        return marks_url
    return backend_url


@login_required
@require_http_methods(["GET"])
def activation_first_action(request: HttpRequest):
    """Explain the gate and link to operational surfaces."""
    try:
        from apps.lifecycle.tenant_school_resolve import resolve_request_school

        school = resolve_request_school(request)
    except ImportError:
        school = getattr(request, "school", None)
    if school is None:
        # When no tenant context can be resolved (manager host, superuser with
        # no membership, etc.) we render the page with neutral links rather
        # than redirecting to "home" — the activation/conversion gates would
        # bounce "/" right back here and produce a redirect cycle.
        return render(
            request,
            "schools/activation_first_action.html",
            {
                "backend_url": "/",
                "portal_take_url": "/",
                "marks_url": "/",
                "primary_action_url": "/",
                "activation_choices": [],
                "school_name": "",
                "activation_single_action": getattr(
                    settings, "CONVERSION_SINGLE_ACTION_ENFORCED", False
                ),
            },
        )

    backend_url = "/"
    portal_take_url = "/"
    marks_url = "/"
    try:
        backend_url = reverse("accounts:backend_dashboard")
    except NoReverseMatch:
        pass
    try:
        portal_take_url = reverse("portal:take_student_attendance")
    except NoReverseMatch:
        pass
    try:
        marks_url = reverse("evals:teacher_marks_entry")
    except NoReverseMatch:
        pass

    primary_action_url = _primary_action_url(
        request, portal_take_url, marks_url, backend_url
    )

    # The multi-link variant used to offer "Open operator dashboard" unconditionally,
    # but /authentication/backend/ is on the strict lock's explicit DENY list — the
    # link could only ever bounce back here. Offer the choices the gate actually
    # honours, and never render a zero-choice list.
    activation_choices = [
        choice
        for choice in (
            {"label": _("Take attendance"), "url": portal_take_url},
            {"label": _("Enter marks"), "url": marks_url},
            {"label": _("Open operator dashboard"), "url": backend_url},
        )
        if _reachable(choice["url"])
    ]
    if not activation_choices and primary_action_url:
        activation_choices = [
            {"label": _("Do your next action"), "url": primary_action_url}
        ]

    return render(
        request,
        "schools/activation_first_action.html",
        {
            "backend_url": backend_url,
            "portal_take_url": portal_take_url,
            "marks_url": marks_url,
            "activation_choices": activation_choices,
            "primary_action_url": primary_action_url,
            "school_name": getattr(school, "name", "") or "",
            "activation_single_action": getattr(
                settings, "CONVERSION_SINGLE_ACTION_ENFORCED", False
            ),
        },
    )


def activation_gate_enabled() -> bool:
    return not getattr(settings, "DISABLE_SCHOOL_ACTIVATION_GATE", False)
