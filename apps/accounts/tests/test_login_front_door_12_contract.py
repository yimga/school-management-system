"""Binding regression contract for the approved 12-part Local Front Door."""
from pathlib import Path
import json
from unittest.mock import patch

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.accounts.views_passkey import passkey_login_options
from apps.siteconfig.views_cockpit_health import _build_login_front_door_health
from apps.communication.forms_announcements import AnnouncementCreateForm
from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires

_BASE_DIR = Path(settings.BASE_DIR)
LOGIN_TPL = _BASE_DIR / "templates/auth/login.html"
LOGIN_CANVAS = _BASE_DIR / "templates/auth/partials/login_immersive_canvas.html"


class LoginFrontDoorTwelveContractTests(SimpleTestCase):
    def test_anonymous_passkey_routes_are_reversible(self):
        self.assertEqual(reverse("accounts:passkey_login_options"), "/authentication/login/passkey/options/")
        self.assertEqual(reverse("accounts:passkey_login_verify"), "/authentication/login/passkey/verify/")

    @patch("apps.accounts.views_passkey._webauthn_available", return_value=False)
    def test_passkey_options_degrades_without_optional_dependency(self, _available):
        request = RequestFactory().get("/authentication/login/passkey/options/")
        request.session = {}
        response = passkey_login_options(request)
        self.assertEqual(response.status_code, 503)

    @patch("apps.accounts.views_passkey._webauthn_available", return_value=True)
    def test_passkey_options_builds_discoverable_credential_request(self, _available):
        request = RequestFactory().get(
            "/authentication/login/passkey/options/",
            HTTP_HOST="localhost",
        )
        request.session = {}
        response = passkey_login_options(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("webauthn_login_challenge", request.session)
        payload = json.loads(response.content)
        self.assertEqual(payload["allowCredentials"], [])
        self.assertEqual(payload["userVerification"], "preferred")

    def test_production_surface_exposes_all_twelve_contract_markers(self):
        base = Path(settings.BASE_DIR)
        login = (base / "templates/auth/login.html").read_text(encoding="utf-8")
        canvas = (base / "templates/auth/partials/login_immersive_canvas.html").read_text(encoding="utf-8")
        js = (base / "static/js/rmc-auth-login-immersive.js").read_text(encoding="utf-8")
        cockpit = (base / "apps/siteconfig/forms_cockpit.py").read_text(encoding="utf-8")
        announcements = (base / "apps/communication/models.py").read_text(encoding="utf-8")
        offline = (base / "static/js/rmc-offline-auth-vault.js").read_text(encoding="utf-8")
        css = (base / "static/css/auth-login-canvas.css").read_text(encoding="utf-8")
        for marker in (
            "data-rmc-passkey-login",
            "data-rmc-returning-user",
            "data-rmc-returning-continue",
            "data-rmc-role-methods",
            "data-rmc-recovery-problem",
            "data-rmc-front-door-contract",
            "data-rmc-verified-host",
            "data-rmc-assistant-ask",
            "Verified school",
            "Why am I seeing this school?",
            "WCAG 2.2",
            "data-rmc-access-assistant",
        ):
            self.assertIn(marker, login)
        # Nine of those twelve markers are attributes that must be ON the
        # emitted elements -- the JS in rmc-auth-login-immersive.js finds the
        # front door by querying for them, and an attribute that exists only in
        # the file is found by nothing. The remaining three ("Verified school",
        # "Why am I seeing this school?", "WCAG 2.2") are inside {% trans %}
        # tags, which a parse cannot see and this template cannot render
        # standalone, so those stay reads.
        assert_markup(
            self,
            LOGIN_TPL,
            "data-rmc-passkey-login",
            "data-rmc-returning-user",
            "data-rmc-returning-continue",
            "data-rmc-role-methods",
            "data-rmc-recovery-problem",
            "data-rmc-front-door-contract",
            "data-rmc-verified-host",
            "data-rmc-assistant-ask",
            "data-rmc-access-assistant",
        )
        self.assertNotIn("QR badge", login)
        self.assertIn("applyRoleSurface", js)
        self.assertIn("has-returning", js)
        self.assertIn("data-rmc-i18n-continue-as", login)
        self.assertIn("data-rmc-local-state", canvas)
        self.assertIn("data-rmc-sponsored-region", canvas)
        self.assertIn("navigator.credentials.get", js)
        self.assertIn("localStorage.setItem(roleMemoryKey", js)
        self.assertIn("lic_sponsored_lines", cockpit)
        self.assertIn("lic_local_first_enabled", cockpit)
        for marker in ("scheduled_at", "expiry_date", "PENDING_APPROVAL", "AnnouncementAuditLog"):
            self.assertIn(marker, announcements)
        self.assertIn("AES-GCM", offline)
        self.assertIn("PBKDF2", offline)
        self.assertIn("scrollbar-gutter: stable", css)
        self.assertIn("data-rmc-auth-high-contrast", css)
        self.assertIn("data-rmc-auth-reduce-motion", css)
        self.assertIn("min-height: 44px", css)
        self.assertIn(".rmc-auth-immersive.has-returning [data-rmc-passkey-standalone]", css)
        self.assertIn("rmc-auth-immersive--front-door", login)
        self.assertIn(".rmc-auth-immersive--front-door", css)
        self.assertIn("data-rmc-auth-contrast", login)
        self.assertIn("data-rmc-auth-motion", login)
        self.assertNotIn(
            ".rmc-auth-immersive__dash,\n  .rmc-auth-immersive__moments { display: none; }",
            css,
        )

    def test_all_twelve_health_checks_use_real_shipped_markers(self):
        rows, score = _build_login_front_door_health()
        self.assertEqual(len(rows), 12)
        self.assertEqual(score, 100)
        self.assertTrue(all(row["status"] == "ready" for row in rows))
        self.assertTrue(all(row["action_url"].startswith("/") for row in rows))
        self.assertEqual(
            rows[3]["action_url"], reverse("portal:device_registrations_index")
        )
        self.assertEqual(
            rows[5]["action_url"], reverse("communication:announcement_create")
        )

    def test_tenant_publisher_exposes_start_and_expiry_controls(self):
        form = AnnouncementCreateForm()
        self.assertIn("scheduled_at", form.fields)
        self.assertEqual(form.fields["scheduled_at"].widget.input_type, "datetime-local")
        self.assertIn("expiry_date", form.fields)

    def test_offline_enrollment_and_unlock_are_both_wired(self):
        base = Path(settings.BASE_DIR)
        portal = (base / "templates/portal_base.html").read_text(encoding="utf-8")
        login = (base / "templates/auth/login.html").read_text(encoding="utf-8")
        canvas = (base / "templates/auth/partials/login_immersive_canvas.html").read_text(encoding="utf-8")
        enrollment = (base / "static/js/rmc-offline-auth-enrollment.js").read_text(encoding="utf-8")
        unlock = (base / "static/js/rmc-offline-login-unlock.js").read_text(encoding="utf-8")
        # Both .js names are {% static %} ARGUMENTS -- never emitted text, and
        # neither shell renders standalone -- so those two stay reads. What a
        # parse settles, on auth/login.html itself, is that the front door still
        # mounts the immersive canvas, and that the canvas still emits the
        # local-mode entry point the unlock flow is opened from. Comment either
        # out and every string here survives while offline unlock is unreachable.
        assert_wires(self, LOGIN_TPL, "auth/partials/login_immersive_canvas.html")
        assert_markup(self, LOGIN_CANVAS, "data-rmc-local-mode-open")
        self.assertIn("rmc-offline-auth-enrollment.js", portal)
        self.assertIn("rmc-offline-login-unlock.js", login)
        self.assertIn("data-rmc-local-mode-open", canvas)
        self.assertIn("sealCapability", enrollment)
        self.assertIn("openCapability", unlock)
        self.assertIn("expires <= Date.now()", unlock)
        self.assertIn("capability.school_host !== window.location.host", unlock)
