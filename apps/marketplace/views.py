import json
import logging
import time
from types import SimpleNamespace
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.billing.models import RevenueSharePayout
from apps.schools.security_enforcer import enforce_tenant_security
from apps.billing.stripe_checkout import (
    get_active_stripe_processor_config,
    stripe_secret_key,
)
from apps.schools.control_plane import user_has_control_plane_access
from apps.marketplace.models import (
    AppInstallation,
    AppRating,
    AppScope,
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceReview,
    PublisherOrganization,
    ScopeGrant,
)
from apps.marketplace.permissions import tenant_marketplace_manage_required
from apps.marketplace.ecosystem_links import build_phase9_ecosystem_links
from apps.marketplace.listing_display import catalog_listing_display
from apps.marketplace.manifest_schema import (
    PRICING_ENTERPRISE,
    PRICING_FREE,
    PRICING_INCLUDED,
    PRICING_PAID,
    classify_scope_access,
    entitlement_hints_for_school,
    normalize_platform_manifest,
    resolve_tenant_catalog_signals,
)
from apps.marketplace.pack_registry import load_platform_pack_catalog
from apps.marketplace.install_impact import build_tenant_install_impact
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
from apps.platform_runtime.events import emit_platform_event
from apps.platform_runtime.observability import record_tenant_surface_view
from apps.siteconfig.commercial_tiers import plan_display_context

logger = logging.getLogger(__name__)


def _tenant_plan_display_context(school) -> dict:
    """Plan name/slug and coarse tier for catalog gating copy (not billing truth)."""
    ctx = plan_display_context(school)
    return {
        "slug": ctx.get("slug", ""),
        "name": ctx.get("name", ""),
        "tier_key": ctx.get("tier_key", "unknown"),
        "tier_label": ctx.get("tier_label", "—"),
        "commercial_tier": ctx.get("commercial_tier", ""),
    }


def _listing_proxy_for_installation(inst, listing_by_app_id: dict):
    """Resolve real listing or a read-only proxy so catalog signals always have app context."""
    lst = listing_by_app_id.get(inst.app_id)
    if lst is not None:
        return lst
    return SimpleNamespace(
        app=inst.app,
        metadata={},
        compatibility={},
        certification_status=MarketplaceListing.ReviewStatus.NOT_REQUIRED,
        security_review_status=MarketplaceListing.ReviewStatus.NOT_REQUIRED,
        status=MarketplaceListing.Status.APPROVED,
        publisher=None,
        kill_switch_active=False,
        installable=True,
    )


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


def _control_plane_school_options(
    request, *, default_limit: int = 200
) -> tuple[list, str, int]:
    from apps.schools.models import School

    school_query = str(request.GET.get("school_q") or "").strip()
    try:
        limit = max(25, min(int(request.GET.get("limit", default_limit)), 1000))
    except (TypeError, ValueError):
        limit = default_limit
    qs = School.objects.filter(is_active=True)
    if school_query:
        qs = qs.filter(
            Q(name__icontains=school_query) | Q(slug__icontains=school_query)
        )
    return list(qs.order_by("name")[:limit]), school_query, limit


@login_required
@user_passes_test(_control_plane_access)
def governance_console(request):
    listings = (
        MarketplaceListing.objects.select_related("app", "publisher", "approved_by")
        .annotate(
            installation_count=Count(
                "app__installations",
                filter=Q(app__installations__status="active"),
                distinct=True,
            ),
            open_review_count=Count(
                "reviews",
                filter=Q(reviews__status__in=["pending", "in_review"]),
                distinct=True,
            ),
        )
        .order_by("-kill_switch_active", "status", "app__name")
    )
    pending_reviews_qs = MarketplaceReview.objects.select_related(
        "listing", "listing__app", "listing__publisher"
    ).filter(
        status__in=[
            MarketplaceReview.Status.PENDING,
            MarketplaceReview.Status.IN_REVIEW,
        ]
    )
    pending_reviews_preview = list(pending_reviews_qs.order_by("requested_at")[:8])
    scheduled_payouts_qs = RevenueSharePayout.objects.filter(
        payout_scope=RevenueSharePayout.Scope.APP_PUBLISHER
    )
    scheduled_payouts_preview = list(
        scheduled_payouts_qs.order_by("scheduled_for", "-created_at")[:8]
    )
    metrics = {
        "publishers_total": PublisherOrganization.objects.count(),
        "publishers_verified": PublisherOrganization.objects.filter(
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED
        ).count(),
        "apps_total": MarketplaceApp.objects.count(),
        "third_party_apps": MarketplaceApp.objects.filter(
            kind=MarketplaceApp.AppKind.THIRD_PARTY
        ).count(),
        "approved_listings": MarketplaceListing.objects.filter(
            status=MarketplaceListing.Status.APPROVED
        ).count(),
        "pending_listings": MarketplaceListing.objects.filter(
            status=MarketplaceListing.Status.PENDING_REVIEW
        ).count(),
        "kill_switch_apps": MarketplaceListing.objects.filter(
            kill_switch_active=True
        ).count(),
        "pending_security_reviews": MarketplaceListing.objects.filter(
            security_review_status=MarketplaceListing.ReviewStatus.PENDING
        ).count(),
        "scheduled_payout_total": (
            RevenueSharePayout.objects.filter(
                payout_scope=RevenueSharePayout.Scope.APP_PUBLISHER,
                status__in=[
                    RevenueSharePayout.Status.SCHEDULED,
                    RevenueSharePayout.Status.IN_TRANSIT,
                ],
            )
            .aggregate(total=Sum("net_amount"))
            .get("total")
            or 0
        ),
    }
    dashboard_url = (
        reverse("super:dashboard") if hasattr(request, "resolver_match") else "/super/"
    )
    catalog_counts = get_platform_catalog_counts()
    listings_page = Paginator(listings, 15).get_page(request.GET.get("page") or 1)
    from apps.platform_runtime.operational_center_nav import (
        enrich_operational_frame_context,
        marketplace_governance_frame_context,
    )

    context = {
        **enrich_operational_frame_context(
            request, marketplace_governance_frame_context()
        ),
        "metrics": metrics,
        "listings": list(listings_page.object_list),
        "page_obj": listings_page,
        "pagination_extra_query": "",
        "pending_reviews_preview": pending_reviews_preview,
        "scheduled_payouts_preview": scheduled_payouts_preview,
        "queue_stats": {
            "pending_reviews_total": pending_reviews_qs.count(),
            "scheduled_payouts_total": scheduled_payouts_qs.count(),
        },
        "dashboard_url": dashboard_url,
        "catalog_counts": catalog_counts,
    }
    return render(request, "marketplace/governance_console.html", context)


