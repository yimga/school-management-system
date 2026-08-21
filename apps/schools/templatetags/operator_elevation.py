"""Explain why an operator was bounced off a tenant host.

``TenantHostControlPlaneIsolationMiddleware`` confines platform operators to the
signed impersonation flow: land on a tenant host without a live session and you
are redirected to the manager host. That redirect used to be *silent*. An
operator clicked a tenant link, found themselves on /super/, and had nothing to
read — which is worse than a wrong message, because the obvious inference is
"I do not have permission", and that is not what happened.

What actually happened is the control this platform should be proudest of.
Reaching tenant data is not refused; it is *recorded*. Root on Linux is still
logged by sudo, and Administrator on Windows is still written to the Security
log — god-mode decides what you may do, never whether it is written down. So
the banner names the tenant and offers the audited way in, rather than
apologising for a permission that is not missing.

The middleware sends only the school pk (``?elevate=<pk>``). The name is
resolved HERE, from the database, so nothing a query string says is ever
rendered as a tenant's identity.
"""

from __future__ import annotations

import logging

from django import template
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)

register = template.Library()

#: Query parameter the isolation middleware sets on its redirect.
ELEVATE_PARAM = "elevate"


def _school_from_request(request):
    raw = (request.GET.get(ELEVATE_PARAM) or "").strip()
    if not raw:
        return None
    from apps.schools.models import School

    try:
        return School.objects.filter(pk=raw).only("id", "name", "subdomain").first()
    except (DatabaseError, ValidationError, ValueError, TypeError) as exc:
        # School.pk is a UUID, so anything that is not one raises ValidationError
        # at the field layer rather than returning an empty queryset. A junk
        # query string renders no banner; it never renders a traceback.
        logger.debug("elevation banner: school lookup failed for %r: %s", raw, exc)
        return None


@register.inclusion_tag(
    "schools/partials/_elevation_required_banner.html", takes_context=True
)
def elevation_required_banner(context):
    """Render the "elevation required" notice, or nothing at all."""
    request = context.get("request")
    if request is None or not getattr(request, "GET", None):
        return {"show": False}
    school = _school_from_request(request)
    if school is None:
        return {"show": False}
    try:
        picker_url = reverse("assist_dock:impersonation_picker")
    except NoReverseMatch:
        picker_url = None
    return {"show": True, "school": school, "picker_url": picker_url}
