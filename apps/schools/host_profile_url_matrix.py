# -*- coding: utf-8 -*-
"""
Canonical URL name lists for **tenant host** vs **manager host** profiles.

Used by tests (`test_tenant_host_profile_url_wiring`) and documentation so navigation,
Studio rails, and control-plane links are **wired** (reverse succeeds on the correct
urlconf) — not only staged in templates.

See: docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md (platform boundary;
Studio OS cross-host deep links in apps/studio_os/deep_links.py).
"""

from __future__ import annotations

# Resolved with Django urlconf ``config.tenant_urls`` (school subdomain / tenant plane).
TENANT_HOST_CRITICAL_VIEWS: tuple[str, ...] = (
    "accounts:login",
    "accounts:redirect",
    "accounts:backend_dashboard",
    "accounts:end_impersonation",
    "accounts:rbac",
    "studio_os:shell",
    "studio_os:experience",
    "studio_os:automation",
    "studio_os:output",
    "studio_os:control",
    "siteconfig:console_domains_hub",
    "siteconfig:guided_onboarding",
    "siteconfig:theme_colors",
    "portal:parent_dashboard",
    "portal:teacher_dashboard_alias",
    "finance:invoices",
    "service_worker_root",
    "sw_asset_manifest",
    "pwa_manifest_platform",
)

# Resolved with ``config.manager_urls`` (manager.runmycampus.com / control plane).
MANAGER_HOST_CRITICAL_VIEWS: tuple[str, ...] = (
    "accounts:login",
    "accounts:redirect",
    "super:dashboard",
    "super:schools_list",
    "super:command_center",
    "super:ai_gateway_console",
    "super:create_school_wizard",
    "super:switch_to_tenant",
    "super:operator_policy",
    "siteconfig:console_domains_hub",
    "studio_os:shell",
    "studio_os:control",
)

# Must **not** resolve on tenant urlconf (operator-only); tests use NoReverseMatch.
MANAGER_ONLY_VIEW_PREFIXES: tuple[str, ...] = ("super:",)
