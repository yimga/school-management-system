"""
Public (marketing + discovery) URL configuration for runmycampus.com.
Used when request.urlconf is set to this module by UrlConfSwitcherMiddleware.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect, render
from django.urls import include, path
from django.views.generic.base import RedirectView

from apps.observability import views as obs_views
from apps.portal.views_ai_copilot import ai_health
from apps.schools.error_views import school_not_found_public
from apps.schools.competitive_marketing_views import (
    marketing_implementation_assurance,
    marketing_pricing_packages_clarity,
    marketing_procurement_checklist,
    marketing_security_packet_request,
    marketing_story_page,
    marketing_trust_dedicated,
)
from apps.schools.marketing_competitor_views import competitor_compare_page
from apps.schools.marketing_kb_views import (
    marketing_kb_article_view,
    marketing_kb_category_view,
    marketing_kb_search_view,
    marketing_kb_typeahead_api,
)
from apps.schools.marketing_views import (
    blog_post_detail,
    buyer_toolkit_download,
    compare_marketing_page,
    developer_marketing_page,
    developer_hub,
    developer_console,
    developer_portal,
    developer_public_api_docs,
    developer_sdk,
    developer_sandbox,
    institution_marketing_page,
    marketing_funnel_dashboard,
    marketing_intent_homepage,
    marketing_personality_page,
    marketing_landing,
    marketing_verb_hub,
    marketplace_marketing_page,
    migrate_marketing_page,
    migration_simulator_page,
    setup_simulator_page,
    regional_marketing_landing,
    marketing_page,
    marketing_solutions_persona,
    role_marketing_page,
    submit_contact_request,
    submit_demo_request,
    submit_security_packet_request,
    topical_marketing_landing,
    marketing_robots_txt,
    marketing_sitemap_xml,
)
from apps.schools.section8_views import (
    verify_caddy_domain,
    global_login_discovery,
    find_school,
    public_verify_hub,
    public_support_hub,
    lti_launch,
    lti_launch_callback,
    lti_ags_lineitems,
    lti_ags_lineitem_detail,
    lti_ags_scores,
    lti_ags_results,
    lti_nrps_memberships,
    lti_deep_linking,
    jwks_json,
)
from apps.schools.views_pending_provision import api_public_pending_provision_progress
from apps.schools.views_e2e_signup_helpers import e2e_signup_verification_token
from apps.schools.signup_views import (
    signup_school,
    signup_slug_check,
    signup_slug_suggest,
    verify_signup,
    resend_signup_verification,
    api_trial_school,
    onboarding_wizard,
    onboard_migration_handoff,
    onboard_migration_start,
    brand_import_api,
)
from apps.siteconfig.views_tour import tour_steps_public_api
from apps.siteconfig.views_verify import verify_student_id
from apps.schools.activation_views import (
    ACTIVATION_FIRST_ACTION_PATH,
    ACTIVATION_FIRST_ACTION_URL_NAME,
    activation_first_action,
)
from apps.siteconfig.command_bar_registry import CommandBarActionsView
from apps.siteconfig.views_manifest import (
    platform_manifest as _platform_manifest,
    portal_manifest as _portal_manifest,
)
from apps.siteconfig.views_manifest_icon import (
    icon_any as _manifest_icon_any,
    icon_maskable as _manifest_icon_maskable,
)
from apps.schools.marketing_views_v2 import marketing_landing_v2
from apps.schools.marketing_region import MARKETING_LEGACY_REGIONAL_SHORTCUTS
from apps.schools.views_marketing_api import marketing_sandbox_validate
from apps.marketplace.urls_developer_platform import (
    public_urlpatterns as marketplace_dev_public_urlpatterns,
)


def home(request):
    return marketing_landing(request)


def offline_page(request):
    return render(request, "offline.html", status=200)


urlpatterns = [
    path("", home, name="home"),
    # Alias for tooling/checklists that expect marketing_home (same view as home).
    path("", home, name="marketing_home"),
    path("v2/", marketing_landing_v2, name="marketing_landing_v2"),
    path("storefront/", marketing_intent_homepage, name="marketing_intent_homepage"),
    path(
        "experience/<slug:personality_slug>/",
        marketing_personality_page,
        name="marketing_personality_page",
    ),
    path("offline/", offline_page, name="offline"),
    # PWA manifest endpoints (mirrored from config/urls.py so templates that emit
    # `{% url 'pwa_manifest_platform' %}` work under the public urlconf when
    # UrlConfSwitcherMiddleware swaps in this module for marketing hosts).
    path("manifest.json", _platform_manifest, name="pwa_manifest_platform"),
    path("manifest-portal.json", _portal_manifest, name="pwa_manifest_portal"),
    path(
        "manifest/icon-<int:size>.png",
        _manifest_icon_any,
        name="pwa_manifest_icon_any",
    ),
    path(
        "manifest/icon-<int:size>-maskable.png",
        _manifest_icon_maskable,
        name="pwa_manifest_icon_maskable",
    ),
    # Universal Command Bar — authenticated owners hit the public host during
    # signup verify + onboarding; base.html includes rmc_command_bar.html when
    # request.user.is_authenticated, so this route must resolve here or the
    # set-password step 500s with NoReverseMatch (2026-06-08 prod dead-end).
    # # rbac-allow: command-bar-server-filters-actions-per-user-and-tenant
    path(
        "api/command-bar/actions/",
        CommandBarActionsView.as_view(),
        name="command_bar_actions",
    ),
    # Activation landing — conversion/activation middleware reverse() this name
    # on the public host during first-run signup (before tenant subdomain live).
    path(
        ACTIVATION_FIRST_ACTION_PATH.lstrip("/"),
        activation_first_action,
        name=ACTIVATION_FIRST_ACTION_URL_NAME,
    ),
    path("-/version/", obs_views.public_version, name="public_version"),
    # SOT batch 1204 / 1199: CDN-safe aliases (identical JSON) on the public urlconf.
    path("api/system/version/", obs_views.public_version, name="api_system_version"),
    path("version.json", obs_views.public_version, name="public_version_json"),
    path(
        "authentication/",
        include(("apps.accounts.urls", "accounts"), namespace="accounts"),
    ),
    path(
        "api/pending-provision/progress/",
        api_public_pending_provision_progress,
        name="api_public_pending_provision_progress",
    ),
    path(
        "api/weather/context/",
        obs_views.api_weather_context,
        name="api_weather_context",
    ),
    path("api/ai/health/", ai_health, name="ai_health"),
    path("healthz/", obs_views.healthz, name="healthz"),
    path("health/", obs_views.public_health, name="health"),
    path("ready/", obs_views.public_health, name="ready"),
    # Health endpoint at /status/ (same as tenant/manager). Render can use /health/ or /status/ for healthCheckPath.
    path("status/", obs_views.public_status, name="status"),
    path("api/caddy-check/", verify_caddy_domain),
    path("api/v1/auth/check-domain/", verify_caddy_domain),
    # Developer discovery API (parity with config.urls — manifests, oauth, interop hub)
    path("api/", include(("apps.api.urls", "api"), namespace="api")),
    path("api/v1/", include(("apps.api.urls_v1", "api_v1"), namespace="api_v1")),
    path(
        "api/v1/oauth/",
        include(("apps.apicenter.oauth_urls", "oauth"), namespace="oauth"),
    ),
    path("api/v2/", include(("apps.api.urls_v2", "api_v2"), namespace="api_v2")),
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
    path("discover/", global_login_discovery, name="global_login_discovery"),
    path("find/", find_school, name="find_school"),
    path("verify/", public_verify_hub, name="public_verify_hub"),
    path("support/", public_support_hub, name="public_support_hub"),
    path("school-not-found/", school_not_found_public, name="school_not_found_public"),
    path("marketing/", marketing_landing, name="marketing_landing"),
    path(
        "academics/",
        RedirectView.as_view(url="/teach/academics/", permanent=False),
        name="marketing_academics_short",
    ),
    path(
        "admissions/",
        RedirectView.as_view(url="/run/admissions/", permanent=False),
        name="marketing_admissions_short",
    ),
    path(
        "finance/",
        RedirectView.as_view(url="/pay/fees/", permanent=False),
        name="marketing_finance_short",
    ),
    path("run/", marketing_verb_hub, {"verb": "run"}, name="marketing_run_hub"),
    path("teach/", marketing_verb_hub, {"verb": "teach"}, name="marketing_teach_hub"),
    path(
        "teach/academics/",
        marketing_page,
        {"page_slug": "platform-student-information-system"},
        name="marketing_teach_academics",
    ),
    path("pay/", marketing_verb_hub, {"verb": "pay"}, name="marketing_pay_hub"),
    path(
        "communicate/",
        marketing_verb_hub,
        {"verb": "communicate"},
        name="marketing_communicate_hub",
    ),
    path("grow/", marketing_verb_hub, {"verb": "grow"}, name="marketing_grow_hub"),
    path(
        "education-operating-system/",
        marketing_page,
        {"page_slug": "education-operating-system"},
        name="marketing_education_operating_system",
    ),
    path(
        "platform/",
        marketing_page,
        {"page_slug": "platform"},
        name="marketing_platform",
    ),
    path(
        "platform/education-os/",
        marketing_page,
        {"page_slug": "platform-education-os"},
        name="marketing_platform_education_os",
    ),
    path(
        "platform/control-plane/",
        marketing_page,
        {"page_slug": "platform-control-plane"},
        name="marketing_platform_control_plane",
    ),
    path(
        "platform/marketplace/",
        RedirectView.as_view(url="/grow/marketplace/", permanent=True),
        name="marketing_platform_marketplace",
    ),
    path(
        "platform/migration-cloud/",
        RedirectView.as_view(url="/grow/migration/", permanent=True),
        name="marketing_platform_migration_cloud",
    ),
    path(
        "platform/runtime/",
        marketing_page,
        {"page_slug": "platform-runtime"},
        name="marketing_platform_runtime",
    ),
    path(
        "platform/integrations/",
        marketing_page,
        {"page_slug": "platform-integrations"},
        name="marketing_platform_integrations",
    ),
    path(
        "platform/security/",
        marketing_page,
        {"page_slug": "platform-security"},
        name="marketing_platform_security",
    ),
    path(
        "platform/analytics/",
        marketing_page,
        {"page_slug": "platform-analytics"},
        name="marketing_platform_analytics",
    ),
    path(
        "platform/student-information-system/",
        marketing_page,
        {"page_slug": "platform-student-information-system"},
        name="marketing_platform_sis",
    ),
    path(
        "platform/admissions/",
        marketing_page,
        {"page_slug": "platform-admissions"},
        name="marketing_platform_admissions",
    ),
    path(
        "platform/attendance/",
        marketing_page,
        {"page_slug": "platform-attendance"},
        name="marketing_platform_attendance",
    ),
    path(
        "platform/fees-payments/",
        marketing_page,
        {"page_slug": "platform-fees-payments"},
        name="marketing_platform_fees_payments",
    ),
    path(
        "platform/grading-report-cards/",
        marketing_page,
        {"page_slug": "platform-grading-report-cards"},
        name="marketing_platform_grading_report_cards",
    ),
    path(
        "platform/parent-portal/",
        marketing_page,
        {"page_slug": "platform-parent-portal"},
        name="marketing_platform_parent_portal",
    ),
    path(
        "platform/teacher-portal/",
        marketing_page,
        {"page_slug": "platform-teacher-portal"},
        name="marketing_platform_teacher_portal",
    ),
    path(
        "platform/student-portal/",
        marketing_page,
        {"page_slug": "platform-student-portal"},
        name="marketing_platform_student_portal",
    ),
    path(
        "platform/communications/",
        marketing_page,
        {"page_slug": "platform-communications"},
        name="marketing_platform_communications",
    ),
    path(
        "platform/workflows/",
        marketing_page,
        {"page_slug": "platform-workflows"},
        name="marketing_platform_workflows",
    ),
    path(
        "platform/offline-first/",
        marketing_page,
        {"page_slug": "platform-offline-first"},
        name="marketing_platform_offline_first",
    ),
    path(
        "product/", marketing_page, {"page_slug": "product"}, name="marketing_product"
    ),
    path(
        "products/admissions/",
        marketing_page,
        {"page_slug": "products-admissions"},
        name="marketing_products_admissions",
    ),
    path(
        "products/academics/",
        marketing_page,
        {"page_slug": "products-academics"},
        name="marketing_products_academics",
    ),
    path(
        "products/finance/",
        marketing_page,
        {"page_slug": "products-finance"},
        name="marketing_products_finance",
    ),
    path(
        "products/communication/",
        marketing_page,
        {"page_slug": "products-communication"},
        name="marketing_products_communication",
    ),
    path(
        "products/automation/",
        marketing_page,
        {"page_slug": "products-automation"},
        name="marketing_products_automation",
    ),
    path(
        "products/analytics/",
        marketing_page,
        {"page_slug": "products-analytics"},
        name="marketing_products_analytics",
    ),
    path(
        "solutions/",
        marketing_page,
        {"page_slug": "solutions"},
        name="marketing_solutions",
    ),
    path(
        "solutions/head/",
        marketing_solutions_persona,
        {"persona_slug": "head"},
        name="marketing_solutions_persona_head",
    ),
    path(
        "solutions/bursar/",
        marketing_solutions_persona,
        {"persona_slug": "bursar"},
        name="marketing_solutions_persona_bursar",
    ),
    path(
        "solutions/teacher/",
        marketing_solutions_persona,
        {"persona_slug": "teacher"},
        name="marketing_solutions_persona_teacher",
    ),
    path(
        "solutions/parent/",
        marketing_solutions_persona,
        {"persona_slug": "parent"},
        name="marketing_solutions_persona_parent",
    ),
    path(
        "solutions/it/",
        marketing_solutions_persona,
        {"persona_slug": "it"},
        name="marketing_solutions_persona_it",
    ),
    path(
        "solutions/k12/",
        RedirectView.as_view(url="/solutions/k12-schools/", permanent=True),
        name="institution_k12",
    ),
    path(
        "solutions/universities/",
        institution_marketing_page,
        {"institution_slug": "universities"},
        name="institution_universities",
    ),
    path(
        "solutions/technical-schools/",
        institution_marketing_page,
        {"institution_slug": "technical-schools"},
        name="institution_technical_schools",
    ),
    path(
        "solutions/private-schools/",
        institution_marketing_page,
        {"institution_slug": "private-schools"},
        name="institution_private_schools",
    ),
    path(
        "solutions/private-schools/",
        institution_marketing_page,
        {"institution_slug": "private-schools"},
        name="marketing_solutions_private_schools",
    ),
    path(
        "solutions/government-education/",
        institution_marketing_page,
        {"institution_slug": "government-education"},
        name="institution_government_education",
    ),
    path(
        "solutions/international-schools/",
        institution_marketing_page,
        {"institution_slug": "international-schools"},
        name="institution_international_schools",
    ),
    path(
        "solutions/international-schools/",
        institution_marketing_page,
        {"institution_slug": "international-schools"},
        name="marketing_solutions_international_schools",
    ),
    path(
        "solutions/faith-based-schools/",
        institution_marketing_page,
        {"institution_slug": "faith-based-schools"},
        name="institution_faith_based_schools",
    ),
    path(
        "solutions/faith-based-schools/",
        institution_marketing_page,
        {"institution_slug": "faith-based-schools"},
        name="marketing_solutions_faith_based_schools",
    ),
    path(
        "solutions/multi-campus/",
        institution_marketing_page,
        {"institution_slug": "multi-campus"},
        name="institution_multi_campus",
    ),
    path(
        "solutions/multi-campus/",
        institution_marketing_page,
        {"institution_slug": "multi-campus"},
        name="marketing_solutions_multi_campus",
    ),
    path(
        "solutions/growing-school-networks/",
        institution_marketing_page,
        {"institution_slug": "growing-school-networks"},
        name="institution_growing_school_networks",
    ),
    path(
        "solutions/growing-school-networks/",
        institution_marketing_page,
        {"institution_slug": "growing-school-networks"},
        name="marketing_solutions_growing_school_networks",
    ),
    path(
        "solutions/k12-schools/",
        institution_marketing_page,
        {"institution_slug": "k12-schools"},
        name="institution_k12_schools",
    ),
    path(
        "solutions/k12-schools/",
        institution_marketing_page,
        {"institution_slug": "k12-schools"},
        name="marketing_solutions_k12_schools",
    ),
    path(
        "pricing/", marketing_page, {"page_slug": "pricing"}, name="marketing_pricing"
    ),
    path(
        "pricing-packages/",
        marketing_pricing_packages_clarity,
        name="marketing_pricing_packages_clarity",
    ),
    path("trust/", marketing_trust_dedicated, name="marketing_trust_dedicated"),
    path(
        "compare/<slug:slug>/",
        competitor_compare_page,
        name="marketing_competitor_compare",
    ),
    path(
        "implementation/",
        marketing_story_page,
        {"story_slug": "implementation"},
        name="marketing_story_implementation",
    ),
    path(
        "offline-first/",
        marketing_story_page,
        {"story_slug": "offline-first"},
        name="marketing_story_offline_first",
    ),
    path(
        "payments-readiness/",
        marketing_story_page,
        {"story_slug": "payments-readiness"},
        name="marketing_story_payments_readiness",
    ),
    path(
        "for-private-schools/",
        marketing_story_page,
        {"story_slug": "for-private-schools"},
        name="marketing_story_private_schools",
    ),
    path(
        "for-school-networks/",
        marketing_story_page,
        {"story_slug": "for-school-networks"},
        name="marketing_story_school_networks",
    ),
    path(
        "pilot-program/",
        marketing_story_page,
        {"story_slug": "pilot-program"},
        name="marketing_story_pilot_program",
    ),
    path(
        "procurement-checklist/",
        marketing_procurement_checklist,
        name="marketing_procurement_checklist",
    ),
    path(
        "procurement-docs/",
        RedirectView.as_view(
            pattern_name="marketing_procurement_checklist", permanent=False
        ),
        name="marketing_procurement_docs",
    ),
    path(
        "implementation-assurance/",
        marketing_implementation_assurance,
        name="marketing_implementation_assurance",
    ),
    path(
        "implementation-timelines/",
        RedirectView.as_view(
            pattern_name="marketing_implementation_assurance", permanent=False
        ),
        name="marketing_implementation_timelines",
    ),
    path(
        "portal-login/",
        RedirectView.as_view(pattern_name="global_login_discovery", permanent=False),
        name="marketing_portal_login",
    ),
    path(
        "find-campus-portal/",
        RedirectView.as_view(pattern_name="find_school", permanent=False),
        name="marketing_find_campus_portal",
    ),
    path(
        "careers/",
        marketing_page,
        {"page_slug": "careers"},
        name="marketing_careers",
    ),
    path(
        "brand-assets/",
        marketing_page,
        {"page_slug": "brand-assets"},
        name="marketing_brand_assets",
    ),
    path(
        "hardware-store/",
        marketing_page,
        {"page_slug": "hardware-store"},
        name="marketing_hardware_store",
    ),
    path(
        "training-academies/",
        marketing_page,
        {"page_slug": "training-academies"},
        name="marketing_training_academies",
    ),
    path(
        "teacher-communities/",
        marketing_page,
        {"page_slug": "teacher-communities"},
        name="marketing_teacher_communities",
    ),
    path(
        "lesson-planning/",
        marketing_page,
        {"page_slug": "lesson-planning"},
        name="marketing_lesson_planning",
    ),
    path(
        "infrastructure-map/",
        marketing_page,
        {"page_slug": "infrastructure-map"},
        name="marketing_infrastructure_map",
    ),
    path(
        "security-matrix/",
        marketing_page,
        {"page_slug": "security-matrix"},
        name="marketing_security_matrix",
    ),
    path(
        "solutions/higher-ed/",
        marketing_page,
        {"page_slug": "solutions-higher-ed"},
        name="marketing_solutions_higher_ed",
    ),
    path(
        "solutions/k12-districts/",
        marketing_page,
        {"page_slug": "solutions-k12-districts"},
        name="marketing_solutions_k12_districts",
    ),
    path(
        "security-packet/",
        marketing_security_packet_request,
        name="marketing_security_packet_request",
    ),
    path(
        "compare/", marketing_page, {"page_slug": "compare"}, name="marketing_compare"
    ),
    path(
        "compare/power-school/",
        compare_marketing_page,
        {"competitor_slug": "power-school"},
        name="compare_power_school",
    ),
    path(
        "compare/blackbaud/",
        compare_marketing_page,
        {"competitor_slug": "blackbaud"},
        name="compare_blackbaud",
    ),
    path(
        "compare/infinite-campus/",
        compare_marketing_page,
        {"competitor_slug": "infinite-campus"},
        name="compare_infinite_campus",
    ),
    path("migrate/", migrate_marketing_page, name="migrate_marketing_page"),
    path("migrate/simulator/", migration_simulator_page, name="migration_simulator"),
    path(
        "migrate/<str:source_slug>/",
        migrate_marketing_page,
        name="migrate_marketing_page_source",
    ),
    path("migrate-from/", migrate_marketing_page, name="marketing_migrate_from"),
    path(
        "migrate-from/<str:source_slug>/",
        migrate_marketing_page,
        name="marketing_migrate_from_source",
    ),
    path(
        "roles/school-admin/",
        role_marketing_page,
        {"role_slug": "school-admin"},
        name="role_school_admin",
    ),
    path(
        "roles/teachers/",
        role_marketing_page,
        {"role_slug": "teachers"},
        name="role_teachers",
    ),
    path(
        "roles/parents/",
        role_marketing_page,
        {"role_slug": "parents"},
        name="role_parents",
    ),
    path(
        "roles/students/",
        role_marketing_page,
        {"role_slug": "students"},
        name="role_students",
    ),
    path(
        "roles/it-directors/",
        role_marketing_page,
        {"role_slug": "it-directors"},
        name="role_it_directors",
    ),
    path(
        "roles/government/",
        role_marketing_page,
        {"role_slug": "government"},
        name="role_government",
    ),
    path(
        "roles/principals/",
        role_marketing_page,
        {"role_slug": "principals"},
        name="role_principals",
    ),
    path(
        "roles/district-leaders/",
        role_marketing_page,
        {"role_slug": "district-leaders"},
        name="role_district_leaders",
    ),
    path(
        "roles/finance/",
        role_marketing_page,
        {"role_slug": "finance"},
        name="role_finance",
    ),
    path(
        "for/principals/",
        role_marketing_page,
        {"role_slug": "principals"},
        name="for_principals",
    ),
    path(
        "for/district-leaders/",
        role_marketing_page,
        {"role_slug": "district-leaders"},
        name="for_district_leaders",
    ),
    path(
        "case-studies/",
        RedirectView.as_view(url="/resources/case-studies/", permanent=True),
        name="marketing_case_studies",
    ),
    path(
        "customers/",
        RedirectView.as_view(
            pattern_name="marketing_resources_case_studies", permanent=False
        ),
        name="marketing_customers",
    ),
    path(
        "security-compliance/",
        marketing_page,
        {"page_slug": "security-compliance"},
        name="marketing_security_compliance",
    ),
    path(
        "security/",
        marketing_page,
        {"page_slug": "security"},
        name="marketing_security",
    ),
    path(
        "compliance/",
        marketing_page,
        {"page_slug": "compliance"},
        name="marketing_compliance",
    ),
    path("ferpa/", marketing_page, {"page_slug": "ferpa"}, name="marketing_ferpa"),
    path("gdpr/", marketing_page, {"page_slug": "gdpr"}, name="marketing_gdpr"),
    path("lgpd/", marketing_page, {"page_slug": "lgpd"}, name="marketing_lgpd"),
    path(
        "integrations/",
        marketing_page,
        {"page_slug": "integrations"},
        name="marketing_integrations",
    ),
    path(
        "book-demo/",
        RedirectView.as_view(pattern_name="marketing_demo", permanent=False),
        name="marketing_book_demo",
    ),
    path("book-demo/submit/", submit_demo_request, name="marketing_book_demo_submit"),
    path("demo/", marketing_page, {"page_slug": "demo"}, name="marketing_demo"),
    path(
        "company/",
        marketing_page,
        {"page_slug": "company"},
        name="marketing_company",
    ),
    path(
        "resources/case-studies/",
        marketing_page,
        {"page_slug": "resources-case-studies"},
        name="marketing_resources_case_studies",
    ),
    path(
        "resources/guides/",
        marketing_page,
        {"page_slug": "resources-guides"},
        name="marketing_resources_guides",
    ),
    path(
        "resources/help-center/",
        marketing_page,
        {"page_slug": "resources-help-center"},
        name="marketing_resources_help_center",
    ),
    path(
        "resources/help-center/search/",
        marketing_kb_search_view,
        name="marketing_kb_search",
    ),
    path(
        "resources/help-center/category/<slug:category_slug>/",
        marketing_kb_category_view,
        name="marketing_kb_category",
    ),
    path(
        "resources/help-center/article/<slug:article_slug>/",
        marketing_kb_article_view,
        name="marketing_kb_article",
    ),
    path(
        "api/v1/marketing/kb/typeahead/",
        marketing_kb_typeahead_api,
        name="marketing_kb_typeahead",
    ),
    path(
        "interactive-preview/",
        marketing_page,
        {"page_slug": "interactive-preview"},
        name="marketing_interactive_preview",
    ),
    path(
        "product-tour/",
        RedirectView.as_view(
            pattern_name="marketing_resources_product_tour", permanent=False
        ),
        name="marketing_product_tour",
    ),
    path(
        "getting-started/",
        marketing_page,
        {"page_slug": "getting-started"},
        name="marketing_getting_started",
    ),
    path("getting-started/simulator/", setup_simulator_page, name="setup_simulator"),
    path("themes/", marketing_page, {"page_slug": "themes"}, name="marketing_themes"),
    path(
        "design-studio/",
        marketing_page,
        {"page_slug": "design-studio"},
        name="marketing_design_studio",
    ),
    path(
        "uptime/", marketing_page, {"page_slug": "uptime"}, name="marketing_uptime"
    ),  # canonical marketing trust/uptime page
    path(
        "buyer-toolkit/",
        marketing_page,
        {"page_slug": "buyer-toolkit"},
        name="marketing_buyer_toolkit",
    ),
    path(
        "buyer-toolkit/download/<str:document>/",
        buyer_toolkit_download,
        name="marketing_buyer_toolkit_download",
    ),
    path(
        "funnel-dashboard/",
        marketing_funnel_dashboard,
        name="marketing_funnel_dashboard",
    ),
    path("about/", marketing_page, {"page_slug": "about"}, name="marketing_about"),
    path(
        "features/",
        marketing_page,
        {"page_slug": "features"},
        name="marketing_features",
    ),
    path(
        "blog/",
        RedirectView.as_view(url="/resources/blog/", permanent=True),
        name="marketing_blog",
    ),
    path("blog/<slug:slug>/", blog_post_detail, name="marketing_blog_detail"),
    path(
        "developers/",
        marketing_page,
        {"page_slug": "developers"},
        name="marketing_developers",
    ),
    path(
        "developers/api/",
        developer_marketing_page,
        {"section_slug": "api"},
        name="developer_api",
    ),
    path(
        "developers/webhooks/",
        developer_marketing_page,
        {"section_slug": "webhooks"},
        name="developer_webhooks",
    ),
    path(
        "developers/integrations/",
        developer_marketing_page,
        {"section_slug": "integrations"},
        name="developer_integrations",
    ),
    path(
        "developers/sdk/",
        developer_marketing_page,
        {"section_slug": "sdk"},
        name="developer_sdk_page",
    ),
    path(
        "developers/app-building/",
        developer_marketing_page,
        {"section_slug": "app-building"},
        name="developer_app_building",
    ),
    path("developer/", developer_hub, name="developer_hub"),
    path("developer/console/", developer_console, name="developer_console"),
    path(
        "developers/api-docs/",
        developer_public_api_docs,
        name="developer_public_api_docs",
    ),
    path("developer-portal/", developer_portal, name="developer_portal"),
    path("developer-portal/sdk/", developer_sdk, name="developer_sdk"),
    path("developer-portal/sandbox/", developer_sandbox, name="developer_sandbox"),
    # Marketplace developer platform (catalog API, publisher signup) before marketing /marketplace/ root.
    path(
        "marketplace/",
        include(
            (marketplace_dev_public_urlpatterns, "marketplace_dev"),
            namespace="marketplace_dev",
        ),
    ),
    path("marketplace/", marketplace_marketing_page, name="marketplace_marketing_page"),
    path(
        "marketplace/apps/",
        marketplace_marketing_page,
        {"section": "apps"},
        name="marketplace_apps",
    ),
    path(
        "marketplace/integrations/",
        marketplace_marketing_page,
        {"section": "integrations"},
        name="marketplace_integrations",
    ),
    path(
        "marketplace/templates/",
        marketplace_marketing_page,
        {"section": "templates"},
        name="marketplace_templates",
    ),
    path(
        "marketplace/blueprints/",
        marketplace_marketing_page,
        {"section": "blueprints"},
        name="marketplace_blueprints",
    ),
    path(
        "marketplace/policy-packs/",
        marketplace_marketing_page,
        {"section": "policy-packs"},
        name="marketplace_policy_packs",
    ),
    path(
        "marketplace/partners/",
        marketplace_marketing_page,
        {"section": "partners"},
        name="marketplace_partners",
    ),
    path(
        "why-switch/",
        marketing_page,
        {"page_slug": "why-switch"},
        name="marketing_why_switch",
    ),
    path(
        "school-management-system/",
        marketing_page,
        {"page_slug": "school-management-system"},
        name="marketing_school_management_system",
    ),
    path(
        "student-information-system/",
        marketing_page,
        {"page_slug": "student-information-system"},
        name="marketing_student_information_system",
    ),
    path(
        "education-erp/",
        marketing_page,
        {"page_slug": "education-erp"},
        name="marketing_education_erp",
    ),
    path(
        "school-administration-software/",
        marketing_page,
        {"page_slug": "school-administration-software"},
        name="marketing_school_administration_software",
    ),
    path(
        "10-reasons/",
        marketing_page,
        {"page_slug": "10-reasons"},
        name="marketing_10_reasons",
    ),
    path(
        "resources/",
        marketing_page,
        {"page_slug": "resources"},
        name="marketing_resources",
    ),
    path(
        "resources/product-tour/",
        marketing_page,
        {"page_slug": "resources-product-tour"},
        name="marketing_resources_product_tour",
    ),
    path(
        "resources/blog/",
        marketing_page,
        {"page_slug": "resources-blog"},
        name="marketing_resources_blog",
    ),
    path(
        "research/",
        marketing_page,
        {"page_slug": "research"},
        name="marketing_research",
    ),
    path(
        "reports/", marketing_page, {"page_slug": "reports"}, name="marketing_reports"
    ),
    path(
        "guides/",
        RedirectView.as_view(url="/resources/guides/", permanent=True),
        name="marketing_guides",
    ),
    path("events/", marketing_page, {"page_slug": "events"}, name="marketing_events"),
    path(
        "verticals/",
        marketing_page,
        {"page_slug": "verticals"},
        name="marketing_verticals",
    ),
    path(
        "trust-center/",
        marketing_page,
        {"page_slug": "trust-center"},
        name="marketing_trust_center",
    ),
    path(
        "trust-center-gdpr/",
        lambda request: redirect("/trust-center/gdpr/", permanent=False),
    ),
    path(
        "trust-center/gdpr/",
        marketing_page,
        {"page_slug": "trust-center-gdpr"},
        name="marketing_trust_gdpr",
    ),
    path(
        "trust-center/ferpa/",
        marketing_page,
        {"page_slug": "trust-center-ferpa"},
        name="marketing_trust_ferpa",
    ),
    path(
        "trust-center/retention/",
        marketing_page,
        {"page_slug": "trust-center-retention"},
        name="marketing_trust_retention",
    ),
    path(
        "trust-center/incidents/",
        marketing_page,
        {"page_slug": "trust-center-breach"},
        name="marketing_trust_incidents",
    ),
    path(
        "trust-center/coppa/",
        marketing_page,
        {"page_slug": "trust-center-coppa"},
        name="marketing_trust_coppa",
    ),
    path(
        "trust-center/accessibility/",
        marketing_page,
        {"page_slug": "trust-center-accessibility"},
        name="marketing_trust_accessibility",
    ),
    path(
        "app-marketplace/",
        marketing_page,
        {"page_slug": "app-marketplace"},
        name="marketing_app_marketplace",
    ),
    path(
        "contact/submit/",
        submit_contact_request,
        name="marketing_contact_submit",
    ),
    path(
        "security-packet/submit/",
        submit_security_packet_request,
        name="marketing_security_packet_submit",
    ),
    path(
        "contact/", marketing_page, {"page_slug": "contact"}, name="marketing_contact"
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
    path(
        "solutions/<str:topic_slug>/", topical_marketing_landing, name="marketing_topic"
    ),
    *[
        path(
            f"{prefix}/",
            regional_marketing_landing,
            {"country_code": country, "language_code": lang},
            name=url_name,
        )
        for prefix, country, lang, url_name in MARKETING_LEGACY_REGIONAL_SHORTCUTS
    ],
    path("onboard/", onboarding_wizard, name="onboard_wizard"),
    path("onboard/migrate/", onboard_migration_handoff, name="onboard_migration_handoff"),
    path("onboard/migrate/start/", onboard_migration_start, name="onboard_migration_start"),
    path("signup/", signup_school, name="signup_school"),
    # Live web-address availability + creative suggestions for the signup form.
    # These render on the PUBLIC host, so they MUST be registered here (not only
    # in config/urls.py) — otherwise the fetch 404s per-host and the live pill /
    # suggestion chips silently never fire in production.
    path("signup/slug-check/", signup_slug_check, name="signup_slug_check"),
    path("signup/slug-suggest/", signup_slug_suggest, name="signup_slug_suggest"),
    path(
        "verify-signup/resend/",
        resend_signup_verification,
        name="resend_signup_verification",
    ),
    path("verify-signup/", verify_signup, name="verify_signup"),
    path(  # rbac-allow: ci-e2e-gated-by-RMC_E2E_SIGNUP_HELPERS-env-only
        "api/e2e/signup-verification-token/",
        e2e_signup_verification_token,
        name="e2e_signup_verification_token",
    ),
    path("verify/<str:token>/", verify_student_id, name="verify_student_id"),
    path(
        "marketing/api/sandbox-validate/",
        marketing_sandbox_validate,
        name="marketing_sandbox_validate",
    ),
    path("api/tour-steps/public/", tour_steps_public_api, name="tour_steps_public_api"),
    path("api/trial/", api_trial_school, name="api_trial_school"),
    path("api/brand-import/", brand_import_api, name="api_brand_import"),
    path("robots.txt", marketing_robots_txt, name="marketing_robots_txt"),
    path("sitemap.xml", marketing_sitemap_xml, name="marketing_sitemap_xml"),
    path("lti/launch/<str:tool_id>/", lti_launch, name="lti_launch"),
    path(
        "lti/launch/<str:tool_id>/callback/",
        lti_launch_callback,
        name="lti_launch_callback",
    ),
    path(
        "lti/service/<str:tool_id>/lineitems",
        lti_ags_lineitems,
        name="lti_ags_lineitems",
    ),
    path(
        "lti/service/<str:tool_id>/lineitems/<str:lineitem_id>",
        lti_ags_lineitem_detail,
        name="lti_ags_lineitem_detail",
    ),
    path(
        "lti/service/<str:tool_id>/lineitems/<str:lineitem_id>/scores",
        lti_ags_scores,
        name="lti_ags_scores",
    ),
    path(
        "lti/service/<str:tool_id>/lineitems/<str:lineitem_id>/results",
        lti_ags_results,
        name="lti_ags_results",
    ),
    path(
        "lti/service/<str:tool_id>/memberships",
        lti_nrps_memberships,
        name="lti_nrps_memberships",
    ),
    path(
        "lti/service/<str:tool_id>/deep-linking",
        lti_deep_linking,
        name="lti_deep_linking",
    ),
    path("lti/jwks.json", jwks_json, name="lti_jwks"),
    # Phase 3: verb-canonical module aliases (same pages, new URL spine)
    path(
        "run/admissions/",
        marketing_page,
        {"page_slug": "platform-admissions"},
        name="marketing_run_admissions",
    ),
    path(
        "run/attendance/",
        marketing_page,
        {"page_slug": "platform-attendance"},
        name="marketing_run_attendance",
    ),
    path(
        "run/analytics/",
        marketing_page,
        {"page_slug": "platform-analytics"},
        name="marketing_run_analytics",
    ),
    path(
        "teach/gradebook/",
        marketing_page,
        {"page_slug": "platform-grading-report-cards"},
        name="marketing_teach_gradebook",
    ),
    path(
        "pay/fees/",
        marketing_page,
        {"page_slug": "platform-fees-payments"},
        name="marketing_pay_fees",
    ),
    path(
        "communicate/inbox/",
        marketing_page,
        {"page_slug": "platform-parent-portal"},
        name="marketing_communicate_inbox",
    ),
    path(
        "grow/marketplace/",
        marketing_page,
        {"page_slug": "platform-marketplace"},
        name="marketing_grow_marketplace",
    ),
    path(
        "grow/migration/",
        marketing_page,
        {"page_slug": "platform-migration-cloud"},
        name="marketing_grow_migration",
    ),
    path(
        "run/workflows/",
        marketing_page,
        {"page_slug": "platform-workflows"},
        name="marketing_run_workflows",
    ),
    path(
        "run/offline/",
        marketing_page,
        {"page_slug": "platform-offline-first"},
        name="marketing_run_offline",
    ),
    path(
        "teach/workspace/",
        marketing_page,
        {"page_slug": "platform-teacher-portal"},
        name="marketing_teach_workspace",
    ),
    path(
        "communicate/announcements/",
        marketing_page,
        {"page_slug": "platform-communications"},
        name="marketing_communicate_announcements",
    ),
    path(
        "pay/reconciliation/",
        marketing_page,
        {"page_slug": "platform-fees-payments"},
        name="marketing_pay_reconciliation",
    ),
    path(
        "communicate/newsletters/",
        marketing_page,
        {"page_slug": "platform-communications"},
        name="marketing_communicate_newsletters",
    ),
    # Regional landing must stay after verb-canonical paths so /run/workflows/ etc. are not captured.
    path(
        "<str:language_code>/<str:country_code>/",
        regional_marketing_landing,
        name="marketing_region",
    ),
]

# Wave 25 v4.00.92 — LTI 1.3 infrastructure (H7 + H8 + H10).
# These MUST land in public_urls (not just config.urls) because the host
# router sends `testserver` / base-domain / .well-known/ traffic here.
# We PREPEND them so the trailing 2-segment regional catch-all
# (``<language_code>/<country_code>/``) doesn't swallow them.
from apps.schools.lti_platform_jwks import (  # noqa: E402
    lti_platform_jwks_view as _lti_platform_jwks_view,
)
from apps.schools.lti_tool_admin import (  # noqa: E402
    LTIToolRegistrationCreateView as _LTIToolRegistrationCreateView,
    LTIToolRegistrationDetailView as _LTIToolRegistrationDetailView,
    LTIToolRegistrationListView as _LTIToolRegistrationListView,
)
from apps.schools.lti_tool_token import (  # noqa: E402
    lti_tool_token_endpoint as _lti_tool_token_endpoint,
)

_LTI_WAVE25_URLPATTERNS = [
    # H10 — Public JWKS endpoint (well-known + alias)
    path(
        ".well-known/jwks.json",
        _lti_platform_jwks_view,
        name="lti_platform_jwks_well_known",
    ),
    path("lti/jwks/", _lti_platform_jwks_view, name="lti_platform_jwks"),
    # H8 — LTI tool token endpoint (RFC 6749 § 4.4 client_credentials)
    path(
        "lti/auth/token/",
        _lti_tool_token_endpoint,
        name="lti_tool_token_endpoint",
    ),
    # H7 — Tool registration admin UI
    path(
        "super/lti/tools/",
        _LTIToolRegistrationListView.as_view(),
        name="lti_tool_registration_list",
    ),
    path(
        "super/lti/tools/register/",
        _LTIToolRegistrationCreateView.as_view(),
        name="lti_tool_registration_create",
    ),
    path(
        "super/lti/tools/<int:pk>/",
        _LTIToolRegistrationDetailView.as_view(),
        name="lti_tool_registration_detail",
    ),
]

# PREPEND so the Wave 25 routes resolve before the 2-segment regional
# marketing catch-all swallows them.
urlpatterns = _LTI_WAVE25_URLPATTERNS + urlpatterns

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
