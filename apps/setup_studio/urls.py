"""Unified Wizard Framework URL routes.

Namespace: ``setup_studio``. Mounted from:
* ``config/urls.py`` (or top-level urls) at ``/setup-studio/wizards/`` for operator
* tenant subdomain urls at ``/school/studio/wizards/`` for tenant

URL names follow the pattern:
* ``setup_studio:operator_wizard_index``      → GET /super/wizards/
* ``setup_studio:operator_wizard``            → /super/wizards/<wizard_key>/
* ``setup_studio:operator_wizard_step``       → /super/wizards/<wizard_key>/<step_key>/
* ``setup_studio:operator_wizard_reset``      → POST /super/wizards/<wizard_key>/reset/
* ``setup_studio:tenant_wizard_index``        → GET /school/studio/wizards/
* ``setup_studio:tenant_wizard``              → /school/studio/wizards/<wizard_key>/
* ``setup_studio:tenant_wizard_step``         → /school/studio/wizards/<wizard_key>/<step_key>/
* ``setup_studio:tenant_wizard_reset``        → POST /school/studio/wizards/<wizard_key>/reset/
* ``setup_studio:wizard_ai_recommend``        → POST /api/wizards/ai/recommend/
"""

from django.urls import path

from apps.setup_studio.wizard_views import (
    OperatorWizardIndexView,
    OperatorWizardView,
    TenantWizardIndexView,
    TenantWizardView,
    WizardAIRecommendView,
    WizardStepDraftSyncView,
    WizardStateResetView,
)
from apps.setup_studio.views_activation_dashboard import (
    BulkPromoteCockpitPresetAPIView,
    WizardActivationDashboardView,
    WizardSearchAPIView,
)
from apps.setup_studio.views_wizard_cache_telemetry import wizard_cache_telemetry
from apps.setup_studio.views_zero_friction import (
    api_blockers,
    api_recommended_setup,
    api_zero_friction_payload,
)

app_name = "setup_studio"

# Step key pattern: lowercase letters, digits, underscores
_STEP_PATTERN = "<slug:step_key>"
_WIZARD_PATTERN = "<slug:wizard_key>"


urlpatterns = [
    # Operator surface
    path("super/wizards/", OperatorWizardIndexView.as_view(), name="operator_wizard_index"),
    path(f"super/wizards/{_WIZARD_PATTERN}/", OperatorWizardView.as_view(), name="operator_wizard"),
    path(f"super/wizards/{_WIZARD_PATTERN}/{_STEP_PATTERN}/", OperatorWizardView.as_view(), name="operator_wizard_step"),
    path(f"super/wizards/{_WIZARD_PATTERN}/reset/", WizardStateResetView.as_view(), name="operator_wizard_reset"),

    # Tenant surface
    path("school/studio/wizards/", TenantWizardIndexView.as_view(), name="tenant_wizard_index"),
    path(f"school/studio/wizards/{_WIZARD_PATTERN}/", TenantWizardView.as_view(), name="tenant_wizard"),
    path(f"school/studio/wizards/{_WIZARD_PATTERN}/{_STEP_PATTERN}/", TenantWizardView.as_view(), name="tenant_wizard_step"),
    path(f"school/studio/wizards/{_WIZARD_PATTERN}/reset/", WizardStateResetView.as_view(), name="tenant_wizard_reset"),

    # AJAX
    path("api/wizards/ai/recommend/", WizardAIRecommendView.as_view(), name="wizard_ai_recommend"),
    path(
        f"api/wizards/{_WIZARD_PATTERN}/{_STEP_PATTERN}/draft/",
        WizardStepDraftSyncView.as_view(),
        name="wizard_step_draft_sync",
    ),

    # v4.00.8: 10x improvements
    # Activation dashboard (staff-only)
    path("super/wizards/activation-dashboard/", WizardActivationDashboardView.as_view(), name="wizard_activation_dashboard"),
    # Search API (authenticated)
    path("api/wizards/search/", WizardSearchAPIView.as_view(), name="wizard_search_api"),
    # Bulk-promote cockpit preset (staff-only)
    path("api/wizards/cockpit-preset/", BulkPromoteCockpitPresetAPIView.as_view(), name="wizard_cockpit_preset_apply"),
    path(  # rbac-allow: intentionally-public-browser-telemetry-beacon-enum-only-no-pii-no-db-read
        "api/wizards/telemetry/cache-event/",
        wizard_cache_telemetry,
        name="wizard_cache_telemetry",
    ),
    path("api/setup-studio/blockers/", api_blockers, name="zero_friction_blockers"),
    path("api/setup-studio/payload/", api_zero_friction_payload, name="zero_friction_payload"),
    path("api/setup-studio/recommended/", api_recommended_setup, name="zero_friction_recommended"),
]
