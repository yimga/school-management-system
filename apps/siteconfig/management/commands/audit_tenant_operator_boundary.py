"""Audit tenant/operator navigation isolation.

This command is intentionally narrow: it checks the paths that previously let a
tenant-host request or tenant-rendered surface point at the manager/operator
plane. It is safe to run locally and in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, resolve, reverse

from config.admin import platform_admin_site, tenant_admin_site


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

        tenant_urls = text("config/tenant_urls.py")
        manager_urls = text("config/manager_urls.py")
        root_urls = text("config/urls.py")
        admin_config = text("config/admin.py")
        deep_links = text("apps/studio_os/deep_links.py")

        record(
            "tenant_urlconf_uses_tenant_admin_site",
            "tenant_admin_site.urls" in tenant_urls
            and "platform_admin_site.urls" not in tenant_urls,
            "tenant host /admin/ must bind tenant_admin_site only",
        )
        record(
            "manager_urlconf_uses_platform_admin_site",
            "platform_admin_site.urls" in manager_urls
            and "tenant_admin_site.urls" not in manager_urls,
            "manager host /admin/ must bind platform_admin_site only",
        )
        record(
            "root_admin_dispatch_unresolved_tenant_fails_closed",
            "Tenant admin requires a resolved tenant." in root_urls
            and 'target_urlconf = "config.tenant_urls" if school is not None else "config.manager_urls"'
            in root_urls,
            "root /admin/ dispatcher must not fall into platform admin for unresolved tenant-like hosts",
        )
        record(
            "admin_registries_are_separate",
            "tenant_admin_site = TenantAdminSite" in admin_config
            and "platform_admin_site = PlatformAdminSite" in admin_config
            and "No shared registry" in admin_config,
            "tenant and platform admin must use separate AdminSite registries",
        )
        record(
            "studio_deep_links_fail_closed_for_operator_namespaces",
            "operator_name = viewname.startswith((\"super:\", \"admin:\"))" in deep_links
            and "if operator_name and not operator_allowed:" in deep_links
            and "return \"\"" in deep_links,
            "Studio deep links must not manufacture /super/ or /admin/ URLs unless explicitly manager-scoped",
        )
        record(
            "tenant_has_distinct_configuration_backend_routes",
            'path("configuration/", school_configuration_center' in tenant_urls
            and 'path("school/settings/", school_configuration_center' in tenant_urls
            and 'path("school/configuration/", school_configuration_center' in tenant_urls
            and '"siteconfig/"' in tenant_urls
            and 'include(("apps.siteconfig.urls", "siteconfig"), namespace="siteconfig")'
            in tenant_urls,
            "tenant config backend must be reachable on tenant host through configuration/school/siteconfig surfaces",
        )

        try:
            tenant_admin_match = resolve("/admin/", urlconf="config.tenant_urls")
            tenant_admin_ok = getattr(tenant_admin_match.func, "admin_site", None) is tenant_admin_site
        except Exception:
            tenant_admin_ok = False
        record(
            "runtime_tenant_admin_resolves_tenant_site",
            tenant_admin_ok,
            "runtime resolver for tenant /admin/ must use tenant_admin_site",
        )

        try:
            manager_admin_match = resolve("/admin/", urlconf="config.manager_urls")
            manager_admin_ok = getattr(manager_admin_match.func, "admin_site", None) is platform_admin_site
        except Exception:
            manager_admin_ok = False
        record(
            "runtime_manager_admin_resolves_platform_site",
            manager_admin_ok,
            "runtime resolver for manager /admin/ must use platform_admin_site",
        )

        try:
            reverse("super:dashboard", urlconf="config.tenant_urls")
            tenant_can_reverse_super = True
        except NoReverseMatch:
            tenant_can_reverse_super = False
        record(
            "runtime_tenant_urlconf_has_no_super_namespace",
            not tenant_can_reverse_super,
            "tenant URLconf must not expose super: namespace",
        )

        try:
            reverse("portal:parent_dashboard", urlconf="config.manager_urls")
            manager_can_reverse_portal = True
        except NoReverseMatch:
            manager_can_reverse_portal = False
        record(
            "runtime_manager_urlconf_has_no_tenant_portal_namespace",
            not manager_can_reverse_portal,
            "manager URLconf must not expose tenant portal namespace",
        )

        closed_gaps = [
            "Tenant-host /super/ no longer redirects to manager host.",
            "Tenant Configuration Control Center suppresses operator links.",
            "Tenant command palette suppresses /super/ and /admin/ actions.",
            "Shared Studio/siteconfig templates guard operator URL tags by manager scope.",
            "Root /admin/ dispatcher fails closed for unresolved tenant-like hosts.",
            "Studio deep links fail closed for super:/admin: unless explicitly manager-scoped.",
            "Tenant and platform admin sites resolve through distinct URLconfs and registries.",
        ]
        watch_gaps = [
            {
                "area": "PostgreSQL/RLS data-plane proof",
                "status": "UNVERIFIED_BY_THIS_AUDIT",
                "reason": "This command proves route/link/admin separation, not row-level SQL policy behavior.",
            },
            {
                "area": "Object storage and media prefixes",
                "status": "UNVERIFIED_BY_THIS_AUDIT",
                "reason": "Needs storage-provider fixture or integration audit to prove tenant prefix isolation.",
            },
            {
                "area": "Async jobs and cache tenant context",
                "status": "UNVERIFIED_BY_THIS_AUDIT",
                "reason": "Needs task queue/cache key audit to prove tenant context propagation outside requests.",
            },
            {
                "area": "All API serializers/querysets",
                "status": "UNVERIFIED_BY_THIS_AUDIT",
                "reason": "Needs queryset/RLS scanner plus endpoint smoke matrix by tenant membership.",
            },
        ]
        reference_patterns = [
            {
                "vendor": "AWS",
                "url": "https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-api-access-authorization/introduction.html",
                "pattern": "Separate authentication from tenant isolation; enforce tenant-aware authorization at API enforcement points.",
            },
            {
                "vendor": "Salesforce",
                "url": "https://architect.salesforce.com/docs/architect/fundamentals/guide/platform-multitenant-architecture.html",
                "pattern": "Use tenant/org identifiers and metadata-driven runtime separation so each tenant customizes independently.",
            },
            {
                "vendor": "Shopify",
                "url": "https://shopify.dev/docs/api/usage/access-scopes",
                "pattern": "Use explicit access scopes and separate admin/storefront/customer access classes.",
            },
        ]

        payload = {
            "status": "PASS" if not findings else "FAIL",
            "checks": checks,
            "findings": findings,
            "closed_gaps": closed_gaps,
            "watch_gaps": watch_gaps,
            "reference_patterns": reference_patterns,
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
            gap_payload = {
                "status": payload["status"],
                "rule": "Tenant frontend, tenant configuration backend, and operator control plane are distinct surfaces. Tenant scope must never resolve into operator scope.",
                "closed_gaps": closed_gaps,
                "watch_gaps": watch_gaps,
                "reference_patterns": reference_patterns,
                "source_files": [
                    "config/tenant_urls.py",
                    "config/manager_urls.py",
                    "config/urls.py",
                    "config/admin.py",
                    "apps/schools/middleware.py",
                    "apps/studio_os/deep_links.py",
                    "apps/siteconfig/control_outcome_center.py",
                    "apps/siteconfig/command_bar_registry.py",
                ],
            }
            (out_dir / "tenant_operator_separation_gap_analysis.json").write_text(
                json.dumps(gap_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            gap_md = [
                "# Tenant Operator Separation Gap Analysis",
                "",
                f"Status: **{gap_payload['status']}**",
                "",
                "Rule: tenant day-to-day frontend, tenant configuration backend, and operator control plane are separate surfaces. Tenant scope must never resolve into operator scope.",
                "",
                "## Closed Gaps",
            ]
            gap_md.extend(f"- {item}" for item in closed_gaps)
            gap_md.extend(["", "## Watch Gaps Requiring Separate Proof"])
            gap_md.extend(
                f"- {item['area']}: {item['status']} - {item['reason']}"
                for item in watch_gaps
            )
            gap_md.extend(
                [
                    "",
                    "## World-Class Operating Pattern",
                    "- Resolve tenant context first, then authorize every resource with that tenant context.",
                    "- Keep tenant admin/configuration separate from platform/operator administration.",
                    "- Use least-privilege scopes for app/platform access and make expanded access explicit.",
                    "- Treat routes, command palettes, deep links, background jobs, storage prefixes, and API querysets as security boundaries.",
                    "",
                    "## Reference Patterns",
                ]
            )
            gap_md.extend(
                f"- {item['vendor']}: {item['pattern']} ({item['url']})"
                for item in reference_patterns
            )
            (out_dir / "tenant_operator_separation_gap_analysis.md").write_text(
                "\n".join(gap_md) + "\n",
                encoding="utf-8",
            )

        if findings:
            raise SystemExit("\n".join(findings))
        self.stdout.write(self.style.SUCCESS("tenant/operator boundary audit passed"))
