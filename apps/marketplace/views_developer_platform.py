"""Developer-platform views — Move 1 of the four strategic moves.

Public surfaces:
  - GET  /marketplace/publisher/signup/         self-serve publisher signup form
  - POST /marketplace/publisher/signup/         submit a signup request
  - GET  /marketplace/publisher/verify-email/   confirm contact email
  - GET  /marketplace/apps/<slug>/              public listing detail page

Control-plane surfaces (operator only):
  - GET  /super/marketplace/signups/                       signup review queue
  - POST /super/marketplace/signups/<id>/decide/           approve / reject

Authenticated publisher surfaces:
  - GET  /super/marketplace/publisher/             partner dashboard (metrics overlay)
  - GET  /super/marketplace/publisher/webhooks/    publisher webhook log
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.marketplace.models import (
    AppInstallation,
    AppRating,
    AppVersion,
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
    PublisherSignupRequest,
    WebhookDelivery,
    WebhookEndpoint,
)
from apps.marketplace import partner_metrics, publisher_signup, ratings
from apps.marketplace.app_versions import list_versions, latest_stable


# ---------- helpers ----------


def _request_base_url(request) -> str:
    proto = "https" if request.is_secure() else "http"
    return f"{proto}://{request.get_host()}"


def _public_listing_qs():
    return (
        MarketplaceListing.objects.filter(
            status=MarketplaceListing.Status.APPROVED,
            kill_switch_active=False,
            app__is_active=True,
        )
        .select_related("app", "app__publisher", "publisher")
    )


def _publisher_for_request_user(user) -> PublisherOrganization | None:
    if not user or not user.is_authenticated:
        return None
    email = (user.email or "").strip().lower()
    if not email:
        return None
    return PublisherOrganization.objects.filter(verified_contact_email__iexact=email).first()


# ---------- public surfaces ----------


@require_GET
def public_app_detail(request, slug: str):
    """Public listing detail page — gallery, README, changelog, version history, install button."""

    listing = get_object_or_404(_public_listing_qs(), app__slug=slug)
    app = listing.app
    versions = list_versions(app, include_yanked=False)
    rating_stats = ratings.aggregate_for_app(app)
    recent_reviews = (
        AppRating.objects.filter(app=app, status=AppRating.Status.PUBLISHED)
        .order_by("-created_at")[:10]
    )
    is_installed_here = False
    if (
        request.user.is_authenticated
        and getattr(request, "school", None) is not None
    ):
        is_installed_here = AppInstallation.objects.filter(
            school=request.school,
            app=app,
            status=AppInstallation.Status.ACTIVE,
        ).exists()
    return render(
        request,
        "marketplace/public_app_detail.html",
        {
            "listing": listing,
            "app": app,
            "publisher": listing.publisher or app.publisher,
            "versions": versions,
            "latest_version": versions[0] if versions else None,
            "screenshot_urls": list(listing.screenshot_urls or []),
            "preview_image_url": listing.preview_image_url or "",
            "rating_stats": rating_stats,
            "recent_reviews": recent_reviews,
            "is_installed_here": is_installed_here,
        },
    )


def public_app_catalog_api(request):
    """JSON catalog API with search + facets — public, no auth required."""

    qs = _public_listing_qs()
    q = (request.GET.get("q") or "").strip()
    category = (request.GET.get("category") or "").strip()
    pricing_model = (request.GET.get("pricing") or "").strip()
    min_rating = request.GET.get("min_rating")
    sort = (request.GET.get("sort") or "popular").strip()

    if q:
        qs = qs.filter(
            Q(app__name__icontains=q)
            | Q(app__description__icontains=q)
            | Q(short_description__icontains=q)
        )
    if category:
        qs = qs.filter(category=category)
    if pricing_model:
        qs = qs.filter(app__pricing_model=pricing_model)

    qs = qs.annotate(
        avg_stars=Avg(
            "app__ratings__stars",
            filter=Q(app__ratings__status=AppRating.Status.PUBLISHED),
        ),
        rating_count=Count(
            "app__ratings",
            filter=Q(app__ratings__status=AppRating.Status.PUBLISHED),
        ),
        install_count=Count(
            "app__installations",
            filter=Q(app__installations__status=AppInstallation.Status.ACTIVE),
        ),
    )
    if min_rating:
        try:
            qs = qs.filter(avg_stars__gte=float(min_rating))
        except (TypeError, ValueError):
            pass

    if sort == "newest":
        qs = qs.order_by("-app__created_at")
    elif sort == "rating":
        qs = qs.order_by("-avg_stars", "-rating_count")
    elif sort == "name":
        qs = qs.order_by("app__name")
    else:  # popular
        qs = qs.order_by("-install_count", "app__name")

    rows = []
    for listing in qs[:200]:
        app = listing.app
        rows.append(
            {
                "slug": app.slug,
                "name": app.name,
                "short_description": listing.short_description,
                "category": listing.category,
                "pricing_model": app.pricing_model,
                "price": str(app.price),
                "publisher_name": getattr(listing.publisher or app.publisher, "name", None),
                "preview_image_url": listing.preview_image_url or "",
                "rating_average": round(float(listing.avg_stars or 0.0), 2),
                "rating_count": int(listing.rating_count or 0),
                "active_installs": int(listing.install_count or 0),
                "current_version": app.version,
                "detail_url": reverse(
                    "marketplace_dev:public_app_detail", kwargs={"slug": app.slug}
                ),
            }
        )

    facet_categories = (
        _public_listing_qs()
        .exclude(category="")
        .values_list("category", flat=True)
        .distinct()
        .order_by("category")
    )
    return JsonResponse(
        {
            "apps": rows,
            "facets": {
                "categories": list(facet_categories),
                "pricing_models": [c for c, _ in MarketplaceApp.PricingModel.choices],
            },
            "total": len(rows),
        }
    )


# ---------- self-serve publisher signup ----------


@csrf_protect
@require_http_methods(["GET", "POST"])
def publisher_signup_view(request):
    """Self-serve publisher signup. GET shows form, POST submits + emails token."""

    if request.method == "GET":
        return render(request, "marketplace/publisher_signup.html", {})

    org = (request.POST.get("organization_name") or "").strip()
    email = (request.POST.get("contact_email") or "").strip().lower()
    if not org or not email:
        return render(
            request,
            "marketplace/publisher_signup.html",
            {"error": "Organization name and contact email are required.", "form": request.POST},
            status=400,
        )
    if PublisherSignupRequest.objects.filter(
        contact_email=email,
        status__in=[
            PublisherSignupRequest.Status.EMAIL_PENDING,
            PublisherSignupRequest.Status.EMAIL_VERIFIED,
            PublisherSignupRequest.Status.APPROVED,
        ],
    ).exists():
        return render(
            request,
            "marketplace/publisher_signup.html",
            {
                "error": "A signup with that email is already in progress. Check your inbox or contact RMC support.",
                "form": request.POST,
            },
            status=409,
        )
    req = publisher_signup.submit_publisher_signup(
        organization_name=org,
        contact_email=email,
        contact_name=request.POST.get("contact_name", ""),
        legal_name=request.POST.get("legal_name", ""),
        country_code=request.POST.get("country_code", ""),
        website_url=request.POST.get("website_url", ""),
        intent=request.POST.get("intent", ""),
        submitted_by=request.user if request.user.is_authenticated else None,
    )
    publisher_signup.send_verification_email(req, base_url=_request_base_url(request))
    return render(
        request,
        "marketplace/publisher_signup_submitted.html",
        {"signup": req},
    )


@require_GET
def verify_email_view(request):
    token = (request.GET.get("token") or "").strip()
    if not token:
        return HttpResponseBadRequest("Missing token.")
    req = publisher_signup.verify_email_token(token)
    return render(
        request,
        "marketplace/publisher_signup_verified.html",
        {"signup": req, "found": req is not None},
    )


# ---------- operator review queue ----------


def _require_operator(request):
    user = request.user
    if not user.is_authenticated or not (user.is_staff or user.is_superuser):
        return False
    return True


@login_required
@require_GET
def signup_review_queue(request):
    if not _require_operator(request):
        return HttpResponse(status=403)
    pending = PublisherSignupRequest.objects.filter(
        status__in=[
            PublisherSignupRequest.Status.EMAIL_PENDING,
            PublisherSignupRequest.Status.EMAIL_VERIFIED,
        ]
    ).order_by("status", "-created_at")
    return render(
        request,
        "marketplace/signup_review_queue.html",
        {"pending": pending},
    )


@login_required
@require_POST
def signup_decide(request, signup_id: int):
    if not _require_operator(request):
        return HttpResponse(status=403)
    action = (request.POST.get("action") or "").strip().lower()
    notes = (request.POST.get("notes") or "").strip()
    if action == "approve":
        try:
            publisher_signup.approve_signup(signup_id, reviewer=request.user, reviewer_notes=notes)
            messages.success(request, "Publisher approved.")
        except (ValueError, PublisherSignupRequest.DoesNotExist) as exc:
            messages.error(request, str(exc))
    elif action == "reject":
        publisher_signup.reject_signup(signup_id, reviewer=request.user, reviewer_notes=notes)
        messages.success(request, "Publisher rejected.")
    else:
        return HttpResponseBadRequest("Unknown action.")
    return redirect("marketplace_dev:signup_review_queue")


# ---------- publisher dashboard metrics + webhook log ----------


@login_required
@require_GET
def partner_dashboard_metrics(request):
    """Extends publisher_dashboard with installs/MRR/churn/payouts JSON snapshot."""

    publisher = _publisher_for_request_user(request.user)
    if publisher is None:
        return JsonResponse(
            {"error": "no_publisher", "detail": "No publisher linked to your account."},
            status=404,
        )
    return JsonResponse(
        {
            "publisher": {"slug": publisher.slug, "name": publisher.name},
            "summary": partner_metrics.metrics_for_publisher(publisher),
            "per_app": [
                {
                    "slug": row["app"].slug,
                    "name": row["app"].name,
                    "active_installs": row["active_installs"],
                    "lifetime_installs": row["lifetime_installs"],
                    "uninstalled_30d": row["uninstalled_30d"],
                    "publisher_share_30d": str(row["publisher_share_30d"]),
                }
                for row in partner_metrics.per_app_metrics(publisher)
            ],
        }
    )


@csrf_protect
@login_required
@require_POST
def submit_rating_view(request, slug: str):
    """Tenant-facing rating submission.

    Polish for Move 1: surfaces the existing ratings.submit_rating service to
    real users. School + user are read from the request; stars must be 1..5.
    """

    school = getattr(request, "school", None)
    if school is None:
        return JsonResponse({"error": "tenant_required"}, status=400)
    app = get_object_or_404(MarketplaceApp, slug=slug)
    try:
        stars = int(request.POST.get("stars") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"error": "stars_must_be_int_1_5"}, status=400)
    if stars < 1 or stars > 5:
        return JsonResponse({"error": "stars_out_of_range"}, status=400)
    rating = ratings.submit_rating(
        app=app,
        school=school,
        author=request.user,
        stars=stars,
        headline=request.POST.get("headline", ""),
        body=request.POST.get("body", ""),
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {
                "id": rating.pk,
                "stars": rating.stars,
                "verified_install": rating.verified_install,
            },
            status=201,
        )
    return redirect("marketplace_dev:public_app_detail", slug=slug)


@csrf_protect
@login_required
@require_POST
def publisher_reply_view(request, rating_id: int):
    """Publisher posts a reply to one of their app's ratings."""

    rating = get_object_or_404(AppRating, pk=rating_id)
    publisher = _publisher_for_request_user(request.user)
    if publisher is None or rating.app.publisher_id != publisher.pk:
        return HttpResponse(status=403)
    text = (request.POST.get("reply") or "").strip()
    if not text:
        return JsonResponse({"error": "reply_required"}, status=400)
    ratings.publisher_reply(rating, reply_text=text)
    return redirect("marketplace_dev:public_app_detail", slug=rating.app.slug)


