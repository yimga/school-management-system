"""Tests for immersive login context builder."""

from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase

from apps.accounts.login_immersive_canvas import (
    build_login_immersive_render_context,
    login_canvas_defaults,
    login_canvas_pro_enabled,
    resolve_login_immersive_section,
)
from apps.accounts.login_immersive_context import build_login_immersive_context
from apps.accounts.views import login_view


class LoginImmersiveContextTests(SimpleTestCase):
    def test_build_returns_required_keys(self):
        request = RequestFactory().get("/authentication/login/")
        payload = build_login_immersive_context(request)
        for key in (
            "ticker_items",
            "carousel_slides",
            "bento_stats",
            "dash_feed",
            "moments",
            "clock_label",
            "date_label",
            "layout_preset",
            "hero_mode",
            "role_preview_labels",
        ):
            self.assertIn(key, payload)
        self.assertTrue(payload["ticker_items"])
        self.assertTrue(payload["moments"])
        self.assertGreaterEqual(len(payload["moments"]), 1)

    def test_free_tier_caps_slides_at_the_free_floor(self):
        # Free tier shows the full built-in rotation (FREE_MAX_SLIDES) but caps
        # a school's custom deck there — a larger deck needs Login Canvas Pro.
        from apps.accounts.login_immersive_canvas import FREE_MAX_SLIDES

        request = RequestFactory().get("/authentication/login/")
        request.site_settings = type(
            "S",
            (),
            {
                "cockpit_payload": {
                    "login_immersive_canvas": {
                        "pro_enabled": False,
                        "hero_banner": {
                            "slides": [
                                {"title": "One"},
                                {"title": "Two"},
                                {"title": "Three"},
                                {"title": "Four"},
                                {"title": "Five"},
                            ]
                        },
                    }
                }
            },
        )()
        section = resolve_login_immersive_section(request)
        slides = section["hero_banner"]["slides"]
        self.assertEqual(len(slides), FREE_MAX_SLIDES)
        self.assertGreaterEqual(FREE_MAX_SLIDES, 3)  # full default rotation, not 1

    def test_pro_enables_marquee_mode(self):
        request = RequestFactory().get("/authentication/login/")
        request.site_settings = type(
            "S",
            (),
            {
                "cockpit_payload": {
                    "login_immersive_canvas": {
                        "pro_enabled": True,
                        "hero_banner": {"mode": "marquee"},
                    }
                }
            },
        )()
        section = resolve_login_immersive_section(request)
        self.assertEqual(section["hero_banner"]["mode"], "marquee")

    def test_non_pro_downgrades_marquee(self):
        request = RequestFactory().get("/authentication/login/")
        request.site_settings = type(
            "S",
            (),
            {
                "cockpit_payload": {
                    "login_immersive_canvas": {
                        "pro_enabled": False,
                        "hero_banner": {"mode": "marquee"},
                    }
                }
            },
        )()
        section = resolve_login_immersive_section(request)
        self.assertEqual(section["hero_banner"]["mode"], "carousel")

    def test_defaults_factory_has_canvas_schema(self):
        defaults = login_canvas_defaults()
        self.assertIn("hero_banner", defaults)
        self.assertIn("zones", defaults)
        self.assertIn("local_first", defaults)
        self.assertTrue(defaults["local_first"]["enabled"])
        self.assertTrue(defaults["enabled"])

    def test_render_context_role_preview_labels(self):
        request = RequestFactory().get("/authentication/login/")
        ctx = build_login_immersive_render_context(request)
        labels = ctx["role_preview_labels"]
        self.assertIn("staff", labels)
        self.assertIn("default", labels)
        self.assertIn("dash_preview", ctx)
        self.assertIn("mini_cards", ctx["dash_preview"]["default"])
        self.assertTrue(ctx["local_first_enabled"])

    def test_sponsored_slots_are_separate_from_hero_and_unsafe_urls_are_dropped(self):
        request = RequestFactory().get("/authentication/login/")
        request.site_settings = type(
            "S",
            (),
            {
                "cockpit_payload": {
                    "login_immersive_canvas": {
                        "pro_enabled": True,
                        "monetization": {
                            "allow_sponsored_slot": True,
                            "sponsored_slots": [
                                {"title": "Safe local fair", "cta_url": "/events/fair/"},
                                {"title": "Unsafe", "cta_url": "javascript:alert(1)"},
                            ],
                        },
                    }
                }
            },
        )()
        ctx = build_login_immersive_render_context(request)
        self.assertEqual([slot["title"] for slot in ctx["sponsored_slots"]], ["Safe local fair"])
        self.assertFalse(any(slide.get("sponsored") for slide in ctx["carousel_slides"]))
        self.assertTrue(ctx["hide_sponsored_offline"])

    def test_has_feature_enables_pro(self):
        request = RequestFactory().get("/authentication/login/")

        class _School:
            def has_feature(self, code):
                return code == "login_canvas_pro"

        request.school = _School()
        request.site_settings = type("S", (), {"cockpit_payload": {}})()
        self.assertTrue(login_canvas_pro_enabled(request, {}))

    def test_cockpit_preview_builder(self):
        from apps.accounts.login_immersive_canvas import build_login_canvas_cockpit_preview

        request = RequestFactory().get("/authentication/login/")
        section = login_canvas_defaults()
        preview = build_login_canvas_cockpit_preview(section, request)
        self.assertEqual(preview["layout_preset"], "civic_editorial")
        self.assertGreaterEqual(preview["slide_count"], 1)

    def test_post_role_defaults_without_query_params(self):
        request = RequestFactory().get("/authentication/login/")
        request.school = None
        request.user = type("U", (), {"is_authenticated": False})()
        request.session = {}
        request.public_host_kind = None
        request.META = {
            "REMOTE_ADDR": "127.0.0.1",
            "SERVER_NAME": "testserver",
            "SERVER_PORT": "80",
        }

        with patch("apps.accounts.views.render") as mock_render:
            login_view(request)
            context = mock_render.call_args[0][2]
        self.assertEqual(context["post_role"], "staff")

    def test_tenant_login_sets_auth_landing_lite_flag(self):
        request = RequestFactory().get("/authentication/login/")
        request.school = None
        request.user = type("U", (), {"is_authenticated": False})()
        request.session = {}
        request.public_host_kind = None
        request.META = {
            "REMOTE_ADDR": "127.0.0.1",
            "SERVER_NAME": "testserver",
            "SERVER_PORT": "80",
        }

        with patch("apps.accounts.views.render") as mock_render:
            login_view(request)
            context = mock_render.call_args[0][2]
            template = mock_render.call_args[0][1]
        self.assertEqual(template, "auth/login.html")
        self.assertTrue(context.get("RMC_AUTH_LANDING_LITE"))

    def test_marquee_hero_requires_pro_entitlement(self):
        request = RequestFactory().get("/siteconfig/super/configure/cockpit/")
        pro = login_canvas_pro_enabled(request, {"pro_enabled": False})
        hero_mode = "marquee"
        self.assertTrue(hero_mode in {"marquee", "hybrid"} and not pro)

    def test_pro_toggle_entitles_marquee_in_cockpit(self):
        request = RequestFactory().get("/siteconfig/super/configure/cockpit/")
        pro = login_canvas_pro_enabled(request, {"pro_enabled": True})
        self.assertTrue(pro)

    def test_gallery_upload_rejects_missing_tenant(self):
        from apps.accounts.login_canvas_media import accept_login_canvas_gallery_image

        result = accept_login_canvas_gallery_image(None, b"")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "missing_tenant")


