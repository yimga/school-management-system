"""
Canonical screen roster for experience_control closure (Path B).

Used by apps.platform_runtime.tests.test_experience_control_closure and thin per-app
test modules. Not a runtime dependency of production code.

Each row maps one operator/product/marketing surface required by system_closure_map
experience_control.required_screens + mission roster (22 entries).
"""

from __future__ import annotations

from typing import Any

# Keys must remain stable; tests assert len(EXPERIENCE_CONTROL_SCREENS) == 22.
EXPERIENCE_CONTROL_SCREENS: list[dict[str, Any]] = [
    {
        "id": "founder_dashboard",
        "primary_user": "superoperator",
        "primary_action": "Sales pipeline / North Star review",
        "reverse_spec": ("super", "founder_dashboard"),
        "urlconf": "config.manager_urls",
        "kwargs": {},
        "risk": "needs_review",
    },
    {
        "id": "backend_dashboard",
        "primary_user": "staff (school tenant)",
        "primary_action": "Role-home primary CTA + next-action strip",
        "reverse_spec": ("accounts", "backend_dashboard"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "tenant_runtime_hub",
        "primary_user": "IT admin",
        "primary_action": "Configure tenant runtime / CCC workflows entry",
        "reverse_spec": ("siteconfig", "tenant_runtime_configuration_hub"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "teacher_dashboard",
        "primary_user": "teacher",
        "primary_action": "Teaching workspace entry",
        "reverse_spec": ("portal", "teacher_dashboard_alias"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "parent_dashboard",
        "primary_user": "parent",
        "primary_action": "Family hub / student shortcuts",
        "reverse_spec": ("portal", "parent_dashboard"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "student_360",
        "primary_user": "staff/parent",
        "primary_action": "Holistic student record",
        "reverse_spec": ("portal", "student_360_page"),
        "urlconf": "config.tenant_urls",
        "kwargs": {"student_id": 1},
        "risk": "needs_review",
    },
    {
        "id": "marketplace_catalog",
        "primary_user": "operator",
        "primary_action": "Browse/install apps",
        "reverse_spec": "tenant_app_catalog",
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "installed_apps",
        "primary_user": "operator",
        "primary_action": "Manage installed marketplace apps",
        "reverse_spec": "tenant_installed_apps",
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "marketplace_monetization_dashboard",
        "primary_user": "operator",
        "primary_action": "Monetization / revenue overview (tenant)",
        "reverse_spec": ("marketplace", "monetization_dashboard"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "needs_review",
    },
    {
        "id": "finance_dashboard",
        "primary_user": "finance staff",
        "primary_action": "Financial overview",
        "reverse_spec": ("finance", "dashboard"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "billing_surfaces",
        "primary_user": "parent/staff",
        "primary_action": "Invoices / payment flows",
        "reverse_spec": ("portal", "parent_finance"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "needs_review",
    },
    {
        "id": "teacher_attendance_export",
        "primary_user": "teacher",
        "primary_action": "Export attendance dataset",
        "reverse_spec": ("portal", "teacher_attendance_export"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "compliance_exports",
        "primary_user": "compliance staff",
        "primary_action": "Run compliance export jobs",
        "reverse_spec": ("siteconfig", "compliance_exports"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "studio_os_experience",
        "primary_user": "operator",
        "primary_action": "Studio OS landing / rail",
        "reverse_spec": ("studio_os", "experience"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "guided_configuration_workflows",
        "primary_user": "operator",
        "primary_action": "Guided configuration / automation workflows",
        "reverse_spec": ("siteconfig", "guided_configuration_workflows"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "event_console",
        "primary_user": "operator",
        "primary_action": "Inspect/replay tenant events",
        "reverse_spec": ("events", "event_console"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "tenant_lifecycle_dashboard",
        "primary_user": "platform operator",
        "primary_action": "Portfolio lifecycle actions",
        "reverse_spec": ("platform_runtime", "tenant_lifecycle_dashboard"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "governed_query_builder",
        "primary_user": "analyst",
        "primary_action": "Preview governed query / export",
        "reverse_spec": ("analytics", "governed_query_builder"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "offline_sync_queue",
        "primary_user": "teacher/operator",
        "primary_action": "Process / retry offline queue",
        "reverse_spec": ("portal", "offline_sync_queue"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "payment_readiness_setup",
        "primary_user": "finance admin",
        "primary_action": "Corridor readiness checklist",
        "reverse_spec": ("finance", "payment_readiness_setup"),
        "urlconf": "config.tenant_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "marketing_homepage",
        "primary_user": "anonymous",
        "primary_action": "Discover / book demo",
        "reverse_spec": "marketing_landing",
        "urlconf": "config.public_urls",
        "kwargs": {},
        "risk": "none",
    },
    {
        "id": "marketing_platform_page",
        "primary_user": "anonymous",
        "primary_action": "Product narrative / proof",
        "reverse_spec": "marketing_products_analytics",
        "urlconf": "config.public_urls",
        "kwargs": {},
        "risk": "none",
    },
]


def reverse_screen(row: dict[str, Any]) -> str:
    from django.urls import reverse

    spec = row["reverse_spec"]
    kw = dict(row.get("kwargs") or {})
    uc = row["urlconf"]
    if isinstance(spec, tuple):
        return reverse(f"{spec[0]}:{spec[1]}", kwargs=kw, urlconf=uc)
    return reverse(spec, kwargs=kw, urlconf=uc)
