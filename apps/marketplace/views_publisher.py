"""
Pass 14.D: publisher dashboard — operator UI on top of the 14.C submission
endpoint.

GET /super/marketplace/publisher/  → list every app belonging to the requester's
PublisherOrganization with status + review-status + last-updated.
GET /super/marketplace/publisher/<slug>/  → detail page with the manifest + review
notes + (when set) the security review queue link.

Auth: control-plane operators only (manager host + SUPERADMIN / is_superuser).
Publisher accounts are platform identities, not tenant identities — these
surfaces render on manager.<base>, never on a school subdomain.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.schools.control_plane import require_super_access_with_host


def _publisher_for_user(user):
    try:
        from apps.marketplace.models import PublisherOrganization
    except ImportError:
        return None
    if not user.email:
        return None
    return PublisherOrganization.objects.filter(
        verified_contact_email=user.email
    ).first()


@require_super_access_with_host
@require_GET
def publisher_dashboard(request):
    publisher = _publisher_for_user(request.user)
    apps = []
    summary = None
    per_app_rows = []
    if publisher is not None:
        try:
            from apps.marketplace.models import MarketplaceApp

            apps = list(
                MarketplaceApp.objects.filter(publisher=publisher)
                .select_related("listing", "publisher")
                .order_by("name")
            )
        except ImportError:
            apps = []
        try:
            from apps.marketplace import partner_metrics

            summary = partner_metrics.metrics_for_publisher(publisher)
            per_app_rows = partner_metrics.per_app_metrics(publisher)
        except ImportError:
            summary = None
            per_app_rows = []
    return render(
        request,
        "marketplace/publisher_dashboard.html",
        {
            "publisher": publisher,
            "apps": apps,
            "no_publisher": publisher is None,
            "metrics_summary": summary,
            "per_app_metrics": per_app_rows,
        },
    )


@require_super_access_with_host
@require_GET
def publisher_app_detail(request, slug: str):
    publisher = _publisher_for_user(request.user)
    try:
        from apps.marketplace.models import MarketplaceApp
    except ImportError:
        return render(request, "marketplace/publisher_dashboard.html", {"apps": [], "no_publisher": True})
    app = get_object_or_404(MarketplaceApp, slug=slug)
    if publisher is None or app.publisher_id != publisher.pk:
        # Hide the existence of other publishers' apps from non-owners.
        from django.http import Http404

        raise Http404("Not your app.")
    return render(
        request,
        "marketplace/publisher_app_detail.html",
        {
            "app": app,
            "listing": getattr(app, "listing", None),
            "publisher": publisher,
        },
    )