def _marketplace_review_action_wants_json(request) -> bool:
    fmt = str(request.POST.get("format") or "").strip().lower()
    if fmt == "html":
        return False
    if fmt == "json":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    if "text/html" in accept and "application/json" not in accept:
        return False
    return True


def _marketplace_review_action_redirect(request, *, message: str):
    messages.success(request, message)
    return redirect("super:marketplace_governance")


@login_required
@user_passes_test(_control_plane_access)
@require_POST
def marketplace_review_action(request, review_id):
    review = get_object_or_404(
        MarketplaceReview.objects.select_related(
            "listing", "listing__app", "listing__publisher"
        ),
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
        if not _marketplace_review_action_wants_json(request):
            return _marketplace_review_action_redirect(
                request, message="Review resubmitted for operator queue."
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
        if not _marketplace_review_action_wants_json(request):
            return _marketplace_review_action_redirect(
                request,
                message=(
                    "Kill switch deactivated."
                    if not listing.kill_switch_active
                    else "Kill switch activated."
                ),
            )
        return JsonResponse(
            {
                "status": "success",
                "kill_switch_active": listing.kill_switch_active,
                "listing_status": listing.status,
            }
        )
    else:
        if not _marketplace_review_action_wants_json(request):
            messages.error(request, "Unsupported review action.")
            return redirect("super:marketplace_governance")
        return JsonResponse(
            {"status": "error", "error": "Unsupported review action."}, status=400
        )

    if not _marketplace_review_action_wants_json(request):
        label = review.listing.app.name
        if action == "approve":
            msg = f"Approved {label} for tenant install."
        elif action == "reject":
            msg = f"Rejected {label}."
        else:
            msg = f"Recorded changes required for {label}."
        return _marketplace_review_action_redirect(request, message=msg)

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
    from apps.policies.blueprint_services import (
        apply_blueprint_pack,
        preview_blueprint_pack,
    )
    from apps.policies.models import BlueprintPack, PolicyBundle, TenantBlueprint
    from apps.policies.policy_registry import invalidate_policy_cache
    from apps.schools.models import School

    packs_qs = BlueprintPack.objects.filter(is_active=True).order_by("category", "name")
    packs_page = Paginator(packs_qs, 12).get_page(request.GET.get("page") or 1)
    packs = list(packs_page.object_list)
    schools, school_query, school_limit = _control_plane_school_options(request)

    # For rollback: schools with PolicyBundles or TenantBlueprint (so we can revert or clear)
    school_bundles = {}
    for b in (
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        PolicyBundle.objects.filter(school__is_active=True)
        .select_related("school")
        .order_by("school__name", "-created_at")[:500]
    ):
        sid = str(b.school_id)
        if sid not in school_bundles:
            school_bundles[sid] = {
                "school_name": b.school.name,
                "bundles": [],
                "current_active_id": None,
            }
        school_bundles[sid]["bundles"].append(
            {
                "id": b.id,
                "name": b.name or f"Bundle #{b.id}",
                "created_at": b.created_at,
            }
        )
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    for tb in TenantBlueprint.objects.filter(school__is_active=True).select_related(
        "school"
    ):
        sid = str(tb.school_id)
        if sid not in school_bundles:
            school_bundles[sid] = {
                "school_name": tb.school.name,
                "bundles": [],
                "current_active_id": None,
            }
        school_bundles[sid]["current_active_id"] = tb.active_bundle_id

    if request.method == "POST":
        action = (request.POST.get("action") or "apply").strip().lower()
        school_id = request.POST.get("school_id") or request.POST.get("school")
        if action == "rollback":
            ack = (request.POST.get("confirm_blueprint_rollback") or "").strip()
            if ack != "ROLLBACK":
                messages.error(
                    request,
                    "Type ROLLBACK in the confirmation field to acknowledge blueprint impact.",
                )
                return redirect("super:blueprint_marketplace")
            bundle_id = request.POST.get("bundle_id", "").strip()
            if not school_id:
                messages.error(request, "Select a school to revert.")
                return redirect("super:blueprint_marketplace")
            school = get_object_or_404(School, pk=school_id, is_active=True)
            tb = TenantBlueprint.objects.filter(school=school).first()
            if not tb:
                messages.info(request, f"“{school.name}” has no blueprint to revert.")
                return redirect("super:blueprint_marketplace")
            new_bundle_id = (
                int(bundle_id) if bundle_id and bundle_id.isdigit() else None
            )
            if new_bundle_id:
                bundle = PolicyBundle.objects.filter(
                    pk=new_bundle_id, school=school
                ).first()
                if not bundle:
                    messages.error(
                        request, "Selected bundle does not belong to this school."
                    )
                    return redirect("super:blueprint_marketplace")
            previous_bundle_id = tb.active_bundle_id
            tb.active_bundle_id = new_bundle_id
            tb.save(update_fields=["active_bundle", "updated_at"])
            invalidate_policy_cache(school)
            emit_platform_event(
                "blueprint_rolled_back",
                {
                    "school_id": str(school.pk),
                    "previous_bundle_id": previous_bundle_id,
                    "new_bundle_id": new_bundle_id,
                    "actor_id": getattr(request.user, "pk", None),
                },
                tenant_id=str(school.pk),
            )
            if new_bundle_id:
                messages.success(
                    request, f"“{school.name}” reverted to selected bundle."
                )
            else:
                messages.success(
                    request, f"“{school.name}” blueprint cleared (no bundle)."
                )
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
                request.session["blueprint_apply_allowed"] = {
                    "pack_id": int(pack.pk),
                    "school_id": str(school.pk),
                    "ts": time.time(),
                }
            except _MARKETPLACE_PREVIEW_FAILURES as e:
                logger.warning("Blueprint pack preview failed: %s", e, exc_info=True)
                messages.error(request, str(e))
            return redirect("super:blueprint_marketplace")

        # apply (N17: preview required for same pack+school within 15 minutes)
        pack_id = request.POST.get("pack_id") or request.POST.get("pack")
        if not pack_id or not school_id:
            messages.error(request, "Select a blueprint pack and a school.")
            return redirect("super:blueprint_marketplace")
        pack = get_object_or_404(BlueprintPack, pk=pack_id, is_active=True)
        school = get_object_or_404(School, pk=school_id, is_active=True)
        try:
            pack_i = int(pack.pk)
        except (TypeError, ValueError):
            messages.error(request, "Invalid pack.")
            return redirect("super:blueprint_marketplace")
        school_i = str(school.pk)
        allowed = request.session.get("blueprint_apply_allowed") or {}
        ts = float(allowed.get("ts") or 0)
        if (
            allowed.get("pack_id") != pack_i
            or str(allowed.get("school_id")) != school_i
            or (time.time() - ts) > 900
        ):
            messages.error(
                request,
                "Preview this blueprint pack for the selected school before applying "
                "(policy keys and impact). Use Preview, then Apply within 15 minutes.",
            )
            return redirect("super:blueprint_marketplace")
        try:
            apply_blueprint_pack(school, pack, applied_by=request.user)
            messages.success(
                request, f"Blueprint “{pack.name}” applied to “{school.name}”."
            )
            request.session.pop("blueprint_apply_allowed", None)
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("super:blueprint_marketplace")

    preview = request.session.pop("blueprint_preview", None)
    catalog_counts = get_platform_catalog_counts()
    blueprint_stats = {
        "packs_total": packs_qs.count(),
        "showing": len(packs),
    }
    from apps.platform_runtime.operational_center_nav import (
        blueprint_marketplace_frame_context,
        enrich_operational_frame_context,
    )

    return render(
        request,
        "marketplace/blueprint_marketplace.html",
        {
            "packs": packs,
            "page_obj": packs_page,
            "pagination_extra_query": "",
            "blueprint_stats": blueprint_stats,
            "schools": schools,
            "school_query": school_query,
            "school_limit": school_limit,
            "school_bundles": school_bundles,
            "preview": preview,
            "catalog_counts": catalog_counts,
            **enrich_operational_frame_context(
                request, blueprint_marketplace_frame_context()
            ),
        },
    )


def _app_catalog_query_params(request) -> dict[str, str]:
    """Preserve browse state across POST redirect."""
    params: dict[str, str] = {}
    for key in ("q", "kind", "page", "school_id", "school_q"):
        val = (request.GET.get(key) or request.POST.get(key) or "").strip()
        if val:
            params[key] = val
    return params


def _app_catalog_redirect(request, **extra: str):
    params = _app_catalog_query_params(request)
    params.update({k: v for k, v in extra.items() if v})
    base = reverse("super:app_catalog")
    if params:
        return redirect(f"{base}?{urlencode(params)}")
    return redirect(base)


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
            sensitive_scope_count=Count(
                "app__scopes", filter=Q(app__scopes__sensitive=True), distinct=True
            ),
        )
        .filter(app__is_active=True)
        .order_by("app__name")
    )
    installable_listings = [
        lst for lst in listings if getattr(lst, "installable", False)
    ]
    for lst in installable_listings:
        lst.catalog_display = catalog_listing_display(lst)

    schools, school_query, school_limit = _control_plane_school_options(
        request, default_limit=80
    )
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
            return _app_catalog_redirect(request)
        if request.POST.get("install_after_impact_preview") != "1":
            messages.error(
                request,
                "Open “Preview impact”, review scopes and compatibility, then confirm "
                "install from that dialog (N17).",
            )
            return _app_catalog_redirect(request)
        app = get_object_or_404(MarketplaceApp, pk=app_id, is_active=True)
        school = get_object_or_404(School, pk=school_id, is_active=True)
        try:
            install_app(
                school,
                app,
                installed_by=request.user,
                install_phase=AppInstallation.InstallPhase.SANDBOX,
            )
            messages.success(
                request,
                f"App “{app.name}” installed for “{school.name}” in sandbox mode.",
            )
        except ValueError as e:
            messages.error(request, str(e))
        return _app_catalog_redirect(request)

    search_query = (request.GET.get("q") or "").strip()
    active_kind = (request.GET.get("kind") or "all").strip().lower()
    valid_kinds = {c[0] for c in MarketplaceApp.AppKind.choices}
    if active_kind not in valid_kinds and active_kind != "all":
        active_kind = "all"

    filtered = installable_listings
    if search_query:
        needle = search_query.lower()
        filtered = [
            lst
            for lst in filtered
            if needle in (lst.app.name or "").lower()
            or needle in (lst.app.slug or "").lower()
            or needle in (lst.app.description or "").lower()
            or needle in (lst.short_description or "").lower()
            or needle in (lst.category or "").lower()
        ]
    if active_kind != "all":
        filtered = [lst for lst in filtered if lst.app.kind == active_kind]

    kind_tabs: list[dict[str, object]] = [
        {"key": "all", "label": "All apps", "count": len(installable_listings)}
    ]
    for kind_key, kind_label in MarketplaceApp.AppKind.choices:
        count = sum(1 for lst in installable_listings if lst.app.kind == kind_key)
        if count:
            kind_tabs.append({"key": kind_key, "label": kind_label, "count": count})

    page_obj = Paginator(filtered, 12).get_page(request.GET.get("page") or 1)
    listings_page = list(page_obj.object_list)

    selected_school_id = (request.GET.get("school_id") or "").strip()
    try:
        selected_school_id_int = int(selected_school_id) if selected_school_id else None
    except ValueError:
        selected_school_id_int = None

    catalog_stats = {
        "apps": len(installable_listings),
        "verified_publishers": PublisherOrganization.objects.filter(
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED
        ).count(),
        "sandbox_ready": sum(
            1
            for listing in installable_listings
            if getattr(listing, "sensitive_scope_count", 0) == 0
        ),
        "installed_pairs": len(installed),
        "showing": len(listings_page),
        "filtered_total": page_obj.paginator.count,
    }
    catalog_counts = get_platform_catalog_counts()
    from apps.schools.decision_architecture import get_decision_architecture_for_page

    browse_q = request.GET.copy()
    browse_q.pop("page", None)
    pagination_extra_query = browse_q.urlencode()

    from apps.platform_runtime.operational_center_nav import (
        app_catalog_frame_context,
        enrich_operational_frame_context,
    )

    return render(
        request,
        "marketplace/app_catalog.html",
        {
            **enrich_operational_frame_context(request, app_catalog_frame_context()),
            "listings": listings_page,
            "page_obj": page_obj,
            "search_query": search_query,
            "active_kind": active_kind,
            "kind_tabs": kind_tabs,
            "schools": schools,
            "school_query": school_query,
            "school_limit": school_limit,
            "selected_school_id": selected_school_id_int,
            "installed": installed,
            "catalog_stats": catalog_stats,
            "catalog_counts": catalog_counts,
            "pagination_extra_query": pagination_extra_query,
            "decision_architecture": get_decision_architecture_for_page("app_catalog"),
            "install_impact_preview_url": reverse(
                "super:marketplace_install_impact_preview"
            ),
        },
    )


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
        rows.append(
            {
                "listing": lst,
                "app": lst.app,
                "countries": compat.get("countries")
                or compat.get("country_codes")
                or [],
                "blueprint_families": compat.get("blueprint_families") or [],
                "plan_tiers": compat.get("plan_tiers") or [],
            }
        )
    rows_page = Paginator(rows, 20).get_page(request.GET.get("page") or 1)
    from apps.platform_runtime.operational_center_nav import (
        compatibility_matrix_frame_context,
        enrich_operational_frame_context,
    )

    return render(
        request,
        "marketplace/compatibility_matrix.html",
        {
            "rows": list(rows_page.object_list),
            "page_obj": rows_page,
            "pagination_extra_query": "",
            **enrich_operational_frame_context(
                request, compatibility_matrix_frame_context()
            ),
        },
    )


