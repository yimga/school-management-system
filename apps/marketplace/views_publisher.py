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

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.marketplace.publisher_access import (
    publisher_for_user,
    require_verified_publisher_with_host,
)


@require_verified_publisher_with_host
@require_GET
def publisher_dashboard(request):
    publisher = publisher_for_user(request.user)
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


@require_verified_publisher_with_host
@require_GET
def publisher_app_detail(request, slug: str):
    publisher = publisher_for_user(request.user)
    try:
        from apps.marketplace.models import MarketplaceApp
    except ImportError:
        return render(request, "marketplace/publisher_dashboard.html", {"apps": [], "no_publisher": True})
    app = get_object_or_404(MarketplaceApp, slug=slug)
    if publisher is None or app.publisher_id != publisher.pk:
        # Hide the existence of other publishers' apps from non-owners.
        from django.http import Http404

        raise Http404("Not your app.")
    listing = getattr(app, "listing", None)
    can_submit = False
    try:
        from apps.marketplace.models import MarketplaceListing

        can_submit = bool(
            listing and listing.status == MarketplaceListing.Status.DRAFT
        )
    except ImportError:
        pass
    return render(
        request,
        "marketplace/publisher_app_detail.html",
        {
            "app": app,
            "listing": listing,
            "publisher": publisher,
            "can_submit_for_review": can_submit,
        },
    )


@require_verified_publisher_with_host
@require_http_methods(["POST"])
def publisher_submit_for_review(request, slug: str):
    publisher = publisher_for_user(request.user)
    try:
        from apps.marketplace.models import MarketplaceApp
        from apps.marketplace.partner_submission import submit_for_review
    except ImportError:
        messages.error(request, "Marketplace is unavailable.")
        return redirect(reverse("super:marketplace_publisher_dashboard"))
    app = get_object_or_404(MarketplaceApp, slug=slug)
    if publisher is None or app.publisher_id != publisher.pk:
        raise Http404("Not your app.")
    submit_for_review(app, requested_by=request.user)
    messages.success(request, "App submitted for security review.")
    return redirect("super:marketplace_publisher_app_detail", slug=slug)
