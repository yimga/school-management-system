from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.billing.models import RevenueSharePayout
from apps.marketplace.models import (
    AppInstallation,
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceReview,
    PublisherOrganization,
)
from apps.marketplace.services import (
    finalize_marketplace_review,
    install_app,
    submit_marketplace_review,
)


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


# ---------- Phase 6: Blueprint & App marketplace (list + apply/install) ----------


@login_required
@user_passes_test(_control_plane_access)
@require_http_methods(["GET", "POST"])
def blueprint_marketplace(request):
    """
    List BlueprintPacks; POST to apply, preview, or rollback.
    Apply: pack_id + school_id, action=apply (default).
    Preview (24.15): action=preview → store preview in session, redirect.
    Rollback: action=rollback + school_id + bundle_id → set TenantBlueprint.active_bundle to bundle (or clear).
    """
    from apps.policies.blueprint_services import apply_blueprint_pack, preview_blueprint_pack
    from apps.policies.models import BlueprintPack, PolicyBundle, TenantBlueprint
    from apps.policies.policy_registry import invalidate_policy_cache
    from apps.schools.models import School

    packs = list(BlueprintPack.objects.filter(is_active=True).order_by("category", "name"))
    schools = list(School.objects.filter(is_active=True).order_by("name")[:200])

    # For rollback: schools with PolicyBundles or TenantBlueprint (so we can revert or clear)
    school_bundles = {}
    for b in PolicyBundle.objects.filter(school__is_active=True).select_related("school").order_by("school__name", "-created_at")[:500]:
        sid = str(b.school_id)
        if sid not in school_bundles:
            school_bundles[sid] = {"school_name": b.school.name, "bundles": [], "current_active_id": None}
        school_bundles[sid]["bundles"].append({"id": b.id, "name": b.name or f"Bundle #{b.id}", "created_at": b.created_at})
    for tb in TenantBlueprint.objects.filter(school__is_active=True).select_related("school"):
        sid = str(tb.school_id)
        if sid not in school_bundles:
            school_bundles[sid] = {"school_name": tb.school.name, "bundles": [], "current_active_id": None}
        school_bundles[sid]["current_active_id"] = tb.active_bundle_id

    if request.method == "POST":
        action = (request.POST.get("action") or "apply").strip().lower()
        school_id = request.POST.get("school_id") or request.POST.get("school")
        if action == "rollback":
            bundle_id = request.POST.get("bundle_id", "").strip()
            if not school_id:
                messages.error(request, "Select a school to revert.")
                return redirect("super:blueprint_marketplace")
            school = get_object_or_404(School, pk=school_id, is_active=True)
            tb = TenantBlueprint.objects.filter(school=school).first()
            if not tb:
                messages.info(request, f"“{school.name}” has no blueprint to revert.")
                return redirect("super:blueprint_marketplace")
            new_bundle_id = int(bundle_id) if bundle_id and bundle_id.isdigit() else None
            if new_bundle_id:
                bundle = PolicyBundle.objects.filter(pk=new_bundle_id, school=school).first()
                if not bundle:
                    messages.error(request, "Selected bundle does not belong to this school.")
                    return redirect("super:blueprint_marketplace")
            tb.active_bundle_id = new_bundle_id
            tb.save(update_fields=["active_bundle", "updated_at"])
            invalidate_policy_cache(school)
            if new_bundle_id:
                messages.success(request, f"“{school.name}” reverted to selected bundle.")
            else:
                messages.success(request, f"“{school.name}” blueprint cleared (no bundle).")
            return redirect("super:blueprint_marketplace")

        if action == "preview":
            pack_id = request.POST.get("pack_id") or request.POST.get("pack")
            if not pack_id or not school_id:
                messages.error(request, "Select a pack and a school to preview.")
                return redirect("super:blueprint_marketplace")
            pack = get_object_or_404(BlueprintPack, pk=pack_id, is_active=True)
            school = get_object_or_404(School, pk=school_id, is_active=True)
            try:
                preview = preview_blueprint_pack(school, pack)
                request.session["blueprint_preview"] = preview
            except Exception as e:
                messages.error(request, str(e))
            return redirect("super:blueprint_marketplace")

        # apply
        pack_id = request.POST.get("pack_id") or request.POST.get("pack")
        if not pack_id or not school_id:
            messages.error(request, "Select a blueprint pack and a school.")
            return redirect("super:blueprint_marketplace")
        pack = get_object_or_404(BlueprintPack, pk=pack_id, is_active=True)
        school = get_object_or_404(School, pk=school_id, is_active=True)
        try:
            apply_blueprint_pack(school, pack, applied_by=request.user)
            messages.success(request, f"Blueprint “{pack.name}” applied to “{school.name}”.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("super:blueprint_marketplace")

    preview = request.session.pop("blueprint_preview", None)
    return render(request, "marketplace/blueprint_marketplace.html", {
        "packs": packs,
        "schools": schools,
        "school_bundles": school_bundles,
        "preview": preview,
    })


@login_required
@user_passes_test(_control_plane_access)
@require_http_methods(["GET", "POST"])
def app_catalog(request):
    """
    List installable apps; POST to install an app for a school.
    """
    from apps.schools.models import School

    listings = (
        MarketplaceListing.objects.select_related("app", "publisher")
        .filter(app__is_active=True)
        .order_by("app__name")
    )
    installable_listings = [lst for lst in listings if getattr(lst, "installable", False)]
    schools = list(School.objects.filter(is_active=True).order_by("name")[:200])
    installed = set()
    if schools:
        for inst in AppInstallation.objects.filter(
            school__in=schools,
            status=AppInstallation.Status.ACTIVE,
        ).values_list("school_id", "app_id"):
            installed.add(inst)

    if request.method == "POST":
        app_id = request.POST.get("app_id") or request.POST.get("app")
        school_id = request.POST.get("school_id") or request.POST.get("school")
        if not app_id or not school_id:
            messages.error(request, "Select an app and a school.")
            return redirect("super:app_catalog")
        app = get_object_or_404(MarketplaceApp, pk=app_id, is_active=True)
        school = get_object_or_404(School, pk=school_id, is_active=True)
        try:
            install_app(school, app, installed_by=request.user)
            messages.success(request, f"App “{app.name}” installed for “{school.name}”.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("super:app_catalog")

    return render(request, "marketplace/app_catalog.html", {
        "listings": installable_listings,
        "schools": schools,
        "installed": installed,
    })


@login_required
@require_GET
def sandbox_embed(request):
    """
    Secure app sandbox (Section 6, 25.2): embed an installed app widget in an iframe
    with sandbox attribute and CSP. Only allows widgets from active installations for this school.
    """
    school = getattr(request, "school", None)
    if not school:
        return HttpResponse(
            "<p>No school context.</p>",
            content_type="text/html",
            status=400,
        )
    app_slug = (request.GET.get("app_slug") or "").strip()
    widget_id = (request.GET.get("widget_id") or "").strip()
    iframe_src = None
    if app_slug:
        inst = (
            AppInstallation.objects.filter(
                school=school,
                app__slug=app_slug,
                status=AppInstallation.Status.ACTIVE,
            )
            .select_related("app")
            .first()
        )
        if inst:
            wconfig = inst.widget_config or inst.app.manifest.get("widgets") or {}
            if isinstance(wconfig, dict) and widget_id and widget_id in wconfig:
                cfg = wconfig[widget_id]
                if isinstance(cfg, dict) and cfg.get("url"):
                    iframe_src = cfg["url"]
            elif isinstance(wconfig, dict):
                for wid, cfg in wconfig.items():
                    if isinstance(cfg, dict) and cfg.get("url"):
                        iframe_src = cfg["url"]
                        break
    if not iframe_src:
        iframe_src = ""
    frame_ancestors = "'self'"
    if iframe_src and (iframe_src.startswith("http://") or iframe_src.startswith("https://")):
        from urllib.parse import urlparse
        try:
            parsed = urlparse(iframe_src)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            frame_ancestors = f"'self' {origin}"
        except Exception:
            pass
    safe_src = (iframe_src or "about:blank").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    sandbox_attr = "sandbox allow-scripts allow-same-origin"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>App Sandbox</title></head>
<body>
<div class="sandbox-container">
  <iframe src="{safe_src}" {sandbox_attr} title="App widget" style="width:100%;height:80vh;border:0;"></iframe>
</div>
</body></html>"""
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = f"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-src 'self' https:; frame-ancestors {frame_ancestors}"
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response
