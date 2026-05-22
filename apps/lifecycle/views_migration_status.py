"""Tenant-facing per-school migration status page.

URL: /portal/migration/status/

Renders a granular progress view for the current tenant's bundles.
Closes audit gap: tenants previously had only /customer/intake_status/
which was binary (complete / not), no granular progress.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .services_migration import tenant_status_snapshot

logger = logging.getLogger(__name__)


def _resolve_school(request):
    school = (
        getattr(request, "school", None)
        or getattr(request, "tenant_school", None)
        or getattr(request, "tenant", None)
    )
    if school and hasattr(school, "id"):
        return school
    return None


@login_required
@require_GET
def tenant_migration_status(request):
    school = _resolve_school(request)
    if school is None:
        return HttpResponseForbidden("No tenant context resolved.")
    snapshot = tenant_status_snapshot(school)
    return render(
        request,
        "lifecycle/migration_status.html",
        {
            "school": school,
            "snapshot": snapshot,
        },
    )