@login_required
@user_passes_test(_control_plane_access)
@require_GET
def sandbox_inspector(request):
    """Control plane: list installations with install_phase=sandbox."""
    from django.urls import reverse

    dashboard_url = (
        reverse("super:dashboard") if hasattr(request, "resolver_match") else "/super/"
    )
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    installations_qs = AppInstallation.objects.filter(
        status=AppInstallation.Status.ACTIVE,
        install_phase=AppInstallation.InstallPhase.SANDBOX,
    ).select_related("app", "school", "installed_by").order_by("-installed_at")
    installations_page = Paginator(installations_qs, 20).get_page(
        request.GET.get("page") or 1
    )
    from apps.platform_runtime.operational_center_nav import (
        enrich_operational_frame_context,
        sandbox_inspector_frame_context,
    )

    return render(
        request,
        "marketplace/sandbox_inspector.html",
        {
            **enrich_operational_frame_context(
                request, sandbox_inspector_frame_context()
            ),
            "installations": list(installations_page.object_list),
            "page_obj": installations_page,
            "pagination_extra_query": "",
            "dashboard_url": dashboard_url,
        },
    )


@login_required
@user_passes_test(_control_plane_access)
@require_GET
def installation_health(request):
    """Control plane: list installations with last_health_at / health_status."""
    from django.urls import reverse

    dashboard_url = (
        reverse("super:dashboard") if hasattr(request, "resolver_match") else "/super/"
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    )
    installations_qs = AppInstallation.objects.filter(
        status=AppInstallation.Status.ACTIVE
    ).select_related("app", "school").order_by("-last_health_at")
    installations_page = Paginator(installations_qs, 20).get_page(
        request.GET.get("page") or 1
    )
    from apps.platform_runtime.operational_center_nav import (
        enrich_operational_frame_context,
        installation_health_frame_context,
    )

    return render(
        request,
        "marketplace/installation_health.html",
        {
            "installations": list(installations_page.object_list),
            "page_obj": installations_page,
            "pagination_extra_query": "",
            "dashboard_url": dashboard_url,
            **enrich_operational_frame_context(
                request, installation_health_frame_context()
            ),
        },
    )


