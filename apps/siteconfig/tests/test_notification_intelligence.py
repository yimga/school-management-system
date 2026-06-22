"""Contract + functional tests for the notification-intelligence engine (Surface 6).

The engine composes the existing bell poller (rmc-notification-bell-poll.js),
the toast self-capture system, and the Notification REST API. It adds a live
in-place bell preview, per-item + bulk mark-read, and instant tenant-badge sync
on toast capture. Config is a SITE cascade (default-on, zero migration). Guards:

  1. cascade gate logic (default-on);
  2. the engine declares its hooks, composes the existing systems, + is CSP-safe;
  3. the config island + engine load on every authenticated shell;
  4. CSS grammar defined;
  5. the four cascade keys are write-whitelisted AND prefix-owned shadow keys;
  6. the admin settings route/view/template + registry action exist;
  7. the school defaults round-trip through set_runtime_default + the façade.
"""

from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

_ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class NotificationCascadeGateTests(SimpleTestCase):
    TPL = Template("{% if SITE.notify_intelligence == False %}false{% else %}true{% endif %}")

    def test_default_is_on(self):
        self.assertEqual(self.TPL.render(Context({})), "true")

    def test_explicit_false_is_off(self):
        site = type("S", (), {"notify_intelligence": False})()
        self.assertEqual(self.TPL.render(Context({"SITE": site})), "false")


class NotificationEngineContractTests(SimpleTestCase):
    def test_engine_declares_hooks_and_composes(self):
        js = _read("static/js/rmc-notification-intelligence.js")
        self.assertIn("data-rmc-unread-badge", js)      # composes the bell badges
        self.assertIn("data-rmc-unread-endpoint", js)   # attaches to the bell wrapper
        self.assertIn("rmc-noti-preview", js)           # live preview panel
        self.assertIn("showToast", js)                  # composes the toast system
        self.assertIn("rmc-noti-item__rd", js)          # inline mark-read control

    def test_engine_reverses_urls_not_hardcoded(self):
        # URLs come from the island; the engine must read them from config,
        # never embed an /api/ path literal.
        js = _read("static/js/rmc-notification-intelligence.js")
        self.assertIn("cfg.listUrl", js)
        self.assertIn("cfg.markAllUrl", js)
        self.assertIn("cfg.readUrlTemplate", js)
        self.assertNotIn("/api/notifications", js)

    def test_engine_is_csp_safe(self):
        js = _read("static/js/rmc-notification-intelligence.js")
        self.assertIn("createElement", js)
        self.assertIn("textContent", js)
        self.assertNotIn(".innerHTML", js)

    def test_config_island_partial(self):
        tpl = _read("templates/partials/rmc_notification_engine.html")
        self.assertIn('id="rmc-notification-config"', tpl)
        self.assertIn("rmc-notification-intelligence.js", tpl)
        self.assertIn("SITE.notify_intelligence", tpl)
        self.assertIn("api:notification-list", tpl)
        self.assertIn("api:notification-mark-all-read", tpl)
        self.assertIn("api:notification-read", tpl)

    def test_engine_loaded_on_every_authenticated_shell(self):
        for shell in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        ):
            self.assertIn("partials/rmc_notification_engine.html", _read(shell), shell)

    def test_css_grammar_defined(self):
        css = _read("static/css/rmc-class-grammar.css")
        for cls in (".rmc-noti-preview", ".rmc-noti-item", ".rmc-noti-empty"):
            self.assertIn(cls, css, cls)

    def test_settings_route_template_and_action(self):
        urls = _read("apps/siteconfig/urls.py")
        self.assertIn('name="notification_settings"', urls)
        self.assertIn(
            "notification_settings", _read("apps/siteconfig/command_bar_registry.py")
        )
        tpl = _read("templates/siteconfig/notification_settings.html")
        for name in (
            "notify_intelligence",
            "notify_bell_preview",
            "notify_inline_actions",
            "notify_toast_sync",
        ):
            self.assertIn(name, tpl, name)


class NotificationCascadeWiringTests(SimpleTestCase):
    KEYS = (
        "notify_intelligence",
        "notify_bell_preview",
        "notify_inline_actions",
        "notify_toast_sync",
    )

    def test_write_keys_whitelisted(self):
        from apps.platform_runtime.runtime_defaults_first_class import _WIZARD_RUNTIME_DEFAULT_KEYS

        for key in self.KEYS:
            self.assertIn(key, _WIZARD_RUNTIME_DEFAULT_KEYS, key)

    def test_keys_are_prefix_owned_shadow_keys(self):
        from apps.siteconfig.domain_ownership import is_runtime_payload_shadow_key

        for key in ("notify_intelligence", "notify_bell_preview"):
            self.assertTrue(is_runtime_payload_shadow_key(key), key)

    def test_can_manage_logic(self):
        from apps.siteconfig.views_notifications_engine import _can_manage_notifications

        class _U:
            def __init__(self, su, perm):
                self.is_authenticated = True
                self.is_superuser = su
                self._perm = perm

            def has_feature_permission(self, p):
                return self._perm

        self.assertTrue(_can_manage_notifications(_U(True, False)))
        self.assertTrue(_can_manage_notifications(_U(False, True)))
        self.assertFalse(_can_manage_notifications(_U(False, False)))
        self.assertFalse(_can_manage_notifications(None))


class NotificationCascadeWriteTests(TestCase):
    def _school(self, tag):
        import uuid

        from apps.schools.models import School

        return School.objects.create(
            name="Notify " + tag,
            slug=f"noti{tag}-{uuid.uuid4().hex[:10]}",
            subdomain=f"noti{tag}-{uuid.uuid4().hex[:10]}",
        )

    def test_set_persists_and_unknown_rejected(self):
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("p")
        self.assertTrue(
            set_runtime_default(school=school, field="notify_bell_preview", value=False)
        )
        self.assertFalse(
            set_runtime_default(school=school, field="notify_not_real", value=True)
        )
        school.refresh_from_db()
        self.assertIs(
            school.settings.get("runtime_defaults", {}).get("notify_bell_preview"), False
        )

    def test_override_reads_back_through_facade(self):
        from django.core.cache import cache

        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.platform_runtime.runtime_defaults_first_class import set_runtime_default

        school = self._school("r")
        set_runtime_default(school=school, field="notify_toast_sync", value=False)
        cache.clear()
        site = get_effective_site_settings(school=school)
        self.assertIs(getattr(site, "notify_toast_sync"), False)


class NotificationSettingsPostTests(TestCase):
    def test_post_writes_school_defaults(self):
        import uuid

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        from apps.accounts.models import User
        from apps.schools.models import School
        from apps.siteconfig.views_notifications_engine import notification_settings_view

        school = School.objects.create(
            name="Notify UI",
            slug=f"notiui-{uuid.uuid4().hex[:10]}",
            subdomain=f"notiui-{uuid.uuid4().hex[:10]}",
        )
        admin = User.objects.create_user(
            username=f"notia-{uuid.uuid4().hex[:8]}@t.test", password="x"
        )
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        req = RequestFactory().post("/notifications/settings/", {"notify_bell_preview": "on"})
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        setattr(req, "_messages", FallbackStorage(req))
        req.user = admin
        req.school = school

        resp = notification_settings_view(req)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        rd = (school.settings or {}).get("runtime_defaults", {})
        self.assertIs(rd.get("notify_bell_preview"), True)
        self.assertIs(rd.get("notify_intelligence"), False)  # checkbox omitted = off
        self.assertIs(rd.get("notify_toast_sync"), False)