class LoginImmersiveTemplateContractTests(SimpleTestCase):
    def test_upgrade_modal_placeholder_exists(self):
        path = Path(settings.BASE_DIR) / "templates" / "components" / "upgrade_modal_placeholder.html"
        self.assertTrue(path.is_file())
        html = path.read_text(encoding="utf-8")
        self.assertIn("data-rmc-upgrade-placeholder", html)

    def test_change_role_button_has_valid_data_attribute(self):
        login_tpl = Path(settings.BASE_DIR) / "templates" / "auth" / "login.html"
        html = login_tpl.read_text(encoding="utf-8")
        self.assertNotIn('data-rmc-auth-back"', html)
        self.assertRegex(html, r"data-rmc-auth-back(?:\s|>)")

    def test_login_template_includes_canvas_partial(self):
        login_tpl = Path(settings.BASE_DIR) / "templates" / "auth" / "login.html"
        html = login_tpl.read_text(encoding="utf-8")
        self.assertIn("login_immersive_canvas.html", html)
        self.assertIn("data-rmc-login-layout", html)
        self.assertIn("data-rmc-local-first", html)

    def test_local_front_door_keeps_promotions_away_from_credentials(self):
        canvas_tpl = Path(settings.BASE_DIR) / "templates" / "auth" / "partials" / "login_immersive_canvas.html"
        html = canvas_tpl.read_text(encoding="utf-8")
        self.assertIn("data-rmc-sponsored-region", html)
        self.assertIn("data-rmc-offline-note", html)
        login_tpl = (Path(settings.BASE_DIR) / "templates" / "auth" / "login.html").read_text(encoding="utf-8")
        credentials = login_tpl.split('data-rmc-auth-step="creds"', 1)[1]
        self.assertNotIn("data-rmc-sponsored-slot", credentials)

    def test_every_operator_and_tenant_login_boundary_declares_local_first_policy(self):
        auth_dir = Path(settings.BASE_DIR) / "templates" / "auth"
        tenant_admin = (auth_dir / "tenant_admin_login.html").read_text(encoding="utf-8")
        operator = (auth_dir / "manager_login.html").read_text(encoding="utf-8")
        operator_admin = (auth_dir / "admin_login.html").read_text(encoding="utf-8")
        self.assertIn('data-rmc-local-first-login="tenant-admin"', tenant_admin)
        self.assertIn('data-rmc-local-first-login="operator"', operator)
        self.assertIn('data-rmc-local-first-login="operator-admin"', operator_admin)
        self.assertIn("promotion-free", operator)
        self.assertIn("promotion-free", operator_admin)

    def test_approved_v3_visual_structure_is_in_production_assets(self):
        base = Path(settings.BASE_DIR)
        login_html = (base / "templates" / "auth" / "login.html").read_text(
            encoding="utf-8"
        )
        canvas_html = (
            base / "templates" / "auth" / "partials" / "login_immersive_canvas.html"
        ).read_text(encoding="utf-8")
        css = (base / "static" / "css" / "auth-login-canvas.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("Sign in to", login_html)
        self.assertIn("rmc-auth-immersive__recommended", login_html)
        self.assertIn('grid-template-areas:', css)
        self.assertIn('"hero pulse-head"', css)
        self.assertIn('"hero pulse"', css)
        dash_start = canvas_html.index('class="rmc-auth-immersive__dash ')
        dash_end = canvas_html.index("{% endif %}", dash_start)
        sponsor = canvas_html.index("data-rmc-sponsored-region")
        self.assertGreater(sponsor, dash_start)
        self.assertGreater(dash_end, sponsor)

    def test_tenant_cockpit_exposes_local_front_door_governance(self):
        forms_source = (
            Path(settings.BASE_DIR) / "apps" / "siteconfig" / "forms_cockpit.py"
        ).read_text(encoding="utf-8")
        for field in (
            "lic_local_first_enabled",
            "lic_local_status_label",
            "lic_local_status_detail",
            "lic_hide_sponsored_offline",
            "lic_sponsored_max_visible",
        ):
            self.assertIn(field, forms_source)