@login_required
@user_passes_test(_control_plane_access)
@require_GET
def marketplace_incident_dashboard(request):
    """Control plane: marketplace incidents; links to support/incident console; recent audit events."""
    from django.urls import reverse
    from apps.marketplace.models import AppAuditLog

    support_url = (
        reverse("super:support_dashboard")
        if hasattr(request, "resolver_match")
        else "/super/support/"
    )
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    dashboard_url = (
        reverse("super:dashboard") if hasattr(request, "resolver_match") else "/super/"
    )
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    recent_events = list(
        AppAuditLog.objects.filter(
            action__in=(
                "install",
                "uninstall",
                "activate_sandbox",
                "schema_patch",
                "suspend",
                "unsuspend",
            ),
        )
        .select_related("school", "app", "actor")
        .order_by("-created_at")[:50]
    )
    from apps.platform_runtime.operational_center_nav import (
        enrich_operational_frame_context,
        marketplace_incident_frame_context,
    )

    return render(
        request,
        "marketplace/incident_dashboard.html",
        {
            "support_url": support_url,
            "dashboard_url": dashboard_url,
            "recent_events": recent_events,
            **enrich_operational_frame_context(
                request, marketplace_incident_frame_context()
            ),
        },
    )


@login_required
@user_passes_test(_control_plane_access)
@require_POST
def super_refresh_installation(request):
    """Control plane: re-apply app manifest to installation (e.g. widget_config)."""
    installation_id = request.POST.get("installation_id")
    if not installation_id:
        messages.error(request, "Select an installation.")
        return redirect("super:marketplace_installation_health")
    inst = get_object_or_404(
        AppInstallation, pk=installation_id, status=AppInstallation.Status.ACTIVE
    )
    refresh_installation(inst)
    messages.success(
        request, f"“{inst.app.name}” at “{inst.school.name}” refreshed from manifest."
    )
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
    try:
        activate_sandbox_installation(inst, activated_by=request.user)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("super:marketplace_sandbox_inspector")
    messages.success(
        request, f"“{inst.app.name}” at “{inst.school.name}” is now active."
    )
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
    from apps.platform_runtime.operational_center_nav import (
        enrich_operational_frame_context,
        package_rollout_frame_context,
    )

    return render(
        request,
        "marketplace/package_rollout.html",
        {
            "packages": sandbox_packages,
            **enrich_operational_frame_context(
                request, package_rollout_frame_context()
            ),
        },
    )


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
        messages.error(
            request,
            "Packages table is not available. Run migrations (e.g. migrate_schemas --shared).",
        )
        return redirect("super:package_rollout")
    promote_package(
        inst, actor_id=getattr(request.user, "id", None), target_mode="production"
    )
    messages.success(
        request, f"“{inst.package_id}” at “{inst.school.name}” promoted to production."
    )
    return redirect("super:package_rollout")


