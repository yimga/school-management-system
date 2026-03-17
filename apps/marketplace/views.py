import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.billing.models import RevenueSharePayout
from apps.schools.control_plane import user_has_control_plane_access
from apps.marketplace.models import (
    AppInstallation,
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceReview,
    PublisherOrganization,
    ScopeGrant,
)
from apps.marketplace.services import (
    activate_sandbox_installation,
    approve_sensitive_scope,
    finalize_marketplace_review,
    install_app,
    refresh_installation,
    submit_marketplace_review,
    uninstall_app,
)
from apps.platform_runtime.catalog_counts import get_platform_catalog_counts

logger = logging.getLogger(__name__)

# §2.4 broad-except: preview can raise from policy/DB layer (typed per broad_exception_audit).
_MARKETPLACE_PREVIEW_FAILURES = (
    ValueError,
    TypeError,
    KeyError,
    ObjectDoesNotExist,
    DatabaseError,
    ImportError,
    AttributeError,
)


def _control_plane_access(user):
    return user_has_control_plane_access(user)


def _tenant_marketplace_allowed(user):
    """Tenant: only ADMIN, IT_ADMIN, LEADERSHIP, or staff/superuser can manage apps and scopes."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    role = (getattr(user, "role", "") or "").upper()
    return role in ("ADMIN", "IT_ADMIN", "LEADERSHIP")


def _control_plane_school_options(request, *, default_limit: int = 200) -> tuple[list, str, int]:
    from apps.schools.models import School

    school_query = str(request.GET.get("school_q") or "").strip()
    try:
        limit = max(25, min(int(request.GET.get("limit", default_limit)), 1000))
    except (TypeError, ValueError):
        limit = default_limit
    qs = School.objects.filter(is_active=True)
    if school_query:
        qs = qs.filter(Q(name__icontains=school_query) | Q(slug__icontains=school_query))
    return list(qs.order_by("name")[:limit]), school_query, limit


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
    dashboard_url = reverse("super:dashboard") if hasattr(request, "resolver_match") else "/super/"
    catalog_counts = get_platform_catalog_counts()
    context = {
        "metrics": metrics,
        "listings": list(listings[:60]),
        "pending_reviews": pending_reviews,
        "scheduled_payouts": scheduled_payouts,
        "dashboard_url": dashboard_url,
        "catalog_counts": catalog_counts,
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
    schools, school_query, school_limit = _control_plane_school_options(request)

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
            except _MARKETPLACE_PREVIEW_FAILURES as e:
                logger.warning("Blueprint pack preview failed: %s", e, exc_info=True)
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
    catalog_counts = get_platform_catalog_counts()
    return render(request, "marketplace/blueprint_marketplace.html", {
        "packs": packs,
        "schools": schools,
        "school_query": school_query,
        "school_limit": school_limit,
        "school_bundles": school_bundles,
        "preview": preview,
        "catalog_counts": catalog_counts,
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
        .prefetch_related("app__scopes")
        .annotate(
            active_installations=Count(
                "app__installations",
                filter=Q(
                    app__installations__status=AppInstallation.Status.ACTIVE,
                    app__installations__uninstalled_at__isnull=True,
                ),
                distinct=True,
            ),
            sandbox_installations=Count(
                "app__installations",
                filter=Q(
                    app__installations__status=AppInstallation.Status.ACTIVE,
                    app__installations__install_phase=AppInstallation.InstallPhase.SANDBOX,
                    app__installations__uninstalled_at__isnull=True,
                ),
                distinct=True,
            ),
            scope_count=Count("app__scopes", distinct=True),
            sensitive_scope_count=Count("app__scopes", filter=Q(app__scopes__sensitive=True), distinct=True),
        )
        .filter(app__is_active=True)
        .order_by("app__name")
    )
    installable_listings = [lst for lst in listings if getattr(lst, "installable", False)]
    schools, school_query, school_limit = _control_plane_school_options(request)
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
            install_app(
                school,
                app,
                installed_by=request.user,
                install_phase=AppInstallation.InstallPhase.SANDBOX,
            )
            messages.success(request, f"App “{app.name}” installed for “{school.name}” in sandbox mode.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("super:app_catalog")

    catalog_stats = {
        "apps": len(installable_listings),
        "verified_publishers": PublisherOrganization.objects.filter(
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED
        ).count(),
        "sandbox_ready": sum(1 for listing in installable_listings if getattr(listing, "sensitive_scope_count", 0) == 0),
        "installed_pairs": len(installed),
    }
    catalog_counts = get_platform_catalog_counts()
    from apps.schools.decision_architecture import get_decision_architecture_for_page
    return render(request, "marketplace/app_catalog.html", {
        "listings": installable_listings,
        "schools": schools,
        "school_query": school_query,
        "school_limit": school_limit,
        "installed": installed,
        "catalog_stats": catalog_stats,
        "catalog_counts": catalog_counts,
        "decision_architecture": get_decision_architecture_for_page("app_catalog"),
    })


@login_required
@user_passes_test(_control_plane_access)
@require_GET
def compatibility_matrix(request):
    """Control plane: which apps are compatible with which country/blueprint/plan."""
    listings = (
        MarketplaceListing.objects.select_related("app", "publisher")
        .filter(app__is_active=True)
        .order_by("app__name")
    )
    rows = []
    for lst in listings:
        compat = getattr(lst, "compatibility", None) or {}
        rows.append({
            "listing": lst,
            "app": lst.app,
            "countries": compat.get("countries") or compat.get("country_codes") or [],
            "blueprint_families": compat.get("blueprint_families") or [],
            "plan_tiers": compat.get("plan_tiers") or [],
        })
    return render(request, "marketplace/compatibility_matrix.html", {"rows": rows})


@login_required
@user_passes_test(_control_plane_access)
@require_GET
def sandbox_inspector(request):
    """Control plane: list installations with install_phase=sandbox."""
    from django.urls import reverse
    dashboard_url = reverse("super:dashboard") if hasattr(request, "resolver_match") else "/super/"
    installations = (
        AppInstallation.objects.filter(
            status=AppInstallation.Status.ACTIVE,
            install_phase=AppInstallation.InstallPhase.SANDBOX,
        )
        .select_related("app", "school", "installed_by")
        .order_by("-installed_at")
    )
    return render(request, "marketplace/sandbox_inspector.html", {
        "installations": installations,
        "dashboard_url": dashboard_url,
    })


@login_required
@user_passes_test(_control_plane_access)
@require_GET
def installation_health(request):
    """Control plane: list installations with last_health_at / health_status."""
    from django.urls import reverse
    dashboard_url = reverse("super:dashboard") if hasattr(request, "resolver_match") else "/super/"
    installations = (
        AppInstallation.objects.filter(status=AppInstallation.Status.ACTIVE)
        .select_related("app", "school")
        .order_by("-last_health_at")
    )
    return render(request, "marketplace/installation_health.html", {
        "installations": installations,
        "dashboard_url": dashboard_url,
    })


@login_required
@user_passes_test(_control_plane_access)
@require_GET
def marketplace_incident_dashboard(request):
    """Control plane: marketplace incidents; links to support/incident console; recent audit events."""
    from django.urls import reverse
    from apps.marketplace.models import AppAuditLog

    support_url = reverse("super:support_dashboard") if hasattr(request, "resolver_match") else "/super/support/"
    dashboard_url = reverse("super:dashboard") if hasattr(request, "resolver_match") else "/super/"
    recent_events = list(
        AppAuditLog.objects.filter(
            action__in=("install", "uninstall", "activate_sandbox", "schema_patch", "suspend", "unsuspend"),
        )
        .select_related("school", "app", "actor")
        .order_by("-created_at")[:50]
    )
    return render(request, "marketplace/incident_dashboard.html", {
        "support_url": support_url,
        "dashboard_url": dashboard_url,
        "recent_events": recent_events,
    })


@login_required
@user_passes_test(_control_plane_access)
@require_POST
def super_refresh_installation(request):
    """Control plane: re-apply app manifest to installation (e.g. widget_config)."""
    installation_id = request.POST.get("installation_id")
    if not installation_id:
        messages.error(request, "Select an installation.")
        return redirect("super:marketplace_installation_health")
    inst = get_object_or_404(AppInstallation, pk=installation_id, status=AppInstallation.Status.ACTIVE)
    refresh_installation(inst)
    messages.success(request, f"“{inst.app.name}” at “{inst.school.name}” refreshed from manifest.")
    return redirect("super:marketplace_installation_health")


@login_required
@user_passes_test(_control_plane_access)
@require_POST
def super_activate_sandbox(request):
    """Control plane: move installation from sandbox to active."""
    installation_id = request.POST.get("installation_id")
    if not installation_id:
        messages.error(request, "Select an installation.")
        return redirect("super:marketplace_sandbox_inspector")
    inst = get_object_or_404(
        AppInstallation,
        pk=installation_id,
        install_phase=AppInstallation.InstallPhase.SANDBOX,
        status=AppInstallation.Status.ACTIVE,
    )
    activate_sandbox_installation(inst, activated_by=request.user)
    messages.success(request, f"“{inst.app.name}” at “{inst.school.name}” is now active.")
    return redirect("super:marketplace_sandbox_inspector")


@login_required
@user_passes_test(_control_plane_access)
@require_GET
def package_rollout(request):
    """Control plane: list InstalledPackage (packages engine) with apply_stage=sandbox; offer Promote to production (Phase 4)."""
    from django.db.utils import ProgrammingError

    from apps.packages.models import InstalledPackage

    try:
        sandbox_packages = list(
            InstalledPackage.objects.filter(
                apply_stage="sandbox",
                is_active=True,
                school_id__isnull=False,
            )
            .select_related("school")
            .order_by("-applied_at")
        )
    except ProgrammingError:
        # Table packages_installedpackage may not exist yet (migrations not run or wrong schema).
        sandbox_packages = []
    return render(request, "marketplace/package_rollout.html", {"packages": sandbox_packages})


@login_required
@user_passes_test(_control_plane_access)
@require_POST
def package_promote(request):
    """Control plane: promote an InstalledPackage from sandbox to production (Phase 4)."""
    from django.db.utils import ProgrammingError

    from apps.packages.engine import promote_package
    from apps.packages.models import InstalledPackage

    pk = request.POST.get("installed_id") or request.POST.get("id")
    if not pk:
        messages.error(request, "Select a package.")
        return redirect("super:package_rollout")
    try:
        inst = get_object_or_404(
            InstalledPackage,
            pk=pk,
            apply_stage="sandbox",
            is_active=True,
            school_id__isnull=False,
        )
    except ProgrammingError:
        messages.error(request, "Packages table is not available. Run migrations (e.g. migrate_schemas --shared).")
        return redirect("super:package_rollout")
    promote_package(inst, actor_id=getattr(request.user, "id", None), target_mode="production")
    messages.success(request, f"“{inst.package_id}” at “{inst.school.name}” promoted to production.")
    return redirect("super:package_rollout")


@login_required
@user_passes_test(_tenant_marketplace_allowed)
@require_GET
def tenant_installed_apps(request):
    """
    Tenant-side: list installed apps for the current school.
    Excludes uninstalled; passes full installation objects for uninstall/activate.
    """
    school = getattr(request, "school", None)
    if not school:
        return render(request, "marketplace/tenant_installed_apps.html", {
            "installations": [],
            "school": None,
            "pending_scope_grants_count": 0,
            "page_title": "Installed apps",
            "page_subtitle": "No school context.",
            "action_url": reverse("tenant_app_catalog"),
        })
    installations = list(
        AppInstallation.objects.filter(
            school=school,
            status=AppInstallation.Status.ACTIVE,
            uninstalled_at__isnull=True,
        )
        .select_related("app")
        .order_by("-installed_at")
    )
    pending_scope_grants_count = ScopeGrant.objects.filter(
        installation__school=school,
        status=ScopeGrant.GrantStatus.PENDING,
    ).count()
    return render(
        request,
        "marketplace/tenant_installed_apps.html",
        {
            "installations": installations,
            "school": school,
            "pending_scope_grants_count": pending_scope_grants_count,
            "page_title": "Installed apps",
            "page_subtitle": "Apps installed for this school. New installs land in sandbox first.",
            "action_url": reverse("tenant_app_catalog"),
        },
    )


@login_required
@user_passes_test(_tenant_marketplace_allowed)
@require_GET
def tenant_app_catalog(request):
    """Tenant: browse installable apps for current school and install with scope consent."""
    school = getattr(request, "school", None)
    if not school:
        return render(request, "marketplace/tenant_app_catalog.html", {"listings": [], "school": None, "installed_slugs": set()})
    listings = (
        MarketplaceListing.objects.select_related("app", "publisher")
        .prefetch_related("app__scopes")
        .annotate(
            active_installations=Count(
                "app__installations",
                filter=Q(
                    app__installations__status=AppInstallation.Status.ACTIVE,
                    app__installations__uninstalled_at__isnull=True,
                ),
                distinct=True,
            ),
            scope_count=Count("app__scopes", distinct=True),
            sensitive_scope_count=Count("app__scopes", filter=Q(app__scopes__sensitive=True), distinct=True),
        )
        .filter(app__is_active=True, status=MarketplaceListing.Status.APPROVED)
        .order_by("app__name")
    )
    installable = []
    for lst in listings:
        if getattr(lst, "kill_switch_active", False):
            continue
        installable.append(lst)
    installed_slugs = set(
        AppInstallation.objects.filter(
            school=school,
            status=AppInstallation.Status.ACTIVE,
            uninstalled_at__isnull=True,
        ).values_list("app__slug", flat=True)
    )
    catalog_stats = {
        "apps": len(installable),
        "installed": len(installed_slugs),
        "sandbox_ready": sum(1 for listing in installable if getattr(listing, "sensitive_scope_count", 0) == 0),
        "verified_publishers": sum(
            1
            for listing in installable
            if getattr(getattr(listing, "publisher", None), "verification_status", "") == PublisherOrganization.VerificationStatus.VERIFIED
        ),
    }
    catalog_counts = get_platform_catalog_counts()
    return render(request, "marketplace/tenant_app_catalog.html", {
        "listings": installable,
        "school": school,
        "installed_slugs": installed_slugs,
        "catalog_stats": catalog_stats,
        "catalog_counts": catalog_counts,
    })


@login_required
@user_passes_test(_tenant_marketplace_allowed)
@require_POST
def tenant_install_app(request):
    """Tenant: install app for current school with scope consent (sensitive scopes → pending)."""
    school = getattr(request, "school", None)
    if not school:
        messages.error(request, "No school context.")
        return redirect("tenant_installed_apps")
    app_id = request.POST.get("app_id") or request.POST.get("app")
    if not app_id:
        messages.error(request, "Select an app.")
        return redirect("tenant_app_catalog")
    app = get_object_or_404(MarketplaceApp, pk=app_id, is_active=True)
    try:
        install_app(
            school,
            app,
            installed_by=request.user,
            install_phase=AppInstallation.InstallPhase.SANDBOX,
            skip_compatibility=False,
        )
        messages.success(request, f"App “{app.name}” has been installed in sandbox mode. Review it, then activate.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("tenant_installed_apps")


@login_required
@user_passes_test(_tenant_marketplace_allowed)
@require_POST
def tenant_uninstall_app(request):
    """Tenant: uninstall app for current school."""
    school = getattr(request, "school", None)
    if not school:
        messages.error(request, "No school context.")
        return redirect("tenant_installed_apps")
    installation_id = request.POST.get("installation_id")
    if not installation_id:
        messages.error(request, "Select an installation.")
        return redirect("tenant_installed_apps")
    inst = get_object_or_404(AppInstallation, pk=installation_id, school=school, uninstalled_at__isnull=True)
    try:
        uninstall_app(school, inst.app, uninstalled_by=request.user)
        messages.success(request, f"App “{inst.app.name}” has been uninstalled.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("tenant_installed_apps")


@login_required
@user_passes_test(_tenant_marketplace_allowed)
@require_GET
def tenant_scope_consent(request):
    """Tenant: list pending scope grants and approve (elevated approval for sensitive scopes)."""
    school = getattr(request, "school", None)
    if not school:
        return render(request, "marketplace/tenant_scope_consent.html", {"pending_grants": [], "school": None})
    pending_grants = list(
        ScopeGrant.objects.filter(
            installation__school=school,
            status=ScopeGrant.GrantStatus.PENDING,
        )
        .select_related("installation", "installation__app", "scope")
        .order_by("installation__app__name", "scope__scope_code")
    )
    return render(request, "marketplace/tenant_scope_consent.html", {
        "pending_grants": pending_grants,
        "school": school,
    })


@login_required
@user_passes_test(_tenant_marketplace_allowed)
@require_POST
def tenant_approve_scope(request):
    """Tenant: approve a pending (sensitive) scope grant."""
    school = getattr(request, "school", None)
    if not school:
        messages.error(request, "No school context.")
        return redirect("tenant_installed_apps")
    grant_id = request.POST.get("grant_id")
    if not grant_id:
        messages.error(request, "Select a scope grant.")
        return redirect("tenant_scope_consent")
    grant = get_object_or_404(
        ScopeGrant,
        pk=grant_id,
        installation__school=school,
        status=ScopeGrant.GrantStatus.PENDING,
    )
    approve_sensitive_scope(grant, request.user)
    messages.success(request, f"Scope “{grant.scope.scope_code}” has been approved.")
    return redirect("tenant_scope_consent")


@login_required
@user_passes_test(_tenant_marketplace_allowed)
@require_POST
def tenant_activate_installation(request):
    """Tenant: move a sandbox installation to active so it appears in runtime."""
    school = getattr(request, "school", None)
    if not school:
        messages.error(request, "No school context.")
        return redirect("tenant_installed_apps")
    installation_id = request.POST.get("installation_id")
    if not installation_id:
        messages.error(request, "Select an installation.")
        return redirect("tenant_installed_apps")
    inst = get_object_or_404(
        AppInstallation,
        pk=installation_id,
        school=school,
        install_phase=AppInstallation.InstallPhase.SANDBOX,
        status=AppInstallation.Status.ACTIVE,
    )
    activate_sandbox_installation(inst, activated_by=request.user)
    messages.success(request, f"“{inst.app.name}” is now active.")
    return redirect("tenant_installed_apps")


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
    _embed_parse_errors = (ValueError, TypeError, AttributeError, KeyError)
    if iframe_src and (iframe_src.startswith("http://") or iframe_src.startswith("https://")):
        from urllib.parse import urlparse
        try:
            parsed = urlparse(iframe_src)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            frame_ancestors = f"'self' {origin}"
        except _embed_parse_errors:
            pass
    # Origin check: only allow embed to be loaded from our own origins (Referer/Origin)
    request_origin = request.META.get("HTTP_ORIGIN") or request.META.get("HTTP_REFERER", "")
    if request_origin:
        from urllib.parse import urlparse
        from django.conf import settings
        try:
            parsed = urlparse(request_origin)
            host = (parsed.netloc or "").split(":")[0]
            allowed = list(getattr(settings, "ALLOWED_HOSTS", [])) or ["localhost", "127.0.0.1"]
            if host and host not in allowed and not any(host == h.lstrip(".") or host.endswith("." + h.lstrip(".")) for h in allowed if isinstance(h, str) and h.startswith(".")):
                return HttpResponse(
                    "<p>Embed not allowed from this origin.</p>",
                    content_type="text/html",
                    status=403,
                )
        except _embed_parse_errors:
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
