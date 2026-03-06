from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.billing.models import RevenueSharePayout
from apps.marketplace.models import MarketplaceApp, MarketplaceListing, MarketplaceReview, PublisherOrganization
from apps.marketplace.services import finalize_marketplace_review, submit_marketplace_review


def _control_plane_access(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(user.is_superuser or user.is_staff or (getattr(user, "role", "") or "").upper() == "SUPERADMIN")


@login_required
@user_passes_test(_control_plane_access)
def governance_console(request):
    listings = (
        MarketplaceListing.objects.select_related("app", "publisher", "approved_by")
        .annotate(
            installation_count=Count("app__installations", filter=Q(app__installations__status="active"), distinct=True),
            open_review_count=Count("reviews", filter=Q(reviews__status__in=["pending", "in_review"]), distinct=True),
        )
        .order_by("-kill_switch_active", "status", "app__name")
    )
    pending_reviews = list(
        MarketplaceReview.objects.select_related("listing", "listing__app", "listing__publisher")
        .filter(status__in=[MarketplaceReview.Status.PENDING, MarketplaceReview.Status.IN_REVIEW])
        .order_by("requested_at")[:20]
    )
    scheduled_payouts = list(
        RevenueSharePayout.objects.filter(payout_scope=RevenueSharePayout.Scope.APP_PUBLISHER)
        .order_by("scheduled_for", "-created_at")[:20]
    )
    metrics = {
        "publishers_total": PublisherOrganization.objects.count(),
        "publishers_verified": PublisherOrganization.objects.filter(
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED
        ).count(),
        "apps_total": MarketplaceApp.objects.count(),
        "third_party_apps": MarketplaceApp.objects.filter(kind=MarketplaceApp.AppKind.THIRD_PARTY).count(),
        "approved_listings": MarketplaceListing.objects.filter(status=MarketplaceListing.Status.APPROVED).count(),
        "pending_listings": MarketplaceListing.objects.filter(status=MarketplaceListing.Status.PENDING_REVIEW).count(),
        "kill_switch_apps": MarketplaceListing.objects.filter(kill_switch_active=True).count(),
        "pending_security_reviews": MarketplaceListing.objects.filter(
            security_review_status=MarketplaceListing.ReviewStatus.PENDING
        ).count(),
        "scheduled_payout_total": (
            RevenueSharePayout.objects.filter(
                payout_scope=RevenueSharePayout.Scope.APP_PUBLISHER,
                status__in=[RevenueSharePayout.Status.SCHEDULED, RevenueSharePayout.Status.IN_TRANSIT],
            ).aggregate(total=Sum("net_amount")).get("total")
            or 0
        ),
    }
    context = {
        "metrics": metrics,
        "listings": list(listings[:60]),
        "pending_reviews": pending_reviews,
        "scheduled_payouts": scheduled_payouts,
    }
    return render(request, "marketplace/governance_console.html", context)


@login_required
@user_passes_test(_control_plane_access)
@require_POST
def marketplace_review_action(request, review_id):
    review = get_object_or_404(
        MarketplaceReview.objects.select_related("listing", "listing__app", "listing__publisher"),
        pk=review_id,
    )
    action = str(request.POST.get("action") or "").strip().lower()
    notes = str(request.POST.get("notes") or "").strip()
    findings = {"operator_notes": notes} if notes else {}

    if action == "approve":
        review, listing = finalize_marketplace_review(
            review,
            status=MarketplaceReview.Status.APPROVED,
            reviewed_by=request.user,
            notes=notes,
            findings_json=findings,
        )
    elif action == "changes_required":
        review, listing = finalize_marketplace_review(
            review,
            status=MarketplaceReview.Status.CHANGES_REQUIRED,
            reviewed_by=request.user,
            notes=notes,
            findings_json=findings,
        )
    elif action == "reject":
        review, listing = finalize_marketplace_review(
            review,
            status=MarketplaceReview.Status.REJECTED,
            reviewed_by=request.user,
            notes=notes,
            findings_json=findings,
        )
    elif action == "resubmit":
        new_review = submit_marketplace_review(
            review.listing,
            review_type=review.review_type,
            requested_by=request.user,
            notes=notes or "Resubmitted for review.",
            findings_json=findings,
        )
        return JsonResponse(
            {
                "status": "success",
                "review_id": new_review.pk,
                "listing_status": new_review.listing.status,
                "review_status": new_review.status,
            }
        )
    elif action == "toggle_kill_switch":
        listing = review.listing
        listing.kill_switch_active = not listing.kill_switch_active
        listing.save(update_fields=["kill_switch_active", "updated_at"])
        return JsonResponse(
            {
                "status": "success",
                "kill_switch_active": listing.kill_switch_active,
                "listing_status": listing.status,
            }
        )
    else:
        return JsonResponse({"status": "error", "error": "Unsupported review action."}, status=400)

    return JsonResponse(
        {
            "status": "success",
            "review_id": review.pk,
            "review_status": review.status,
            "listing_status": listing.status,
            "kill_switch_active": listing.kill_switch_active,
        }
    )