@login_required
@tenant_marketplace_manage_required
@require_GET
def tenant_installed_apps(request):
    """
    Tenant-side: list installed apps for the current school.
    Excludes uninstalled; passes full installation objects for uninstall/activate.
    """
    school = getattr(request, "school", None)
    if not school:
        return render(
            request,
            "marketplace/tenant_installed_apps.html",
            {
                "installations": [],
                "school": None,
                "pending_scope_grants_count": 0,
                "page_title": "Installed apps",
                "page_subtitle": "No school context.",
                "action_url": reverse("tenant_app_catalog"),
            },
        )
    phase_filter = (request.GET.get("phase") or "").strip().lower()
    if phase_filter not in {
        AppInstallation.InstallPhase.SANDBOX,
        AppInstallation.InstallPhase.ACTIVE,
    }:
        phase_filter = ""
    installations_qs = (
        AppInstallation.objects.filter(
            school=school,
            status=AppInstallation.Status.ACTIVE,
            uninstalled_at__isnull=True,
        )
        .select_related("app")
        .prefetch_related(
            "scope_grants",
            "scope_grants__scope",
            Prefetch(
                "app__scopes",
                queryset=AppScope.objects.order_by("scope_code"),
            ),
        )
        .order_by("-installed_at")
    )
    if phase_filter:
        installations_qs = installations_qs.filter(install_phase=phase_filter)
    installations = list(installations_qs)
    listing_by_app_id = {
        lst.app_id: lst
        for lst in MarketplaceListing.objects.filter(
            app_id__in=[x.app_id for x in installations]
        ).select_related("app", "publisher")
    }
    for inst in installations:
        lst_like = _listing_proxy_for_installation(inst, listing_by_app_id)
        inst.catalog_signals = resolve_tenant_catalog_signals(
            listing=lst_like,
            school=school,
            installation=inst,
            listing_installable=getattr(lst_like, "installable", True),
        )
        grants_by_scope = {g.scope_id: g for g in inst.scope_grants.all()}
        rows = []
        for sc in inst.app.scopes.all():
            g = grants_by_scope.get(sc.id)
            rows.append(
                {
                    "code": sc.scope_code,
                    "description": sc.description or "",
                    "sensitive": sc.sensitive,
                    "access_tier": classify_scope_access(
                        sc.scope_code, sensitive=sc.sensitive
                    ),
                    "grant_status": getattr(g, "status", "") if g else "",
                }
            )
        inst.scope_display_rows = rows
        mu = inst.catalog_signals.get("manifest_ui") or {}
        keys = mu.get("tenant_editable_config_keys") or []
        inst.tenant_editable_pairs = [
            (str(k).strip(), str((inst.config or {}).get(str(k).strip(), "")))
            for k in keys
            if str(k).strip()
        ]
        try:
            inst.config_display_json = json.dumps(
                inst.config or {}, indent=2, sort_keys=True
            )
        except (TypeError, ValueError):
            inst.config_display_json = "{}"
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
            "page_title": "Sandbox queue" if phase_filter == "sandbox" else "Installed apps",
            "page_subtitle": (
                "Apps waiting in this school's sandbox for review and deliberate activation."
                if phase_filter == "sandbox"
                else "Apps installed for this school. New installs land in sandbox first."
            ),
            "action_url": reverse("tenant_app_catalog"),
            "phase_filter": phase_filter,
        },
    )


