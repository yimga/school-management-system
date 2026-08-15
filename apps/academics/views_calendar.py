"""Academic-calendar confirm action (increment r).

A one-click POST that lets a tenant admin attest their (representative) term dates
are correct for the school — clearing the confirm-before-go-live advisory raised by
:func:`apps.academics.academic_calendar.needs_calendar_confirmation`. The dates stay
fully editable afterward; confirming is an attestation, not a lock.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import NoReverseMatch, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.academics.academic_calendar import confirm_calendar
from apps.accounts.decorators import tenant_admin_required

logger = logging.getLogger(__name__)


def _safe_redirect_target(request) -> str:
    """Same-host redirect from ?next / referer (open-redirect guarded), else the hub."""
    candidate = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    try:
        return reverse("academics:hub")
    except NoReverseMatch:
        return "/"


@require_POST
@tenant_admin_required
def confirm_academic_calendar(request):
    """Confirm the school's representative term-date calendar (tenant-admin only)."""
    school = getattr(request, "school", None)
    if school is None:
        messages.error(request, _("No school in context."))
        return HttpResponseRedirect(_safe_redirect_target(request))
    try:
        confirm_calendar(school, request.user)
        messages.success(request, _("Term dates confirmed. You can still edit them anytime."))
    except Exception:  # noqa: BLE001 — a confirm click must never 500
        logger.exception("confirm_academic_calendar failed for school=%s", getattr(school, "pk", None))
        messages.error(request, _("Could not confirm term dates. Please try again."))
    return HttpResponseRedirect(_safe_redirect_target(request))
