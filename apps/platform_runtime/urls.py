from django.urls import path

from apps.platform_runtime.views_operational_center import (
    implementation_command_center,
    implementation_missing_data_blockers_json,
    pilot_defect_dashboard,
    pilot_evidence_dashboard,
    support_playbook_center,
)
from apps.platform_runtime.views_tenant_lifecycle import tenant_lifecycle_dashboard
from apps.platform_runtime.views_workflow_flight_deck import (
    flight_deck_json_view as workflow_progress_flight_deck_json_view,
    flight_deck_view as workflow_progress_flight_deck_view,
)
from apps.platform_runtime.views_workflow_progress import (
    active_runs_view as workflow_progress_active_runs_view,
    apply_fix_view as workflow_progress_apply_fix_view,
    badge_view as workflow_progress_badge_view,
    cancel_view as workflow_progress_cancel_view,
    e2e_demo_start_view as workflow_progress_e2e_demo_start_view,
    run_detail_view as workflow_progress_run_detail_view,
    stream_view as workflow_progress_stream_view,
)
from apps.platform_runtime.views_workflow_autopilot import (
    autopilot_policy_view as workflow_progress_autopilot_policy_view,
    enable_autopilot_view as workflow_progress_enable_autopilot_view,
)
from apps.platform_runtime.views_workflow_trust import (
    tenant_trusted_active_view as workflow_progress_tenant_trusted_active_view,
    tenant_trusted_stream_view as workflow_progress_tenant_trusted_stream_view,
)
from apps.platform_runtime.views_newsletter import (
    newsletter_confirm_view,
    newsletter_subscribe_view,
    newsletter_unsubscribe_view,
)
from apps.platform_runtime.views_platform_health import (
    platform_health_badge,
    platform_health_center,
    platform_health_recheck,
)
from apps.platform_runtime.views_health_autopilot import health_autopilot_console
from apps.platform_runtime.views_local_ai import (
    browser_inference_config_view,
    local_voice_synthesize_view,
    local_voice_transcribe_view,
)