@login_required
@tenant_marketplace_manage_required
@require_GET
def tenant_app_catalog(request):
    """Tenant: browse installable apps for current school and install with scope consent."""
    school = getattr(request, "school", None)
    if not school:
        return render(
            request,
            "marketplace/tenant_app_catalog.html",
            {
                "listings": [],
                "school": None,
                "installed_slugs": set(),
                "phase9_links": build_phase9_ecosystem_links(),
                "plan_context": {
                    "slug": "",
                    "name": "",
                    "tier_key": "unknown",
                    "tier_label": "—",
                },
                "catalog_install_app_id": None,
            },
        )
    listings = (
        MarketplaceListing.objects.select_related("app", "publisher")
        .prefetch_related("app__scopes", "app__version_compat")
        .filter(app__is_active=True, status=MarketplaceListing.Status.APPROVED)
    )
    catalog_outcomes = list(
        listings.exclude(category="")
        .order_by("category")
        .values_list("category", flat=True)
        .distinct()
    )
    catalog_filters = {
        "q": (request.GET.get("q") or "").strip(),
        "outcome": (request.GET.get("outcome") or "").strip(),
        "pricing": (request.GET.get("pricing") or "").strip().lower(),
        "sort": (request.GET.get("sort") or "relevant").strip().lower(),
    }
    if catalog_filters["q"]:
        query = catalog_filters["q"]
        listings = listings.filter(
            Q(app__name__icontains=query)
            | Q(app__slug__icontains=query)
            | Q(app__description__icontains=query)
            | Q(short_description__icontains=query)
            | Q(category__icontains=query)
            | Q(publisher__name__icontains=query)
        )
    if catalog_filters["outcome"]:
        listings = listings.filter(category__iexact=catalog_filters["outcome"])
    if catalog_filters["pricing"] == "included":
        listings = listings.filter(app__pricing_model=MarketplaceApp.PricingModel.FREE)
    elif catalog_filters["pricing"] == "paid":
        listings = listings.filter(
            app__pricing_model__in=(
                MarketplaceApp.PricingModel.SUBSCRIPTION,
                MarketplaceApp.PricingModel.USAGE,
            )
        )

    listings = listings.annotate(
            active_installations=Count(
                "app__installations",
                filter=Q(
                    app__installations__status=AppInstallation.Status.ACTIVE,
                    app__installations__uninstalled_at__isnull=True,
                ),
                distinct=True,
            ),
            scope_count=Count("app__scopes", distinct=True),
            sensitive_scope_count=Count(
                "app__scopes", filter=Q(app__scopes__sensitive=True), distinct=True
            ),
            average_rating=Avg(
                "app__ratings__stars",
                filter=Q(app__ratings__status=AppRating.Status.PUBLISHED),
            ),
            rating_count=Count(
                "app__ratings",
                filter=Q(app__ratings__status=AppRating.Status.PUBLISHED),
                distinct=True,
            ),
        )
    if catalog_filters["sort"] == "popular":
        listings = listings.order_by("-active_installations", "app__name")
    elif catalog_filters["sort"] == "rating":
        listings = listings.order_by("-average_rating", "-rating_count", "app__name")
    elif catalog_filters["sort"] == "newest":
        listings = listings.order_by("-approved_at", "app__name")
    else:
        catalog_filters["sort"] = "relevant"
        listings = listings.order_by("app__name")
    active_installations = list(
        AppInstallation.objects.filter(
            school=school,
            status=AppInstallation.Status.ACTIVE,
            uninstalled_at__isnull=True,
        ).select_related("app")
    )
    installations_by_app = {i.app_id: i for i in active_installations}
    installed_slugs = {i.app.slug for i in active_installations}
    installable = []
    for lst in listings:
        if getattr(lst, "kill_switch_active", False):
            continue
        lst.catalog_display = catalog_listing_display(lst)
        inst = installations_by_app.get(lst.app_id)
        sig = resolve_tenant_catalog_signals(
            listing=lst,
            school=school,
            installation=inst,
            listing_installable=lst.installable,
        )
        lst.tenant_install_phase = sig.get("tenant_install_phase") or ""
        lst.mkt_lifecycle = sig["lifecycle"]
        lst.mkt_show_update = sig["show_update"]
        lst.mkt_show_rollback = sig["show_rollback"]
        lst.mkt_governance_badge = sig["governance_badge"]
        lst.mkt_manifest_ui = sig["manifest_ui"]
        lst.mkt_entitlement = sig["entitlement"]
        lst.mkt_manifest_warnings = sig.get("manifest_warnings") or []
        lst.mkt_revenue_share_percent = getattr(lst, "revenue_share_percent", None)
        lst.mkt_listing_pipeline_phase = sig.get("listing_pipeline_phase") or ""
        lst.mkt_compatibility = sig.get("compatibility") or {}
        installable.append(lst)
    page_obj = Paginator(installable, 12).get_page(request.GET.get("page") or 1)
    listings_page = list(page_obj.object_list)

    verified_publisher_ids = {
        listing.publisher_id
        for listing in installable
        if listing.publisher_id
        and getattr(listing.publisher, "verification_status", "")
        == PublisherOrganization.VerificationStatus.VERIFIED
    }
    compatibility_review_count = sum(
        1
        for listing in installable
        if not bool((getattr(listing, "mkt_compatibility", None) or {}).get("ok", True))
    )
    unverified_listing_count = sum(
        1
        for listing in installable
        if getattr(getattr(listing, "publisher", None), "verification_status", "")
        != PublisherOrganization.VerificationStatus.VERIFIED
    )
    catalog_policy_healthy = not compatibility_review_count and not unverified_listing_count
    catalog_stats = {
        "apps": len(installable),
        "installed": len(installed_slugs),
        "sandbox_ready": sum(
            1
            for listing in installable
            if getattr(listing, "sensitive_scope_count", 0) == 0
        ),
        "verified_publishers": len(verified_publisher_ids),
        "compatibility_review": compatibility_review_count,
        "showing": len(listings_page),
        "filtered_total": page_obj.paginator.count,
    }
    catalog_masthead_chips = [
        {"label": "Available", "value": str(catalog_stats["apps"]), "tone": "info"},
        {
            "label": "Verified publishers",
            "value": str(catalog_stats["verified_publishers"]),
            "tone": "success",
        },
        {"label": "Installed", "value": str(catalog_stats["installed"]), "tone": "neutral"},
    ]
    catalog_counts = get_platform_catalog_counts()
    platform_pack_catalog = {}
    try:
        platform_pack_catalog = load_platform_pack_catalog()
    except (OSError, ValueError, json.JSONDecodeError):
        logger.debug("tenant_app_catalog: pack catalog load skipped", exc_info=True)
    plan_context = _tenant_plan_display_context(school)
    catalog_install_app_id = None
    raw_install = (request.GET.get("install_app") or "").strip()
    if raw_install.isdigit():
        cand = int(raw_install)
        valid_app_ids = {lst.app_id for lst in installable}
        if cand in valid_app_ids:
            catalog_install_app_id = cand
    browse_q = request.GET.copy()
    browse_q.pop("page", None)
    pagination_extra_query = browse_q.urlencode()
    record_tenant_surface_view(
        surface="tenant_app_catalog",
        request=request,
        extra={
            "listings_count": len(installable),
            "plan_tier": plan_context.get("tier_key"),
        },
    )
    from apps.platform_runtime.operational_center_nav import tenant_app_catalog_frame_context

    return render(
        request,
        "marketplace/tenant_app_catalog.html",
        {
            "listings": listings_page,
            "page_obj": page_obj,
            "pagination_extra_query": pagination_extra_query,
            "school": school,
            "installed_slugs": installed_slugs,
            "catalog_stats": catalog_stats,
            "catalog_counts": catalog_counts,
            "catalog_filters": catalog_filters,
            "catalog_outcomes": catalog_outcomes,
            "catalog_masthead_chips": catalog_masthead_chips,
            "catalog_policy_healthy": catalog_policy_healthy,
            "install_impact_preview_url": reverse("tenant_install_impact_preview"),
            "phase9_links": build_phase9_ecosystem_links(),
            "platform_pack_catalog": platform_pack_catalog,
            "plan_context": plan_context,
            "catalog_install_app_id": catalog_install_app_id,
            "sandbox_queue_url": f'{reverse("tenant_installed_apps")}?phase=sandbox',
            **tenant_app_catalog_frame_context(),
        },
    )


@login_required
@tenant_marketplace_manage_required
@require_GET
def tenant_install_impact_preview(request):
    """N17: JSON impact preview before sandbox install (tenant school context)."""
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"error": "No school context."}, status=400)
    app_id = request.GET.get("app_id")
    if not app_id:
        return JsonResponse({"error": "app_id required"}, status=400)
    app = get_object_or_404(MarketplaceApp, pk=app_id, is_active=True)
    return JsonResponse(build_tenant_install_impact(school, app))


@login_required
@user_passes_test(_control_plane_access)
@require_GET
def super_install_impact_preview(request):
    """N17: JSON for control-plane catalog (requires school_id)."""
    app_id = request.GET.get("app_id")
    school_id = request.GET.get("school_id")
    if not app_id or not school_id:
        return JsonResponse({"error": "app_id and school_id required"}, status=400)
    from apps.schools.models import School

    school = School.objects.filter(pk=school_id, is_active=True).first()
    if not school:
        return JsonResponse({"error": "School not found."}, status=404)
    app = get_object_or_404(MarketplaceApp, pk=app_id, is_active=True)
    return JsonResponse(build_tenant_install_impact(school, app))


