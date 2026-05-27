#!/usr/bin/env python3

"""Verify unified tenant lifecycle (onboarding + offboarding) is wired end-to-end."""



from __future__ import annotations



import sys

from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))



REQUIRED = (

    ("apps/lifecycle/unified_lifecycle.py", "resolve_unified_lifecycle"),

    ("apps/lifecycle/tenant_school_resolve.py", "resolve_request_school"),
    ("apps/lifecycle/tenant_school_resolve.py", "require_tenant_lifecycle_school"),
    ("apps/siteconfig/views_school_onboarding.py", "require_tenant_lifecycle_school"),
    ("apps/platform_runtime/views_administration.py", "require_tenant_lifecycle_school"),
    ("apps/people/views_backend.py", "block_if_wind_down_commerce"),
    ("apps/schools/middleware_activation_gate.py", "/school/studio/"),
    ("apps/schools/activation_views.py", "resolve_request_school"),
    ("apps/schools/tenant_offboarding.py", "self_service_closure_cancelled"),
    ("apps/siteconfig/views_form_draft.py", "resolve_request_school"),
    ("apps/siteconfig/views_onboarding_coach.py", "can_access_tenant_lifecycle"),

    ("apps/lifecycle/tenant_school_resolve.py", "bind_lifecycle_school_session"),

    ("apps/lifecycle/tenant_school_resolve.py", "LIFECYCLE_SCHOOL_SESSION_KEY"),

    ("apps/lifecycle/launch_rail.py", "build_launch_rail_payload"),

    ("apps/lifecycle/wind_down.py", "apply_wind_down_mode"),

    ("apps/lifecycle/views_tenant_lifecycle.py", "resolve_request_school"),

    ("apps/schools/signup_views.py", "_redirect_verified_admin_to_tenant_surface"),

    ("apps/schools/signup_views.py", "bind_lifecycle_school_session"),

    ("apps/schools/tenant_offboarding.py", '"wind_down_mode": wind_down_mode'),

    ("apps/lifecycle/signals.py", "STATE_LIVE"),

    ("apps/lifecycle/views_tenant_lifecycle.py", "tenant_provisioning_status"),

    ("apps/siteconfig/views_tenant_studio_hub.py", "can_access_tenant_lifecycle"),

    ("apps/schools/views_tenant_self_offboarding.py", "resolve_request_school"),

    ("apps/lifecycle/context_processors.py", "resolve_request_school"),

    ("templates/siteconfig/tenant_provisioning_status.html", "data-rmc-provisioning-status"),

    ("templates/siteconfig/tenant_launch_fast_path.html", "data-rmc-launch-fast-path"),

    ("templates/siteconfig/tenant_studio_hub.html", "data-rmc-tenant-studio-fast-path"),

    ("templates/schools/super_tenant_360.html", "data-rmc-offboarding-checklist"),

    ("static/js/rmc-tenant-provisioning-status.js", "data-rmc-provisioning-poll"),

    ("config/tenant_urls.py", "tenant_provisioning_status"),

    ("config/tenant_urls.py", "tenant_launch_fast_path"),

    ("apps/schools/signup_views.py", "CREATION_PATH_SELF_SERVE"),

    ("apps/schools/signup_views.py", "api_trial_school"),

    ("apps/lifecycle/views_rapid_create.py", "CREATION_PATH_OPERATOR"),

    ("apps/lifecycle/views_rapid_create.py", "redirect_after_operator_school_create"),

    ("apps/lifecycle/wind_down_guards.py", "block_if_wind_down_commerce"),

    ("apps/finance/views_invoicing.py", "block_if_wind_down_commerce"),
    ("apps/finance/views_payments.py", "block_if_wind_down_commerce"),
    ("apps/finance/views_offline_bursar_queue.py", "block_if_wind_down_commerce"),
    ("apps/finance/views_permission_to_pay.py", "block_if_wind_down_commerce"),

    ("apps/people/views_backend.py", "block_if_wind_down_commerce"),
    ("scripts/generate_portal_tenant_sweep_routes.py", "/school/studio/provisioning/"),
    ("scripts/generate_portal_tenant_sweep_routes.py", "/school/studio/fast-path/"),
    ("apps/lifecycle/enrollment_workflow_matrix.py", "build_lifecycle_workflow_hub_payload"),
    ("apps/lifecycle/views_tenant_lifecycle.py", "tenant_lifecycle_command_center"),
    ("templates/siteconfig/tenant_lifecycle_command_center.html", "data-shell-surface=\"tenant-lifecycle-command-center\""),
    ("config/tenant_urls.py", "school/studio/lifecycle/"),
    ("apps/lifecycle/views_tenant_lifecycle.py", "onboarding_playbook_api_url"),
    (
        "templates/siteconfig/tenant_lifecycle_command_center.html",
        "workflow_playbook_assistant.html",
    ),
    (
        "templates/siteconfig/tenant_lifecycle_command_center.html",
        "section-lifecycle-playbook",
    ),

)





def _import_smoke() -> list[str]:

    failures: list[str] = []

    try:
        import os

        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()

    except Exception as exc:  # noqa: BLE001

        return [f"django.setup failed: {exc}"]

    try:

        from apps.lifecycle.tenant_school_resolve import resolve_request_school
        from django.urls import reverse

        reverse("tenant_provisioning_status", urlconf="config.tenant_urls")

        reverse(

            "siteconfig:onboarding_step",

            kwargs={"step_key": "academic_year"},

            urlconf="config.tenant_urls",

        )

        resolve_request_school  # noqa: B018

    except Exception as exc:  # noqa: BLE001

        failures.append(f"import_smoke: {exc}")

    return failures





def main() -> int:

    failures: list[str] = []

    for rel, needle in REQUIRED:

        path = ROOT / rel

        if not path.is_file():

            failures.append(f"missing file: {rel}")

            continue

        text = path.read_text(encoding="utf-8", errors="replace")

        if needle not in text:

            failures.append(f"{rel}: missing `{needle}`")



    failures.extend(_import_smoke())



    if failures:

        print("TENANT_LIFECYCLE_UNIFIED_FAIL")

        for msg in failures:

            print(f"  - {msg}")

        return 1



    print("TENANT_LIFECYCLE_UNIFIED_PASS")

    print(f"  checks: {len(REQUIRED)} + import_smoke")

    return 0





if __name__ == "__main__":

    sys.exit(main())