@csrf_protect
@login_required
@require_http_methods(["GET", "POST"])
def webhook_endpoints_view(request, app_slug: str):
    """Publisher CRUD for WebhookEndpoint rows on one of their apps.

    GET lists; POST creates with auto-generated secret. Edits land via
    `webhook_endpoint_edit_view`.
    """

    publisher = _publisher_for_request_user(request.user)
    app = get_object_or_404(MarketplaceApp, slug=app_slug)
    if publisher is None or app.publisher_id != publisher.pk:
        return HttpResponse(status=403)
    if request.method == "POST":
        from apps.marketplace.webhooks import new_secret

        url_value = (request.POST.get("url") or "").strip()
        if not url_value.startswith(("https://", "http://")):
            messages.error(request, "URL must be http:// or https://")
            return redirect("marketplace_dev:webhook_endpoints", app_slug=app_slug)
        topics_raw = (request.POST.get("topics") or "").strip()
        topics = [t.strip() for t in topics_raw.split(",") if t.strip()] or ["*"]
        WebhookEndpoint.objects.create(
            app=app,
            url=url_value[:500],
            description=request.POST.get("description", "")[:255],
            secret=new_secret(),
            topics=topics,
            is_active=True,
        )
        messages.success(request, "Webhook endpoint added.")
        return redirect("marketplace_dev:webhook_endpoints", app_slug=app_slug)
    endpoints = list(WebhookEndpoint.objects.filter(app=app).order_by("-created_at"))
    return render(
        request,
        "marketplace/webhook_endpoints.html",
        {"app": app, "endpoints": endpoints, "publisher": publisher},
    )