@login_required
@tenant_marketplace_manage_required
@enforce_tenant_security(action="admin", require_school=False)
@require_POST
def tenant_install_app(request):
    """
    Tenant: install app for current school with **explicit per-scope consent**.

    Pillar 4 (sandboxed marketplace security): the install POST MUST carry one
    ``consented_scopes`` value per scope the manifest declares. The backend
    refuses install if any required scope is missing from the consented list,
    and writes a ``compliance.AuditLog.PERMISSION_GRANT`` capturing the exact
    scope list the admin acknowledged.
    """
    school = getattr(request, "school", None)
    if not school:
        messages.error(request, "No school context.")
        return redirect("tenant_installed_apps")
    app_id = request.POST.get("app_id") or request.POST.get("app")
    if not app_id:
        messages.error(request, "Select an app.")
        return redirect("tenant_app_catalog")
    if request.POST.get("install_after_impact_preview") != "1":
        messages.error(
            request,
            "Use “Review impact & install” and confirm from the impact preview dialog (N17).",
        )
        return redirect("tenant_app_catalog")
    app = get_object_or_404(MarketplaceApp, pk=app_id, is_active=True)
    manifest = normalize_platform_manifest(
        app.manifest,
        app_slug=app.slug,
        app_name=app.name,
        version=app.version,
        publisher_slug="",
    )
    ent = entitlement_hints_for_school(school, manifest)
    if ent.get("blocked"):
        messages.error(
            request,
            ent.get("upgrade_message") or "Plan or module requirements not met for this app.",
        )
        return redirect("tenant_app_catalog")

    # Pillar 4: explicit, per-scope consent gate.
    declared_scope_codes = sorted(
        {(s or "").strip() for s in app.scopes.values_list("scope_code", flat=True) if (s or "").strip()}
    )
    consented_scopes = sorted(
        {(s or "").strip() for s in request.POST.getlist("consented_scopes") if (s or "").strip()}
    )
    missing_consent = [c for c in declared_scope_codes if c not in consented_scopes]
    if missing_consent:
        messages.error(
            request,
            "Install blocked: the following permission scope(s) were not "
            "explicitly confirmed in the consent dialog: "
            + ", ".join(missing_consent),
        )
        return redirect("tenant_app_catalog")

    target_version = (request.POST.get("target_version") or "").strip() or None
    try:
        installation = install_app(
            school,
            app,
            installed_by=request.user,
            install_phase=AppInstallation.InstallPhase.SANDBOX,
            skip_compatibility=False,
            grant_scope_codes=consented_scopes,
            target_version=target_version,
        )
        # Compliance audit: capture the EXACT scope list the admin acknowledged.
        try:
            from apps.compliance.models_audit import AuditLog as ComplianceAuditLog

            ComplianceAuditLog.objects.create(
                user=request.user,
                action=ComplianceAuditLog.Action.PERMISSION_GRANT,
                model_name="AppInstallation",
                object_id=str(installation.pk),
                object_repr=f"{app.slug} @ {school.slug}",
                sensitivity=ComplianceAuditLog.Sensitivity.HIGH,
                new_values={
                    "app_id": app.pk,
                    "app_slug": app.slug,
                    "school_id": str(school.pk),
                    "school_slug": school.slug,
                    "installation_id": installation.pk,
                    "scopes_consented": consented_scopes,
                },
                app_label="marketplace",
                reason="Marketplace install — per-scope consent",
            )
        except (ImportError, AttributeError, TypeError, ValueError) as exc:
            logger.warning("Compliance AuditLog write failed for install: %s", exc)
        messages.success(
            request,
            f"App “{app.name}” has been installed in sandbox mode. Review it, then activate.",
        )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("tenant_installed_apps")


@login_required
@tenant_marketplace_manage_required
@enforce_tenant_security(action="admin", require_school=False)
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
    inst = get_object_or_404(
        AppInstallation, pk=installation_id, school=school, uninstalled_at__isnull=True
    )
    try:
        uninstall_app(school, inst.app, uninstalled_by=request.user)
        messages.success(request, f"App “{inst.app.name}” has been uninstalled.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("tenant_installed_apps")


@login_required
@tenant_marketplace_manage_required
@require_GET
def tenant_scope_consent(request):
    """Tenant: list pending scope grants and approve (elevated approval for sensitive scopes)."""
    school = getattr(request, "school", None)
    if not school:
        return render(
            request,
            "marketplace/tenant_scope_consent.html",
            {
                "pending_grants": [],
                "pending_grant_rows": [],
                "granted_grants": [],
                "granted_grant_rows": [],
                "school": None,
            },
        )
    pending_grants = list(
        ScopeGrant.objects.filter(
            installation__school=school,
            status=ScopeGrant.GrantStatus.PENDING,
        )
        .select_related("installation", "installation__app", "scope")
        .order_by("installation__app__name", "scope__scope_code")
    )
    granted_grants = list(
        ScopeGrant.objects.filter(
            installation__school=school,
            status=ScopeGrant.GrantStatus.GRANTED,
        )
        .select_related("installation", "installation__app", "scope")
        .order_by("-granted_at", "installation__app__name", "scope__scope_code")[:200]
    )
    grant_rows_pending = []
    for g in pending_grants:
        sc = g.scope
        grant_rows_pending.append(
            {
                "grant": g,
                "access_tier": classify_scope_access(
                    sc.scope_code, sensitive=getattr(sc, "sensitive", False)
                ),
            }
        )
    grant_rows_ok = []
    for g in granted_grants:
        sc = g.scope
        grant_rows_ok.append(
            {
                "grant": g,
                "access_tier": classify_scope_access(
                    sc.scope_code, sensitive=getattr(sc, "sensitive", False)
                ),
            }
        )
    return render(
        request,
        "marketplace/tenant_scope_consent.html",
        {
            "pending_grants": pending_grants,
            "pending_grant_rows": grant_rows_pending,
            "granted_grants": granted_grants,
            "granted_grant_rows": grant_rows_ok,
            "school": school,
        },
    )


@login_required
@tenant_marketplace_manage_required
@enforce_tenant_security(action="admin", require_school=False)
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
@tenant_marketplace_manage_required
@enforce_tenant_security(action="admin", require_school=False)
@require_POST
def tenant_save_installation_config(request):
    """
    Merge tenant-safe config keys listed in manifest ``tenant_editable_config_keys`` only.
    All other manifest configuration remains read-only in the UI.
    """
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
        uninstalled_at__isnull=True,
        status=AppInstallation.Status.ACTIVE,
    )
    manifest = normalize_platform_manifest(
        inst.app.manifest,
        app_slug=inst.app.slug,
        app_name=inst.app.name,
        version=inst.app.version,
    )
    if not manifest.get("configurable", True):
        messages.error(request, "This app is not configurable.")
        return redirect("tenant_installed_apps")
    allowed = manifest.get("tenant_editable_config_keys") or []
    if not allowed:
        messages.error(
            request,
            "Tenant configuration is read-only for this app (manifest has no editable keys).",
        )
        return redirect("tenant_installed_apps")
    cfg = dict(inst.config or {})
    for key in allowed:
        field = f"tenant_cfg_{key}"
        if field in request.POST:
            cfg[key] = (request.POST.get(field) or "").strip()
    inst.config = cfg
    inst.save(update_fields=["config"])
    messages.success(
        request,
        f"Saved configuration for “{inst.app.name}”.",
    )
    return redirect("tenant_installed_apps")


