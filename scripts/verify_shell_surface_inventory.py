#!/usr/bin/env python3
"""
Fail if required shell / RMC contract substrings are missing from canonical templates.

Extends the allowlist as Studio OS, CCC, control-plane, and admin surfaces converge.
**1037/1038:** Also fails if any template (outside the django-messages wrapper allowlist) uses a raw
``include "partials/shell_chrome_django_messages.html"`` — use ``*_tenant_portal``,
``*_control_plane``, or ``*_base_bootstrap`` partials.
On success, writes ``docs/generated/shell_surface_inventory_ledger.md`` (mechanical).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "docs" / "generated" / "shell_surface_inventory_ledger.md"
LEDGER_JSON = REPO / "docs" / "generated" / "shell_surface_inventory_ledger.json"

# relpath -> required substrings (all must be present)
TEMPLATE_REQUIRED_SUBSTRINGS: dict[str, tuple[str, ...]] = {
    "templates/partials/shell_rmc_registry_html_attrs.html": (
        "data-rmc-route-family=",
        "data-rmc-layout-token=",
        "data-rmc-nav-family=",
        "data-rmc-host-kind=",
        "data-rmc-main-region=",
    ),
    "templates/portal_base.html": (
        "data-rmc-shell-root",
        "rmc_shell.portal_shell_root",
        "rmc_shell.portal_default_document_title",
        "rmc_shell.tenant_portal_breadcrumb_surface",
        "partials/shell_chrome_site_preview_banner_top.html",
        "partials/shell_chrome_impersonation_session_strip.html",
        "partials/shell_chrome_breadcrumb_row_open.html",
        "partials/shell_chrome_breadcrumb_row_between_primary_and_actions.html",
        "partials/shell_chrome_breadcrumb_row_close.html",
        "partials/shell_rmc_registry_html_attrs.html",
        "partials/shell_portal_layout_wrap_open.html",
        "partials/shell_chrome_django_messages_tenant_portal.html",
        "rmc_shell.authenticated_surface",
    ),
    "templates/partials/shell_chrome_django_messages.html": (
        "data-shell-chrome=\"django-messages\"",
    ),
    "templates/partials/shell_chrome_django_messages_tenant_portal.html": (
        "shell_chrome_django_messages.html",
        "shell_chrome_messages_variant=\"tenant-portal\"",
    ),
    "templates/partials/shell_chrome_django_messages_control_plane.html": (
        "shell_chrome_django_messages.html",
        "shell_chrome_messages_variant=\"control-plane\"",
    ),
    "templates/partials/shell_chrome_marketplace_tenant_ops_strip.html": (
        "data-shell-marketplace-ops=",
        "data-shell-chrome=",
    ),
    "templates/partials/shell_chrome_backend_ops_strip.html": (
        "data-backend-ops-surface=",
        "data-shell-chrome=",
    ),
    "templates/partials/shell_chrome_backend_system_indicators.html": (
        "data-backend-system-indicators=",
        "data-shell-chrome=",
    ),
    "templates/partials/shell_chrome_backend_operational_status_load.html": (
        "data-shell-chrome=\"backend-operational-status-load\"",
        "backend-status-fragment",
        "backend_dashboard_status_fragment",
    ),
    "templates/partials/shell_chrome_breadcrumb_row_open.html": (
        "data-shell-chrome=\"breadcrumb-row\"",
        "data-shell-chrome-breadcrumb-surface=",
        "data-shell-chrome=\"breadcrumb-slot\"",
    ),
    "templates/partials/shell_chrome_breadcrumb_row_between_primary_and_actions.html": (
        "data-shell-chrome=\"breadcrumb-actions-slot\"",
    ),
    "templates/partials/shell_chrome_breadcrumb_row_close.html": (
        "Close actions + outer breadcrumb row",
    ),
    "templates/partials/backend_portal_breadcrumb_actions.html": (
        "siteconfig:console_domains_hub",
        "breadcrumb-backend-actions",
    ),
    "templates/partials/shell_chrome_backend_ops_depth_summary.html": (
        "data-shell-ops-section=\"pending-alerts-activity\"",
        "data-shell-alerts=",
        "data-shell-chrome=\"backend-ops-depth\"",
    ),
    "templates/partials/shell_chrome_backend_ops_audit_snapshot.html": (
        "data-shell-chrome=\"backend-audit-snapshot\"",
        "data-shell-ops-section=\"audit-system-counts\"",
        "data-ops-count=\"pending-invites\"",
    ),
    "templates/partials/shell_chrome_backend_stats_core_strip.html": (
        "data-shell-chrome=\"backend-stats-core-strip\"",
        "data-shell-ops-section=\"core-kpi-counts\"",
        "data-kpi-count=\"students-active\"",
    ),
    "templates/partials/shell_chrome_backend_finance_pulse_strip.html": (
        "data-shell-chrome=\"backend-finance-pulse-strip\"",
        "data-shell-ops-section=\"finance-pulse-counts\"",
        "data-kpi-count=\"finance-overdue\"",
    ),
    "templates/partials/shell_chrome_backend_planner_recommended_next_strip.html": (
        "data-shell-chrome=\"backend-planner-recommended-next\"",
        "data-shell-ops-section=\"planner-recommended-next\"",
        "backend-planner-next",
    ),
    "templates/partials/shell_chrome_contextual_info_banner.html": (
        "data-shell-chrome=\"contextual-info-banner\"",
        "data-shell-banner-level=",
    ),
    "templates/partials/shell_chrome_page_heading_actions_strip.html": (
        "data-shell-chrome=\"page-heading-actions-strip\"",
        "data-shell-chrome=\"page-heading-actions-toolbar\"",
    ),
    "templates/partials/shell_chrome_impersonation_session_strip.html": (
        "data-shell-chrome=\"impersonation-session-strip\"",
        "accounts:end_impersonation",
    ),
    "templates/partials/shell_chrome_site_preview_banner_top.html": (
        "data-shell-chrome=\"site-preview-banner-top\"",
        "siteconfig:clear_preview",
    ),
    "templates/partials/shell_portal_layout_wrap_open.html": (
        "portal_wrap_authenticated_shell",
        "data-rmc-authenticated-shell",
    ),
    "templates/partials/shell_skip_link.html": (
        "skip_href",
    ),
    "templates/base.html": (
        "partials/shell_rmc_registry_html_attrs.html",
        "data-surface=",
        "partials/shell_chrome_django_messages_base_bootstrap.html",
    ),
    "templates/partials/shell_chrome_django_messages_base_bootstrap.html": (
        "shell_chrome_django_messages.html",
        "shell_chrome_messages_variant=\"base-bootstrap\"",
        "public_host_kind",
    ),
    "templates/control_plane_skeleton.html": (
        "data-rmc-shell-root",
        "data-shell-layout=",
        "partials/shell_rmc_registry_html_attrs.html",
        "partials/shell_skip_link.html",
    ),
    "templates/control_plane_base.html": (
        "data-shell-layout=",
        "data-rmc-layout-token=",
        "rmc_shell.control_plane_product_title",
        "data-rmc-shell-title=",
        "rmc_shell.shell_sidebar_control_plane",
        "rmc_shell.control_plane_breadcrumb_surface",
        "partials/shell_chrome_breadcrumb_row_open.html",
        "partials/shell_chrome_breadcrumb_row_between_primary_and_actions.html",
        "partials/shell_chrome_breadcrumb_row_close.html",
        "data-rmc-authenticated-shell",
        "cp_layout_authenticated_shell",
        "partials/shell_chrome_django_messages_control_plane.html",
        "partials/shell_chrome_impersonation_session_strip.html",
        "authenticated_surface",
    ),
    "templates/studio_os/shell.html": (
        "data-shell-layout=",
        "data-shell-host=",
        "rmc_shell.layout_token",
        "rmc_shell.shell_data_studio_host",
        "data-rmc-nav-family=",
        "rmc_shell.studio_os_sidebar_token",
        "data-shell-sidebar=",
    ),
    "templates/studio_os/shell_control_plane.html": (
        "data-shell-layout=",
        "data-shell-host=",
        "rmc_shell.layout_token",
        "rmc_shell.shell_data_studio_host",
        "data-rmc-nav-family=",
    ),
    "templates/studio_os/partials/shell_main_content.html": (
        "data-shell-studio-region",
        "data-rmc-studio-os-embed",
    ),
    "templates/components/admin_nav_bridge.html": (
        "data-shell-nav-bridge=",
    ),
    "templates/siteconfig/tenant_runtime_configuration_hub.html": (
        "data-siteconfig-surface=",
    ),
    "templates/siteconfig/region_grading_scales_matrix.html": (
        "data-shell-surface=",
        "data-page-archetype=",
        "control_plane_base.html",
    ),
    "templates/siteconfig/region_validation_dashboard.html": (
        "data-shell-surface=",
        "data-page-archetype=",
        "control_plane_base.html",
    ),
    "templates/siteconfig/region_comparison.html": (
        "data-shell-surface=",
        "data-page-archetype=",
        "control_plane_base.html",
    ),
    "templates/siteconfig/entity_catalog_overview.html": (
        "data-shell-surface=",
        "data-page-archetype=",
        "control_plane_base.html",
    ),
    "templates/siteconfig/metadata_operator_hub.html": (
        "data-shell-surface=",
        "data-page-archetype=",
        "control_plane_base.html",
    ),
    "templates/siteconfig/metadata_dynamic_fields_operator.html": (
        "data-shell-surface=",
        "data-page-archetype=",
        "control_plane_base.html",
    ),
    "templates/siteconfig/config_mutation_audit_evidence.html": (
        "data-shell-surface=",
        "data-page-archetype=",
        "control_plane_base.html",
    ),
    "templates/siteconfig/scheduled_reports_delivery_hub.html": (
        "data-shell-surface=",
    ),
    "templates/siteconfig/term_publish_status_evidence.html": (
        "data-shell-surface=",
        "data-admin-replacement-category=",
    ),
    "templates/siteconfig/academic_years_setup_evidence.html": (
        "data-shell-surface=",
        "data-admin-replacement-category=",
    ),
    "templates/siteconfig/departments_setup_evidence.html": (
        "data-shell-surface=",
        "data-admin-replacement-category=",
    ),
    "templates/marketplace/tenant_app_catalog.html": (
        "data-shell-marketplace=",
        "shell_chrome_marketplace_tenant_ops_strip",
    ),
    "templates/accounts/backend_dashboard.html": (
        "data-shell-role-home=",
        "data-shell-role-ops=",
        "shell_chrome_backend_ops_strip",
        "shell_chrome_backend_system_indicators",
        "shell_chrome_backend_operational_status_load",
        "shell_chrome_breadcrumb_row_open.html",
        "shell_chrome_backend_ops_depth_summary",
        "shell_chrome_backend_ops_audit_snapshot",
        "shell_chrome_backend_stats_core_strip",
        "shell_chrome_backend_finance_pulse_strip",
        "shell_chrome_backend_planner_recommended_next_strip",
        "school_onboarding_card.html",
    ),
    "templates/accounts/school_onboarding_card.html": (
        "data-rmc-onboarding=",
        "data-rmc-onboarding-progress=",
        "data-rmc-onboarding-steps=",
        "data-rmc-onboarding-next-action=",
    ),
    "templates/siteconfig/bulk_letters.html": (
        "shell_chrome_page_heading_actions_strip.html",
        "page_heading_title=",
    ),
    "templates/siteconfig/user_preferences.html": (
        "shell_chrome_contextual_info_banner.html",
        "chrome_banner_title=",
    ),
    "templates/siteconfig/school_theme_settings.html": (
        "shell_chrome_contextual_info_banner.html",
        "shell_chrome_page_heading_actions_strip.html",
        "page_heading_variant=",
    ),
    "templates/schools/super_workflow_packs.html": (
        "control_plane_base.html",
        "breadcrumb_actions",
        "js-return-to-origin",
        "data-page-archetype=\"catalog\"",
    ),
    "templates/schools/super_blueprints_catalog.html": (
        "control_plane_base.html",
        "breadcrumb_actions",
        "js-return-to-origin",
        "data-page-archetype=\"catalog\"",
    ),
    "templates/backend_base.html": (
        "backend_portal_breadcrumb_actions.html",
        "block.super",
    ),
    "templates/siteconfig/partials/configuration_control_center_staging_publish.html": (
        "data-ccc-staging-strip",
        "data-ccc-staging-operator-footnote",
    ),
    "templates/admin/base_site.html": (
        "setAttribute('data-shell-layout', 'admin')",
        "setAttribute('data-rmc-route-family'",
        "data-rmc-admin-shell",
        "data-rmc-shell-root",
    ),
}

# 1037: only these templates may `include` the core django-messages partial; parents use wrappers.
DJANGO_MSG_CORE_INCLUDE = 'include "partials/shell_chrome_django_messages.html"'


# Wave F: canonical app shells must not inline Django messages loops (use wrapper partials).
SHELL_TEMPLATES_NO_INLINE_MESSAGES: tuple[str, ...] = (
    "templates/portal_base.html",
    "templates/control_plane_base.html",
    "templates/backend_base.html",
    "templates/studio_os/shell.html",
)

INLINE_MSG_FOR_LOOP = "{% for message in messages %}"


def _canonical_shell_inline_message_loop_violations() -> list[str]:
    bad: list[str] = []
    for rel in SHELL_TEMPLATES_NO_INLINE_MESSAGES:
        path = REPO / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if INLINE_MSG_FOR_LOOP in text:
            bad.append(
                f"{rel}: inline messages loop; use shell_chrome_django_messages_* partials (shared chrome policy)"
            )
    return bad


def _django_messages_direct_include_violations() -> list[str]:
    bad: list[str] = []
    allowed = {
        "templates/partials/shell_chrome_django_messages_tenant_portal.html",
        "templates/partials/shell_chrome_django_messages_control_plane.html",
        "templates/partials/shell_chrome_django_messages_base_bootstrap.html",
    }
    for path in (REPO / "templates").rglob("*.html"):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO).as_posix()
        if rel == "templates/partials/shell_chrome_django_messages.html":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if DJANGO_MSG_CORE_INCLUDE in text and rel not in allowed:
            bad.append(
                f"{rel}: use shell_chrome_django_messages_* wrapper partial, not a raw core include (1037)"
            )
    return bad


def _write_ledger(passed: bool, rows: list[dict[str, str]]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verify": "verify_shell_surface_inventory",
        "passed": passed,
        "templates_checked": len(TEMPLATE_REQUIRED_SUBSTRINGS),
        "rows": rows,
    }
    LEDGER_JSON.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Shell surface inventory (generated)",
        "",
        f"**UTC** `{payload['generated_at']}`  ",
        f"**Status** `{'PASS' if passed else 'FAIL'}`  ",
        "",
        "| Template | Substrings (required) |",
        "| --- | --- |",
    ]
    for r in rows:
        lines.append(f"| `{r['path']}` | {r['summary']} |")
    lines.append("")
    LEDGER.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    bad: list[str] = []
    rows: list[dict[str, str]] = []
    for rel, needles in sorted(TEMPLATE_REQUIRED_SUBSTRINGS.items()):
        path = REPO / rel
        if not path.is_file():
            bad.append(f"MISSING FILE {rel}")
            rows.append(
                {
                    "path": rel,
                    "summary": "FILE MISSING",
                }
            )
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        miss: list[str] = []
        for n in needles:
            if n not in text:
                bad.append(f"{rel}: missing {n!r}")
                miss.append(n)
        rows.append(
            {
                "path": rel,
                "summary": "ok" if not miss else f"missing: {', '.join(miss)}",
            }
        )
    dmv = _django_messages_direct_include_violations()
    for b in dmv:
        bad.append(b)
    for b in _canonical_shell_inline_message_loop_violations():
        bad.append(b)
    if bad:
        _write_ledger(False, rows)
        print("verify_shell_surface_inventory: FAIL", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        return 1
    _write_ledger(True, rows)
    print("verify_shell_surface_inventory: PASS (shell markers present, ledger written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
