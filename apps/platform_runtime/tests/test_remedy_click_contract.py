from django.test import SimpleTestCase

from apps.platform_runtime.remedy_click_contract import click_reduction, direct_remedy_violations
from apps.setup_studio.services import STEP_DEFINITIONS, _registry_field_cta


class RemedyClickContractTests(SimpleTestCase):
    def test_every_registry_finding_opens_exact_editor(self):
        for key in (
            "country", "subdivision", "timezone", "currency", "locale", "calendar",
            "institution_type", "grading_scale", "education_system",
        ):
            with self.subTest(key=key):
                url = _registry_field_cta(key)["url"]
                self.assertIn(f"repair_field={key}", url)
                self.assertTrue(url.endswith("#repair-editor"))

    def test_setup_actions_do_not_fall_back_to_undirected_hubs(self):
        actions = []
        for definition in STEP_DEFINITIONS:
            query = definition.get("link_query") or ""
            fragment = definition.get("link_fragment") or ""
            pseudo_url = {
                "accounts:backend_dashboard": "/authentication/backend/",
                "school_configuration_center_canonical": "/school/configuration/",
            }.get(definition["link_name"], f"/{definition['link_name'].replace(':', '/')}/")
            if query:
                pseudo_url += f"?{query}"
            if fragment:
                pseudo_url += f"#{fragment}"
            actions.append({"key": definition["key"], "cta_url": pseudo_url})
        self.assertEqual(direct_remedy_violations(actions), [])

    def test_direct_editor_exceeds_fifty_percent_click_reduction_goal(self):
        self.assertGreaterEqual(click_reduction(before_clicks=3, after_clicks=1), 50)

    def test_broad_hub_without_focus_is_rejected(self):
        violations = direct_remedy_violations([{"key": "profile", "cta_url": "/school/configuration/"}])
        self.assertEqual(violations[0]["reason"], "broad hub destination")
