"""Audit tenant/operator navigation isolation.

This command is intentionally narrow: it checks the paths that previously let a
tenant-host request or tenant-rendered surface point at the manager/operator
plane. It is safe to run locally and in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand


REPO = Path(__file__).resolve().parents[4]


class Command(BaseCommand):
    help = "Audit tenant/operator boundary links and redirect guards."

    def add_arguments(self, parser):
        parser.add_argument(
            "--write",
            action="store_true",
            help="Write docs/generated/tenant_operator_boundary_audit.*",
        )

    def handle(self, *args, **options):
        findings = []
        checks = []

        def record(name: str, passed: bool, detail: str) -> None:
            checks.append({"name": name, "passed": passed, "detail": detail})
            if not passed:
                findings.append(f"{name}: {detail}")

        def text(rel: str) -> str:
            return (REPO / rel).read_text(encoding="utf-8")

        middleware = text("apps/schools/middleware.py")
        marker = 'if kind is None and path.startswith("/super/"):'
        block = middleware[middleware.find(marker) : middleware.find("# /t/<slug>/")]
        record(
            "tenant_super_path_fails_closed",
            marker in block
            and "_redirect_to_manager_host" not in block
            and "_response_for_unknown_tenant_host" in block,
            "tenant-host /super/ must resolve to tenant backend or unknown-tenant handling, never manager redirect",
        )

        outcome = text("apps/siteconfig/control_outcome_center.py")
        record(
            "outcome_center_operator_routes_manager_only",
            "_is_operator_route(url_name) and not _is_manager_scope(request)" in outcome
            and "Tenant requests must not manufacture operator URLs" in outcome,
            "control outcome resolver must not use manager URLconf for tenant operator routes",
        )

        command_bar = text("apps/siteconfig/command_bar_registry.py")
        record(
            "command_palette_filters_operator_actions_by_request",
            "_is_operator_action(action)" in command_bar
            and "get_actions_for_user(request.user, school, request=request)" in command_bar,
            "command palette must hide /super/ and /admin/ actions outside manager scope",
        )

        console = text("apps/siteconfig/views_console_domains.py")
        record(
            "configuration_center_hides_operator_links_on_tenant",
            "_is_operator_url_name" in console
            and "_build_platform_config_context" in console
            and 'context["platform_operator_hub_url"] = None' in console,
            "tenant Configuration Control Center must not receive platform/operator links",
        )

        template_failures = []
        for rel in [
            "templates/siteconfig/config_mutation_audit_evidence.html",
            "templates/siteconfig/entity_catalog_overview.html",
            "templates/siteconfig/feature_control_panel_content.html",
            "templates/siteconfig/metadata_dynamic_fields_operator.html",
            "templates/siteconfig/metadata_operator_hub.html",
            "templates/siteconfig/operator_control_plane_page.html",
            "templates/studio_os/shell.html",
            "templates/studio_os/shell_control_plane.html",
            "templates/studio_os/partials/shell_main_content.html",
            "templates/studio_os/partials/subpages/control_impact.html",
            "templates/partials/cockpit/_ai_copilot_rail.html",
            "templates/partials/cockpit/_globe_nexus_interstitial.html",
            "templates/partials/cockpit/_live_world_map.html",
            "templates/partials/control_plane_unified_header.html",
        ]:
            lines = text(rel).splitlines()
            for idx, line in enumerate(lines):
                if "{% url 'super:" not in line and '{% url "super:' not in line:
                    continue
                window = "\n".join(lines[max(0, idx - 4) : idx + 1])
                if (
                    "request.public_host_kind == 'manager'" not in window
                    or "not request.school" not in window
                ):
                    template_failures.append(f"{rel}:{idx + 1}")
        record(
            "tenant_shared_templates_guard_super_urls",
            not template_failures,
            "unguarded super URL tags: " + ", ".join(template_failures[:20])
            if template_failures
            else "all audited shared super URL tags are manager-scoped",
        )

        payload = {
            "status": "PASS" if not findings else "FAIL",
            "checks": checks,
            "findings": findings,
        }
        if options["write"]:
            out_dir = REPO / "docs" / "generated"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "tenant_operator_boundary_audit.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            md = ["# Tenant Operator Boundary Audit", "", f"Status: **{payload['status']}**", ""]
            for check in checks:
                state = "PASS" if check["passed"] else "FAIL"
                md.append(f"- {state}: {check['name']} - {check['detail']}")
            (out_dir / "tenant_operator_boundary_audit.md").write_text(
                "\n".join(md) + "\n",
                encoding="utf-8",
            )

        if findings:
            raise SystemExit("\n".join(findings))
        self.stdout.write(self.style.SUCCESS("tenant/operator boundary audit passed"))
