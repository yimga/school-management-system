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


def _primary_action_url(
    request: HttpRequest, portal_take_url: str, marks_url: str, backend_url: str
) -> str:
    role = getattr(request.user, "role", None)
    try:
        if role == User.Role.TEACHER:
            return reverse("portal:teacher_attendance")
        if role == User.Role.PARENT:
            return reverse("portal:parent_dashboard")
    except NoReverseMatch:
        pass
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

    return render(
        request,
        "schools/activation_first_action.html",
        {
            "backend_url": backend_url,
            "portal_take_url": portal_take_url,
            "marks_url": marks_url,
            "primary_action_url": primary_action_url,
            "school_name": getattr(school, "name", "") or "",
            "activation_single_action": getattr(
                settings, "CONVERSION_SINGLE_ACTION_ENFORCED", False
            ),
        },
    )


def activation_gate_enabled() -> bool:
    return not getattr(settings, "DISABLE_SCHOOL_ACTIVATION_GATE", False)
