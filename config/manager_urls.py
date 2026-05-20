"""
Manager host URL configuration (manager.runmycampus.com).
Dedicated for super-admin and operations access.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import include, path, reverse

from apps.api.user_preferences_api import ControlPlanePreferencesAPI
from apps.billing import api_views as billing_api_views
from apps.billing.models import TenantSubscription
from apps.observability import views as obs_views
from apps.observability.models import PlatformIncident
from apps.platform_runtime.views_administration import internal_admin_alias_redirect
from apps.schools.models import School
from apps.schools.marketing_views import marketing_page
from apps.schools.section8_views import find_school, global_login_discovery
from apps.schools.control_plane import (
    require_control_plane_access,
    user_has_control_plane_access,
)
from config.admin import platform_admin_site

# Shared error handlers (avoid circular import via config.urls during urlconf load).
from config.error_handlers import (
    page_not_found as handler404_view,
    permission_denied as handler403_view,
    server_error as handler500_view,
    service_unavailable as handler503_view,
)

handler403 = handler403_view
handler404 = handler404_view
handler500 = handler500_view
handler503 = handler503_view


def manager_home(request):
    if request.user.is_authenticated:
        if user_has_control_plane_access(request.user):
            return redirect("super:dashboard")
        return redirect("accounts:redirect")
    return redirect("accounts:login")


def offline_page(request):
    return render(request, "offline.html", status=200)


@require_control_plane_access
def manager_offline_sync_center(request):
    return render(request, "platform_runtime/manager_offline_sync_center.html", status=200)


def manager_help(request):
    """Operator Help Center hub (KB is one section, not the whole center)."""
    from django.urls import reverse

    return redirect(reverse("manager_help_center"))


def manager_support_request(request):
    from config.manager_operator_support import manager_support_request as _view

    return _view(request)


def manager_feedback(request):
    from django.urls import reverse

    return redirect(reverse("manager_feedback_loop"))


def manager_notifications(request):
    return redirect("super:command_center")


@require_control_plane_access
def manager_public_to_product_matrix(request):
    """Wave 6 (v2.77): operator-facing matrix of public promises vs product delivery.

    Reads from `apps.schools.public_product_promise_matrix.PUBLIC_TO_PRODUCT_PROMISES`
    and resolves every `public_route_name` + `product_route_name` so the operator
    can verify each promise still lands somewhere real. Drift here = marketing
    overshoot.
    """
    from django.urls import NoReverseMatch, reverse
    from apps.schools.public_product_promise_matrix import (
        all_promises,
        status_counts,
    )

    rows = []
    for promise in all_promises():
        public_url = None
        public_resolve_error = None
        try:
            public_url = reverse(promise["public_route_name"])
        except NoReverseMatch as e:
            public_resolve_error = str(e)

        product_url = None
        product_resolve_error = None
        product_name = promise.get("product_route_name")
        if product_name:
            try:
                product_url = reverse(
                    product_name, kwargs=promise.get("product_route_kwargs") or {}
                )
            except NoReverseMatch as e:
                product_resolve_error = str(e)

        rows.append(
            {
                **promise,
                "public_url": public_url,
                "public_resolve_error": public_resolve_error,
                "product_url": product_url,
                "product_resolve_error": product_resolve_error,
                "is_broken": bool(
                    public_resolve_error
                    or (product_name and product_resolve_error)
                ),
            }
        )

    return render(
        request,
        "schools/manager_public_to_product_matrix.html",
        {
            "rows": rows,
            "counts": status_counts(),
            "broken_count": sum(1 for r in rows if r["is_broken"]),
        },
    )


@require_control_plane_access
def manager_feature_gap_register(request):
    """Operator-facing feature-gap register surface.

    Reads from `apps.schools.feature_gap_register.FEATURE_REGISTER` and resolves
    each row's proof (route / model / mgmt command / CI gate). Drift here = we
    are claiming a feature with no working proof.
    """
    from django.apps import apps as django_apps
    from django.urls import NoReverseMatch, reverse
    from apps.schools.feature_gap_register import features_by_domain

    rows_by_domain = []
    total = 0
    shipped = 0
    broken = 0
    for domain, features in sorted(features_by_domain().items()):
        domain_rows = []
        for f in features:
            total += 1
            proof_resolved = False
            proof_url = None
            proof_error = None
            if f.proof_route_name:
                try:
                    proof_url = reverse(f.proof_route_name)
                    proof_resolved = True
                except NoReverseMatch as e:
                    proof_error = str(e)
            elif f.proof_model:
                try:
                    app_label, model_name = f.proof_model.split(".", 1)
                    django_apps.get_model(app_label, model_name)
                    proof_resolved = True
                except (LookupError, ValueError) as e:
                    proof_error = str(e)
            elif f.proof_ci_gate or f.proof_management_command:
                proof_resolved = True
            else:
                proof_error = "No proof source declared."

            is_broken = f.status == "shipped" and not proof_resolved
            if f.status == "shipped":
                shipped += 1
            if is_broken:
                broken += 1
            domain_rows.append(
                {
                    **f.to_dict(),
                    "proof_url": proof_url,
                    "proof_error": proof_error,
                    "is_broken": is_broken,
                }
            )
        rows_by_domain.append({"domain": domain, "features": domain_rows})

    return render(
        request,
        "schools/manager_feature_gap_register.html",
        {
            "rows_by_domain": rows_by_domain,
            "total": total,
            "shipped": shipped,
            "broken": broken,
        },
    )


def manager_legacy_surface_redirect(request, surface: str, remaining: str = ""):
    del remaining
    destination = (
        "super:billing_dashboard" if surface == "finance" else "super:dashboard"
    )
    return redirect(destination)


def _subscription_plan_label(subscription: TenantSubscription) -> str:
    plan = getattr(subscription, "plan", None)
    if plan and getattr(plan, "name", None):
        return plan.name
    return "plan"


@require_control_plane_access
def manager_search_api(request):
    urlconf = getattr(request, "urlconf", None)
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        query_lower = query.lower()
        results = []
        static_catalog = _manager_search_static_catalog(urlconf)
        if not query_lower:
            # Empty query: show a broader intent strip (BR-02 / §8.0.4); include the full
            # static catalog so curated tails (e.g. Workflow simulator) are not truncated.
            results = list(static_catalog)
        else:
            for item in static_catalog:
                haystack = f"{item['title']} {item['description']} {' '.join(item['meta'])}".lower()
                if query_lower in haystack:
                    results.append(item)
        return JsonResponse({"results": results})

    query_lower = query.lower()
    results: list[dict[str, object]] = []

    static_catalog = _manager_search_static_catalog(urlconf)
    for item in static_catalog:
        haystack = (
            f"{item['title']} {item['description']} {' '.join(item['meta'])}".lower()
        )
        if query_lower in haystack:
            results.append(item)

    school_matches = School.objects.filter(
        Q(name__icontains=query) | Q(slug__icontains=query)
    ).order_by("name")[:6]
    for school in school_matches:
        results.append(
            {
                "title": school.name,
                "description": f"Tenant {school.slug}",
                "url": f"{reverse('super:dashboard', urlconf=urlconf)}?tenant={school.slug}",
                "type": "class",
                "meta": [school.country_code or "Tenant"],
            }
        )

    incident_matches = PlatformIncident.objects.filter(
        Q(title__icontains=query)
        | Q(summary__icontains=query)
        | Q(source_system__icontains=query)
        | Q(incident_type__icontains=query)
    ).order_by("-created_at")[:5]
    for incident in incident_matches:
        results.append(
            {
                "title": incident.title,
                "description": incident.summary
                or incident.source_system
                or "Platform incident",
                "url": reverse("platform_incidents_console", urlconf=urlconf),
                "type": "alert",
                "meta": [incident.status, incident.severity],
            }
        )

    subscription_matches = (
        TenantSubscription.objects.select_related("billing_account__school", "plan")
        .filter(
            Q(status__icontains=query)
            | Q(plan__name__icontains=query)
            | Q(billing_account__school__name__icontains=query)
        )
        .order_by("-updated_at")[:5]
    )
    for subscription in subscription_matches:
        school = getattr(subscription.billing_account, "school", None)
        tenant_slug = getattr(school, "slug", "")
        label = school.name if school else str(subscription.billing_account)
        results.append(
            {
                "title": f"{label} subscription",
                "description": f"{_subscription_plan_label(subscription)} - {subscription.status}",
                "url": f"{reverse('super:billing_dashboard', urlconf=urlconf)}?tenant={tenant_slug}",
                "type": "invoice",
                "meta": [subscription.status],
            }
        )

    return JsonResponse({"results": results[:12]})


def _manager_search_static_catalog(urlconf=None):
    # §8 Click compression: intents per CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL (≤3 clicks)
    def url(name, **kwargs):
        return reverse(name, urlconf=urlconf, kwargs=kwargs or None)

    return [
        {
            "title": "Migration Cloud",
            "description": "Start migrations, inspect bundles, review health, audit chains, tokens, and webhooks.",
            "url": url("super:migration_cloud"),
            "type": "app",
            "meta": ["Migration Cloud", "Imports", "Readiness"],
        },
        {
            "title": "Start migration",
            "description": "Create a Migration Cloud bundle from a vendor export or canonical template.",
            "url": url("migration_cloud_super:bundle_new"),
            "type": "app",
            "meta": ["Migration Cloud", "Intake"],
        },
        {
            "title": "Migration Cloud health",
            "description": "Webhook, MAA, companion upload, keypair, sunset, and scanner readiness.",
            "url": url("migration_cloud_super:migration_cloud_health"),
            "type": "alert",
            "meta": ["Migration Cloud", "Health"],
        },
        {
            "title": "Public-to-Product matrix",
            "description": "Verify public promises against product routes and proof surfaces.",
            "url": url("manager_public_to_product_matrix"),
            "type": "report",
            "meta": ["Readiness", "Proof"],
        },
        {
            "title": "Feature gap register",
            "description": "Operator register for shipped features, proof routes, models, commands, and CI gates.",
            "url": url("manager_feature_gap_register"),
            "type": "report",
            "meta": ["Readiness", "Feature gaps"],
        },
        {
            "title": "Feedback loop",
            "description": "Live usage, friction, feedback submissions, and AI-assistant adoption signals.",
            "url": url("manager_feedback_loop"),
            "type": "report",
            "meta": ["Readiness", "Voice of customer"],
        },
        {
            "title": "Lane-2 readiness",
            "description": "PSP, SOC2 evidence, and pilot readiness scoreboard for external work.",
            "url": url("manager_lane2_readiness"),
            "type": "report",
            "meta": ["Readiness", "PSP", "SOC2", "Pilots"],
        },
        {
            "title": "Open report library",
            "description": "Report packs, letters, and report card builder hub.",
            "url": f"{url('studio_os:output')}?pane=reports",
            "type": "report",
            "meta": ["Studio Output", "Report library"],
        },
        {
            "title": "Feature control",
            "description": "Feature flags and capabilities.",
            "url": url("studio_os:control"),
            "type": "class",
            "meta": ["Studio Control", "Feature flags"],
        },
        {
            "title": "Launch checklist",
            "description": "Launch readiness and setup studio.",
            "url": url("studio_os:launch"),
            "type": "student",
            "meta": ["Studio Launch", "Setup"],
        },
        {
            "title": "Studio Output",
            "description": "Report library hub, document library, IDs, branding, policy.",
            "url": f"{url('studio_os:output')}?pane=reports",
            "type": "report",
            "meta": ["Studio", "Reports"],
        },
        {
            "title": "Tenant Mission Control",
            "description": "Global tenant registry, readiness, and platform posture.",
            "url": url("super:dashboard"),
            "type": "report",
            "meta": ["Control plane"],
        },
        {
            "title": "Schools list",
            "description": "Paginated tenant directory, sector filters, and links to tenant 360.",
            "url": url("super:schools_list"),
            "type": "class",
            "meta": ["Control plane", "Tenants", "Directory"],
        },
        {
            "title": "Analytics overview",
            "description": "Fleet analytics, observability entry points, and chart reference patterns.",
            "url": url("super:analytics_overview"),
            "type": "report",
            "meta": ["Control plane", "Analytics", "Observability"],
        },
        {
            "title": "Mission Queues",
            "description": "Approvals, incidents, provisioning breaches, and operator backlog.",
            "url": url("super:command_center"),
            "type": "class",
            "meta": ["Queues"],
        },
        {
            "title": "Platform Billing",
            "description": "Subscriptions, trials, and revenue exceptions.",
            "url": url("super:billing_dashboard"),
            "type": "invoice",
            "meta": ["Billing"],
        },
        {
            "title": "Marketplace Governance",
            "description": "Publishers, app review queue, kill switches, and revenue-share posture.",
            "url": url("super:marketplace_governance"),
            "type": "app",
            "meta": ["Marketplace"],
        },
        {
            "title": "Blueprint Marketplace",
            "description": "Apply policy packs (e.g. Cameroon Francophone, UAE MoE+IB) to a school.",
            "url": url("super:blueprint_marketplace"),
            "type": "app",
            "meta": ["Marketplace", "Phase 6"],
        },
        {
            "title": "App Catalog",
            "description": "Install approved marketplace apps for a school.",
            "url": url("super:app_catalog"),
            "type": "app",
            "meta": ["Marketplace", "Phase 6"],
        },
        {
            "title": "Platform Incidents",
            "description": "Operator incident console and escalation status.",
            "url": url("platform_incidents_console"),
            "type": "alert",
            "meta": ["Observability"],
        },
        {
            "title": "Provision Tenant",
            "description": "Launch the tenant onboarding wizard.",
            "url": url("super:create_school_wizard"),
            "type": "student",
            "meta": ["Provisioning"],
        },
        {
            "title": "Geography (region packs)",
            "description": "Wedges 7–13 continent packs, compare US/CAN/GBR, Create school with pack.",
            "url": url("super:geography"),
            "type": "class",
            "meta": ["Geography", "Region packs", "Wedges", "GTM"],
        },
        {
            "title": "Trust center",
            "description": "Security & trust hub; residency, compliance, audit export, platform events.",
            "url": url("super:trust_center"),
            "type": "class",
            "meta": ["Trust", "Security", "Compliance"],
        },
        {
            "title": "Operator policy",
            "description": "Governance, break-glass, change classes, metrics and automation API pointers.",
            "url": url("super:operator_policy"),
            "type": "class",
            "meta": ["Policy", "Governance", "Control plane"],
        },
        {
            "title": "Backlog unlock center",
            "description": "Machine-evaluated gates and program tracks; refresh after merges or CI.",
            "url": url("super:backlog_unlock_center"),
            "type": "class",
            "meta": ["Backlog", "Gates", "CI"],
        },
        {
            "title": "Fleet governed changes",
            "description": "Cross-tenant change records and legal status transitions.",
            "url": url("super:fleet_governed_changes"),
            "type": "class",
            "meta": ["Fleet", "Governance", "Change"],
        },
        {
            "title": "Platform operator hub",
            "description": "Curated super URLs plus platform-admin changelists in one screen (single-pane entry).",
            "url": url("super:platform_operator_hub"),
            "type": "class",
            "meta": ["Operator hub", "Super", "Platform admin"],
        },
        {
            "title": "Playbook operator hub",
            "description": "Migration playbook audit, execution log filters, and curated operator deep links.",
            "url": url("super:playbook_operator_hub"),
            "type": "class",
            "meta": ["Automation", "Playbooks", "Control plane"],
        },
        {
            "title": "Runtime truth hub",
            "description": "Read-only RuntimeDefaults payload preview and slim SiteSettings singleton.",
            "url": url("super:runtime_truth_hub"),
            "type": "class",
            "meta": ["Runtime", "Phase B", "Control plane"],
        },
        {
            "title": "Metadata & lineage hub",
            "description": "Entity catalog, governance search, lineage graph, feature control, and tenant runtime links.",
            "url": url("siteconfig:metadata_operator_hub"),
            "type": "class",
            "meta": ["Metadata", "Catalog", "Lineage", "Control plane"],
        },
        {
            "title": "Workflow simulator",
            "description": "Simulate workflow resolution for a school and role (control plane).",
            "url": url("super:workflow_simulator"),
            "type": "class",
            "meta": ["Workflows", "Control plane"],
        },
    ]


from apps.siteconfig.views_manifest import (  # noqa: E402
    platform_manifest as _platform_manifest,
    portal_manifest as _portal_manifest,
)
from apps.siteconfig.views_manifest_icon import (  # noqa: E402
    icon_any as _manifest_icon_any,
    icon_maskable as _manifest_icon_maskable,
)
from apps.portal.views_ai_copilot import (  # noqa: E402
    ai_health as _ai_health,
    ai_copilot_query as _ai_copilot_query,
)


urlpatterns = [
    path("", manager_home, name="home"),
    path("", manager_home, name="manager_home"),
    path("offline/", offline_page, name="offline"),
    path("offline/sync/", manager_offline_sync_center, name="manager_offline_sync_center"),
    path("manifest.json", _platform_manifest, name="pwa_manifest_platform"),
    path("manifest-portal.json", _portal_manifest, name="pwa_manifest_portal"),
    path("manifest/icon-<int:size>.png", _manifest_icon_any, name="pwa_manifest_icon_any"),
    path("manifest/icon-<int:size>-maskable.png", _manifest_icon_maskable, name="pwa_manifest_icon_maskable"),
    path("api/ai/health/", _ai_health, name="ai_health"),
    path("api/ai-copilot/validate/", _ai_copilot_query, name="ai_copilot_query"),
    path("-/version/", obs_views.public_version, name="public_version"),
    path("help/", manager_help, name="manager_help"),
    path(
        "help-center/",
        __import__(
            "config.manager_help_center", fromlist=["manager_help_center"]
        ).manager_help_center,
        name="manager_help_center",
    ),
    path(
        "help-center/ai-review/",
        __import__(
            "config.manager_ai_review_queue", fromlist=["manager_ai_review_queue"]
        ).manager_ai_review_queue,
        name="manager_ai_review_queue",
    ),
    path(
        "help-center/analytics/",
        __import__(
            "config.manager_help_analytics", fromlist=["manager_help_analytics"]
        ).manager_help_analytics,
        name="manager_help_analytics",
    ),
    path(
        "help-center/locale-families/",
        __import__(
            "config.manager_kb_locale_families",
            fromlist=["manager_kb_locale_families"],
        ).manager_kb_locale_families,
        name="manager_kb_locale_families",
    ),
    path(
        "feature-center/",
        __import__(
            "config.manager_help_engagement", fromlist=["manager_feature_center"]
        ).manager_feature_center,
        name="manager_feature_center",
    ),
    path(
        "contact-us/",
        __import__(
            "config.manager_help_engagement", fromlist=["manager_contact_us"]
        ).manager_contact_us,
        name="manager_contact_us",
    ),
    path(
        "product-roadmap/",
        __import__(
            "config.manager_help_engagement", fromlist=["manager_product_roadmap"]
        ).manager_product_roadmap,
        name="manager_product_roadmap",
    ),
    path("", include(("apps.feedback.urls", "feedback"), namespace="feedback")),
    path("support/", manager_support_request, name="manager_support_request"),
    path("feedback/", manager_feedback, name="manager_feedback"),
    path("notifications/", manager_notifications, name="manager_notifications"),
    path(
        "public-to-product/",
        manager_public_to_product_matrix,
        name="manager_public_to_product_matrix",
    ),
    path(
        "feature-gap-register/",
        manager_feature_gap_register,
        name="manager_feature_gap_register",
    ),
    path(
        "feedback-loop/",
        __import__("config.manager_feedback_loop", fromlist=["manager_feedback_loop"]).manager_feedback_loop,
        name="manager_feedback_loop",
    ),
    path(
        "lane2-readiness/",
        __import__("config.manager_lane2_readiness", fromlist=["manager_lane2_readiness"]).manager_lane2_readiness,
        name="manager_lane2_readiness",
    ),
    # v2.94 — cross-school integrations rollup for the operations team.
    path(
        "integrations-rollup/",
        __import__(
            "apps.integrations_marketplace.manager_views",
            fromlist=["manager_integrations_rollup"],
        ).manager_integrations_rollup,
        name="manager_integrations_rollup",
    ),
    # v3.4 — district-level bulk pre-stage of OAuth integrations.
    path(
        "integrations-bulk-prestage/",
        __import__(
            "apps.integrations_marketplace.manager_views",
            fromlist=["manager_bulk_prestage"],
        ).manager_bulk_prestage,
        name="manager_integrations_bulk_prestage",
    ),
    path("internal-admin/", internal_admin_alias_redirect, name="internal_admin"),
    path("internal-admin/<path:remaining>", internal_admin_alias_redirect),
    path(
        "admin/siteconfig/customizer/",
        __import__(
            "apps.siteconfig.legacy_redirects",
            fromlist=["legacy_customizer_redirect"],
        ).legacy_customizer_redirect,
    ),
    path("admin/", platform_admin_site.urls),
    path(
        "authentication/",
        include(("apps.accounts.urls", "accounts"), namespace="accounts"),
    ),
    path("super/", include(("apps.schools.super_urls", "super"), namespace="super")),
    path(
        "super/migration/",
        include(
            ("apps.migration_cloud.urls", "migration_cloud_super"),
            namespace="migration_cloud_super",
        ),
        {"shell": "super"},
    ),
    path("sales/", include(("apps.sales.urls", "sales"), namespace="sales")),
    path(
        "siteconfig/",
        include(("apps.siteconfig.urls", "siteconfig"), namespace="siteconfig"),
    ),
    path(
        "studio/", include(("apps.studio_os.urls", "studio_os"), namespace="studio_os")
    ),
    path(
        "configuration/",
        include(
            ("apps.platform_runtime.configuration_urls", "configuration"),
            namespace="configuration",
        ),
    ),
    path(
        "automation/",
        include(("apps.automation.urls", "automation"), namespace="automation"),
    ),
    path(
        "api-center/",
        include(("apps.apicenter.urls", "apicenter"), namespace="apicenter"),
    ),
    path(
        "platform-runtime/",
        include(
            ("apps.platform_runtime.urls", "platform_runtime"),
            namespace="platform_runtime",
        ),
    ),
    path(
        "ops/incidents/",
        obs_views.platform_incidents_console,
        name="platform_incidents_console",
    ),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    path("status/", obs_views.public_status, name="status"),
    path("find/", find_school, name="find_school"),
    path("discover/", global_login_discovery, name="global_login_discovery"),
    path("api/health/", obs_views.api_health, name="api_health"),
    path(
        "api/control-plane-preferences/",
        ControlPlanePreferencesAPI.as_view(),
        name="api_control_plane_preferences",
    ),
    path("api/search/", manager_search_api, name="manager_search_api"),
    path(
        "api/internal/metadata/",
        include(("apps.metadata.urls", "metadata"), namespace="metadata"),
    ),
    path(
        "api/billing/processors/<str:processor_code>/webhook/",
        billing_api_views.platform_billing_processor_webhook,
        name="platform_billing_processor_webhook",
    ),
    path(
        "api/observability/incidents/",
        obs_views.api_platform_incidents,
        name="api_platform_incidents",
    ),
    path(
        "api/observability/incidents/<uuid:incident_id>/status/",
        obs_views.api_platform_incident_status,
        name="api_platform_incident_status",
    ),
    path(
        "api/observability/slo-dashboard/",
        obs_views.api_operational_slo_dashboard,
        name="api_operational_slo_dashboard",
    ),
    path(
        "api/weather/context/",
        obs_views.api_weather_context,
        name="api_weather_context",
    ),
    # Guided assistants for AI Center (siteconfig:ai_center). Listed after manager-only
    # api/search/, api/health/, and observability routes so those keep precedence.
    path("api/", include(("apps.api.urls", "api"), namespace="api")),
    path("api/v1/", include(("apps.api.urls_v1", "api_v1"), namespace="api_v1")),
    path(
        "portal/",
        manager_legacy_surface_redirect,
        {"surface": "portal"},
        name="manager_legacy_portal",
    ),
    path(
        "portal/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "portal"},
    ),
    path(
        "academics/",
        manager_legacy_surface_redirect,
        {"surface": "academics"},
        name="manager_legacy_academics",
    ),
    path(
        "academics/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "academics"},
    ),
    path(
        "evals/",
        manager_legacy_surface_redirect,
        {"surface": "evals"},
        name="manager_legacy_evals",
    ),
    path(
        "evals/<path:remaining>", manager_legacy_surface_redirect, {"surface": "evals"}
    ),
    path(
        "reports/",
        manager_legacy_surface_redirect,
        {"surface": "reports"},
        name="manager_legacy_reports",
    ),
    path(
        "reports/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "reports"},
    ),
    path(
        "finance/",
        manager_legacy_surface_redirect,
        {"surface": "finance"},
        name="manager_legacy_finance",
    ),
    path(
        "finance/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "finance"},
    ),
    path(
        "communication/",
        manager_legacy_surface_redirect,
        {"surface": "communication"},
        name="manager_legacy_communication",
    ),
    path(
        "communication/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "communication"},
    ),
    path("kb/", include(("apps.portal.urls_kb", "kb"), namespace="kb")),
    path(
        "legacy-kb/",
        manager_legacy_surface_redirect,
        {"surface": "kb"},
        name="manager_legacy_kb",
    ),
    path("legacy-kb/<path:remaining>", manager_legacy_surface_redirect, {"surface": "kb"}),
    path(
        "analytics/",
        manager_legacy_surface_redirect,
        {"surface": "analytics"},
        name="manager_legacy_analytics",
    ),
    path(
        "analytics/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "analytics"},
    ),
    path(
        "compliance/",
        manager_legacy_surface_redirect,
        {"surface": "compliance"},
        name="manager_legacy_compliance",
    ),
    path(
        "compliance/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "compliance"},
    ),
    path(
        "payroll/",
        manager_legacy_surface_redirect,
        {"surface": "payroll"},
        name="manager_legacy_payroll",
    ),
    path(
        "payroll/<path:remaining>",
        manager_legacy_surface_redirect,
        {"surface": "payroll"},
    ),
    path(
        "privacy/", marketing_page, {"page_slug": "privacy"}, name="marketing_privacy"
    ),
    path("terms/", marketing_page, {"page_slug": "terms"}, name="marketing_terms"),
    path(
        "cookie-policy/",
        marketing_page,
        {"page_slug": "cookie-policy"},
        name="marketing_cookie_policy",
    ),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
