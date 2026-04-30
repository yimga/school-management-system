from django.test import SimpleTestCase, override_settings
from django.urls import clear_url_caches, resolve, reverse


SAFE_STATUSES = {200, 301, 302, 303, 307, 308, 401, 403, 405}


ROUTE_GRID = {
    "login/logout": [
        ("public", "config.urls", "accounts:login"),
        ("public", "config.urls", "accounts:logout"),
        ("tenant", "config.tenant_urls", "accounts:login"),
        ("manager", "config.manager_urls", "accounts:login"),
    ],
    "dashboards": [
        ("admin", "config.urls", "admin:index"),
        ("teacher", "config.urls", "accounts:backend_dashboard"),
        ("parent", "config.urls", "portal:parent_dashboard"),
        ("manager", "config.manager_urls", "super:dashboard"),
    ],
    "marketplace": [
        ("public", "config.public_urls", "marketplace_marketing_page"),
        ("tenant", "config.tenant_urls", "tenant_app_catalog"),
        ("manager", "config.manager_urls", "super:marketplace_governance"),
    ],
    "billing": [
        ("tenant", "config.tenant_urls", "finance:dashboard"),
        ("tenant", "config.tenant_urls", "siteconfig:billing_plan_readonly"),
        ("manager", "config.manager_urls", "super:billing_dashboard"),
    ],
    "attendance": [
        ("tenant", "config.tenant_urls", "portal:student_attendance_export"),
        ("api", "config.urls", "api_v1:attendance-bulk"),
    ],
    "reports": [
        ("tenant", "config.tenant_urls", "reports:verify_report_hash"),
        ("tenant", "config.tenant_urls", "siteconfig:report_templates_catalog_evidence"),
        ("manager", "config.manager_urls", "studio_os:output"),
    ],
    "ccc/siteconfig": [
        ("tenant", "config.tenant_urls", "siteconfig:tenant_runtime_configuration_hub"),
        ("tenant", "config.tenant_urls", "siteconfig:guided_configuration_workflows"),
        ("manager", "config.manager_urls", "siteconfig:metadata_operator_hub"),
    ],
    "studio os": [
        ("tenant", "config.tenant_urls", "studio_os:experience"),
        ("tenant", "config.tenant_urls", "studio_os:automation"),
        ("manager", "config.manager_urls", "studio_os:control"),
    ],
    "api endpoints": [
        ("public", "config.urls", "health"),
        ("public", "config.urls", "api_health"),
        ("manager", "config.manager_urls", "manager_search_api"),
        ("tenant", "config.tenant_urls", "api-schema-ui"),
    ],
}


HTTP_SMOKE = [
    ("config.urls", "home"),
    ("config.urls", "offline"),
    ("config.urls", "accounts:login"),
    ("config.urls", "accounts:logout"),
    ("config.urls", "accounts:backend_dashboard"),
    ("config.tenant_urls", "studio_os:experience"),
    ("config.tenant_urls", "siteconfig:tenant_runtime_configuration_hub"),
    ("config.manager_urls", "super:dashboard"),
    ("config.manager_urls", "manager_search_api"),
]


@override_settings(
    ALLOWED_HOSTS=["testserver", "manager.runmycampus.com", "tenant.runmycampus.com"],
    SECURE_SSL_REDIRECT=False,
)
class RouteIntegrityTests(SimpleTestCase):
    def test_route_grid_reverses_under_expected_scope(self):
        failures = []
        for category, routes in ROUTE_GRID.items():
            for label, urlconf, route_name in routes:
                try:
                    reverse(route_name, urlconf=urlconf)
                except Exception as exc:  # pragma: no cover - failure message path
                    failures.append(f"{category}:{label}:{route_name}:{urlconf}: {exc}")
        self.assertEqual(failures, [])

    def test_representative_routes_resolve_to_views(self):
        for urlconf, route_name in HTTP_SMOKE:
            clear_url_caches()
            with self.settings(ROOT_URLCONF=urlconf):
                path = reverse(route_name)
                match = resolve(path, urlconf=urlconf)
                self.assertIsNotNone(match.func, f"{route_name} under {urlconf}")

    def test_error_templates_have_no_dead_end_actions(self):
        required = {
            "errors/403.html": ["accounts:redirect", "accounts:request_waiver"],
            "errors/404.html": ["accounts:redirect", "kb:kb_home"],
            "errors/500.html": ["accounts:redirect"],
            "errors/offline.html": ["Retry connection", "Home"],
        }
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        for template, needles in required.items():
            body = (root / "templates" / template).read_text(encoding="utf-8")
            for needle in needles:
                self.assertIn(needle, body, f"{template} is missing {needle}")