@login_required
@tenant_marketplace_manage_required
@enforce_tenant_security(action="admin", require_school=False)
@require_GET
def app_purchase_intent(request, app_id: int):
    """
    Route free/included apps to the catalog; paid/enterprise toward billing checkout
    or plan summary. Never simulates a completed purchase.
    """
    school = getattr(request, "school", None)
    if not school:
        messages.error(request, "No school context.")
        return redirect("tenant_app_catalog")
    app = get_object_or_404(MarketplaceApp, pk=app_id, is_active=True)
    listing_for_gate = getattr(app, "listing", None)
    if listing_for_gate is not None and getattr(
        listing_for_gate, "kill_switch_active", False
    ):
        messages.info(
            request,
            "This marketplace listing is temporarily unavailable.",
        )
        return redirect("tenant_app_catalog")
    pub = getattr(getattr(app, "publisher", None), "slug", "") or ""
    manifest = normalize_platform_manifest(
        app.manifest,
        app_slug=app.slug,
        app_name=app.name,
        version=app.version or "",
        publisher_slug=pub,
    )
    pt = str(manifest.get("pricing_type") or "").strip().lower()
    freeish = pt in (
        "",
        "free",
        "included",
        str(PRICING_FREE).lower(),
        str(PRICING_INCLUDED).lower(),
    )
    if freeish:
        base = reverse("tenant_app_catalog")
        return redirect(f"{base}?focus_app={app.pk}")
    if pt in (str(PRICING_PAID).lower(), str(PRICING_ENTERPRISE).lower(), "enterprise"):
        cfg = get_active_stripe_processor_config()
        sku = str(manifest.get("billing_sku") or "").strip()
        if cfg and stripe_secret_key(cfg):
            if not sku:
                messages.info(
                    request,
                    "Paid apps require a billing_sku mapped to Stripe in the platform catalog. "
                    "Your operator must set the SKU and Stripe price before checkout can start.",
                )
                return redirect(reverse("siteconfig:billing_plan_readonly"))
            q = urlencode({"marketplace_app_id": app.pk})
            return redirect(f"{reverse('siteconfig:billing_checkout_start')}?{q}")
        messages.info(
            request,
            "Billing checkout is unavailable or your plan is not set. "
            "Review Plan & entitlements or contact your operator.",
        )
        return redirect(reverse("siteconfig:billing_plan_readonly"))
    return redirect("tenant_app_catalog")


@login_required
@tenant_marketplace_manage_required
@enforce_tenant_security(action="admin", require_school=False)
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
    try:
        activate_sandbox_installation(inst, activated_by=request.user)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("tenant_installed_apps")
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
        from apps.marketplace.sandbox_embed_registry import resolve_sandbox_iframe_src

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
            iframe_src = resolve_sandbox_iframe_src(
                app_slug=app_slug,
                widget_config=wconfig if isinstance(wconfig, dict) else {},
                widget_id=widget_id,
                request=request,
            )
    if not iframe_src:
        iframe_src = ""
    elif not iframe_src.startswith(("http://", "https://")):
        # Chromeless embed: preview the target surface's CONTENT without the full
        # portal shell (header/sidebar/footer). portal_base renders
        # data-rmc-embed on <html> for ?rmc_embed=1 and css/rmc-embed.css hides
        # the chrome. Only same-origin (relative) surfaces get the flag; external
        # third-party widget URLs are left untouched.
        sep = "&" if "?" in iframe_src else "?"
        iframe_src = f"{iframe_src}{sep}rmc_embed=1"
    frame_ancestors = "'self'"
    _embed_parse_errors = (ValueError, TypeError, AttributeError, KeyError)
    if iframe_src and (
        iframe_src.startswith("http://") or iframe_src.startswith("https://")
    ):
        from urllib.parse import urlparse

        try:
            parsed = urlparse(iframe_src)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            frame_ancestors = f"'self' {origin}"
        except _embed_parse_errors:
            pass
    # Origin check: only allow embed to be loaded from our own origins (Referer/Origin)
    request_origin = request.META.get("HTTP_ORIGIN") or request.META.get(
        "HTTP_REFERER", ""
    )
    if request_origin:
        from urllib.parse import urlparse
        from django.conf import settings

        try:
            parsed = urlparse(request_origin)
            host = (parsed.netloc or "").split(":")[0]
            allowed = list(getattr(settings, "ALLOWED_HOSTS", [])) or [
                "localhost",
                "127.0.0.1",
            ]
            if (
                host
                and host not in allowed
                and not any(
                    host == h.lstrip(".") or host.endswith("." + h.lstrip("."))
                    for h in allowed
                    if isinstance(h, str) and h.startswith(".")
                )
            ):
                return HttpResponse(
                    "<p>Embed not allowed from this origin.</p>",
                    content_type="text/html",
                    status=403,
                )
        except _embed_parse_errors:
            pass
    safe_src = (
        (iframe_src or "about:blank")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    sandbox_attr = "sandbox allow-scripts allow-same-origin"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>App Sandbox</title></head>
<body>
<div class="sandbox-container">
  <iframe src="{safe_src}" {sandbox_attr} title="App widget" style="width:100%;height:80vh;border:0;"></iframe>
</div>
</body></html>"""
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-src 'self' https:; frame-ancestors {frame_ancestors}"
    )
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response
