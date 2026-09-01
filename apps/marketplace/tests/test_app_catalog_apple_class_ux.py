from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires


ROOT = Path(__file__).resolve().parents[3]


class AppCatalogAppleClassUXTests(SimpleTestCase):
    def test_platform_and_tenant_catalogs_show_permission_scope_visuals(self):
        paths = [
            ROOT / "templates" / "marketplace" / "app_catalog.html",
            ROOT / "templates" / "marketplace" / "tenant_app_catalog.html",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                # The catalog scope is markup and the dependency graph is an
                # {% include %} -- both answerable by the engine, and a comment
                # satisfies neither. The lowercase "scope"/"sandbox" sweeps and
                # the assertNotIn below are byte questions and stay reads.
                assert_markup(self, path, "data-apple-class-app-catalog")
                assert_wires(self, path, "components/apple_class_dependency_graph.html")
                self.assertIn("data-apple-class-app-catalog", text)
                self.assertIn("apple_class_dependency_graph.html", text)
                self.assertIn("scope", text.lower())
                self.assertIn("sandbox", text.lower())
                self.assertNotIn("settlement proof complete", text.lower())