urlpatterns = [
    path(  # rbac-allow: authenticated-tenant-local-browser-ai-config
        "local-ai/browser-config/",
        browser_inference_config_view,
        name="browser_inference_config",
    ),
    path(  # rbac-allow: authenticated-tenant-explicit-consent-local-stt
        "local-ai/voice/transcribe/",
        local_voice_transcribe_view,
        name="local_voice_transcribe",
    ),
    path(  # rbac-allow: authenticated-tenant-explicit-consent-local-tts
        "local-ai/voice/synthesize/",
        local_voice_synthesize_view,
        name="local_voice_synthesize",
    ),
    path(
        "lifecycle/",
        tenant_lifecycle_dashboard,
        name="tenant_lifecycle_dashboard",
    ),
    path(
        "implementation/",
        implementation_command_center,
        name="implementation_command_center",
    ),
    path(
        "implementation/blockers.json",
        implementation_missing_data_blockers_json,
        name="implementation_missing_data_blockers_json",
    ),
    path(
        "support-playbooks/",
        support_playbook_center,
        name="support_playbook_center",
    ),
    path(
        "pilot-evidence/",
        pilot_evidence_dashboard,
        name="pilot_evidence_dashboard",
    ),
    path(
        "pilot-defects/",
        pilot_defect_dashboard,
        name="pilot_defect_dashboard",
    ),
    # Workflow Progress Bus — platform-wide (v4.00.96).
    path(  # rbac-allow: auth-gated-via-login_required_api-401-on-anonymous
        "workflow-progress/active/",
        workflow_progress_active_runs_view,
        name="workflow_progress_active_runs",
    ),
    path(  # rbac-allow: auth-gated-via-login_required_api-401-on-anonymous
        "workflow-progress/badge/",
        workflow_progress_badge_view,
        name="workflow_progress_badge",
    ),
    path(  # rbac-allow: auth-gated-via-login_required_sse-401-on-anonymous
        "workflow-progress/stream/",
        workflow_progress_stream_view,
        name="workflow_progress_stream",
    ),
    path(  # rbac-allow: auth-gated-via-login_required_api-401-on-anonymous
        "workflow-progress/detail/<int:run_id>/",
        workflow_progress_run_detail_view,
        name="workflow_progress_run_detail",
    ),
    path(  # rbac-allow: auth-gated-via-login_required_api-401-on-anonymous
        "workflow-progress/cancel/<int:run_id>/",
        workflow_progress_cancel_view,
        name="workflow_progress_cancel",
    ),
    path(  # rbac-allow: auth-gated-via-login_required_api-401-on-anonymous
        "workflow-progress/apply-fix/<int:run_id>/",
        workflow_progress_apply_fix_view,
        name="workflow_progress_apply_fix",
    ),
    path(  # rbac-allow: auth-gated-via-login_required_api-401-on-anonymous
        "workflow-progress/e2e-demo/start/",
        workflow_progress_e2e_demo_start_view,
        name="workflow_progress_e2e_demo_start",
    ),
    path(  # rbac-allow: super-staff-workflow-flight-deck-mission-control
        "workflow-progress/flight-deck/",
        workflow_progress_flight_deck_view,
        name="workflow_progress_flight_deck",
    ),
    path(  # rbac-allow: auth-gated-via-login_required_api-staff-flight-deck-json
        "workflow-progress/flight-deck.json",
        workflow_progress_flight_deck_json_view,
        name="workflow_progress_flight_deck_json",
    ),
    path(  # rbac-allow: auth-gated-tenant-safe-workflow-active-json
        "workflow-progress/tenant-trusted/active/",
        workflow_progress_tenant_trusted_active_view,
        name="workflow_progress_tenant_trusted_active",
    ),
    path(  # rbac-allow: auth-gated-tenant-safe-workflow-sse-stream
        "workflow-progress/tenant-trusted/stream/",
        workflow_progress_tenant_trusted_stream_view,
        name="workflow_progress_tenant_trusted_stream",
    ),
    path(  # rbac-allow: auth-gated-via-login_required_api-staff-autopilot-policy
        "workflow-progress/autopilot/policy/",
        workflow_progress_autopilot_policy_view,
        name="workflow_progress_autopilot_policy",
    ),
    path(  # rbac-allow: auth-gated-via-login_required_api-staff-enable-autopilot
        "workflow-progress/autopilot/enable/",
        workflow_progress_enable_autopilot_view,
        name="workflow_progress_enable_autopilot",
    ),
    # Platform Health — registries → assist-dock connective tissue (2026-06-03).
    path(  # rbac-allow: staff-gated-via-staff_member_required-redirect-on-non-staff
        "platform-health/",
        platform_health_center,
        name="platform_health_center",
    ),
    path(  # rbac-allow: staff-gated-via-login_required_api-plus-is_staff-403
        "platform-health/badge/",
        platform_health_badge,
        name="platform_health_badge",
    ),
    path(  # rbac-allow: staff-gated-via-login_required_api-plus-is_staff-403
        "platform-health/recheck/",
        platform_health_recheck,
        name="platform_health_recheck",
    ),
    # Platform Intelligence & Self-Healing — consolidated AI + health-autopilot console.
    path(  # rbac-allow: staff-gated-via-staff_member_required-redirect-on-non-staff
        "self-healing/",
        health_autopilot_console,
        name="health_autopilot_console",
    ),
    # Newsletter subscription (v4.00.98 Phase 3).
    path(  # rbac-allow: intentionally-public-marketing-newsletter-double-opt-in-signup
        "newsletter/subscribe/",
        newsletter_subscribe_view,
        name="newsletter_subscribe",
    ),
    path(  # rbac-allow: intentionally-public-newsletter-doi-confirm-unguessable-url-token
        "newsletter/confirm/<str:token>/",
        newsletter_confirm_view,
        name="newsletter_confirm",
    ),
    path(  # rbac-allow: intentionally-public-newsletter-unsubscribe-unguessable-url-token
        "newsletter/unsubscribe/<str:token>/",
        newsletter_unsubscribe_view,
        name="newsletter_unsubscribe",
    ),
]