@csrf_protect
@login_required
@require_POST
def webhook_endpoint_edit_view(request, app_slug: str, endpoint_id: int):
    """Toggle active, rotate secret, or delete one endpoint."""

    publisher = _publisher_for_request_user(request.user)
    app = get_object_or_404(MarketplaceApp, slug=app_slug)
    if publisher is None or app.publisher_id != publisher.pk:
        return HttpResponse(status=403)
    endpoint = get_object_or_404(WebhookEndpoint, pk=endpoint_id, app=app)
    action = (request.POST.get("action") or "").strip()
    if action == "toggle":
        endpoint.is_active = not endpoint.is_active
        endpoint.save(update_fields=["is_active", "updated_at"])
    elif action == "rotate_secret":
        from apps.marketplace.webhooks import new_secret

        endpoint.secret = new_secret()
        endpoint.save(update_fields=["secret", "updated_at"])
        messages.success(request, "Secret rotated. Update your handler.")
    elif action == "delete":
        endpoint.delete()
        messages.success(request, "Endpoint deleted.")
    return redirect("marketplace_dev:webhook_endpoints", app_slug=app_slug)


@csrf_protect
@login_required
@require_http_methods(["GET", "POST"])
def app_versions_view(request, app_slug: str):
    """Publisher version-history page + publish form."""

    publisher = _publisher_for_request_user(request.user)
    app = get_object_or_404(MarketplaceApp, slug=app_slug)
    if publisher is None or app.publisher_id != publisher.pk:
        return HttpResponse(status=403)
    if request.method == "POST":
        from apps.marketplace import app_versions
        from apps.marketplace.semver_utils import parse_semver

        version = (request.POST.get("version") or "").strip()
        channel = (request.POST.get("channel") or "stable").strip()
        changelog = request.POST.get("changelog", "")
        if not parse_semver(version):
            messages.error(request, f"Invalid semver: {version!r}")
            return redirect("marketplace_dev:app_versions", app_slug=app_slug)
        try:
            app_versions.publish_version(
                app,
                version=version,
                channel=channel,
                changelog=changelog,
                published_by=request.user,
            )
            messages.success(request, f"Published v{version} on channel {channel}.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("marketplace_dev:app_versions", app_slug=app_slug)
    versions = list(AppVersion.objects.filter(app=app).order_by("-created_at"))
    return render(
        request,
        "marketplace/app_versions.html",
        {"app": app, "versions": versions, "publisher": publisher},
    )


@login_required
@require_GET
def publisher_webhook_log(request):
    publisher = _publisher_for_request_user(request.user)
    if publisher is None:
        return HttpResponse(status=403)
    app_ids = list(MarketplaceApp.objects.filter(publisher=publisher).values_list("id", flat=True))
    endpoints = WebhookEndpoint.objects.filter(app_id__in=app_ids).select_related("app")
    deliveries = (
        WebhookDelivery.objects.filter(app_id__in=app_ids)
        .select_related("endpoint", "app")
        .order_by("-created_at")[:200]
    )
    return render(
        request,
        "marketplace/publisher_webhook_log.html",
        {
            "endpoints": endpoints,
            "deliveries": deliveries,
        },
    )
