"""Public signup local-first country adapter bootstrap (v4.02.24 regression)."""

import json

from django.test import RequestFactory, SimpleTestCase

from apps.schools.signup_views import _signup_localization_json
from apps.siteconfig.country_localization_service import resolve_country_pack
from apps.siteconfig.views_country_localization import country_localization_pack


class SignupCountryLocalizationBootTests(SimpleTestCase):
    databases = {"default"}

    def test_cn_localization_api_returns_localized_pack(self):
        request = RequestFactory().get("/api/v1/localization/CN/")
        response = country_localization_pack(request, "CN")
        data = json.loads(response.content)
        self.assertEqual(data["country_code"], "CN")
        self.assertEqual(data["calendar_systems"][0]["code"], "cn-2-semester")
        codes = {st["code"] for st in data["school_types"]}
        self.assertIn("youeryuan", codes)
        self.assertIn("xiaoxue", codes)

    def test_signup_localization_bootstrap_json_embeds_pack_and_url(self):
        request = RequestFactory().get("/signup/?country_code=CN")
        pack = resolve_country_pack("CN")
        payload = json.loads(_signup_localization_json(request, "CN", pack))
        self.assertEqual(payload["country_code"], "CN")
        self.assertIn("localization_country", payload["urls"])
        self.assertTrue(payload["urls"]["localization_country"])
        self.assertEqual(payload["pack"]["calendar_systems"][0]["code"], "cn-2-semester")
        self.assertIn("prefetch_countries", payload)
        self.assertIn("CN", payload["prefetch_countries"])
        self.assertIn("migration", payload)
        self.assertEqual(payload["migration"]["country_code"], "CN")

    def test_base_template_wires_public_signup_platform_surface(self):
        base_html = (self.base_path / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("request.resolver_match.url_name == 'signup_school'", base_html)
        self.assertIn("partials/rmc_platform_surface_page_data.html", base_html)

    @property
    def base_path(self):
        from pathlib import Path

        return Path(__file__).resolve().parents[3]
