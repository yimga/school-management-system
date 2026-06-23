"""Wave 2 — TenantLocaleMiddleware (local-first timezone + language activation).

Before this, ``School.timezone`` / ``School.default_language`` were stored but never
applied at render time. The middleware activates the tenant's timezone every request
(reset on response) and fills the tenant default language only when no stronger signal
(cookie / matched Accept-Language / user preference) already won.

All SimpleTestCase — fake request + fake school, no DB.
"""

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone, translation

_ROOT = Path(__file__).resolve().parents[3]


class _FakeSchool:
    def __init__(self, tz="", lang=""):
        self.timezone = tz
        self.default_language = lang


def _mw():
    from apps.schools.middleware import TenantLocaleMiddleware

    return TenantLocaleMiddleware(lambda r: HttpResponse())


class TimezoneActivationTests(SimpleTestCase):
    def tearDown(self):
        timezone.deactivate()

    def test_activates_tenant_timezone(self):
        req = RequestFactory().get("/")
        req.school = _FakeSchool(tz="Africa/Lagos")
        _mw().process_request(req)
        self.assertEqual(timezone.get_current_timezone_name(), "Africa/Lagos")

    def test_response_resets_timezone(self):
        mw = _mw()
        req = RequestFactory().get("/")
        req.school = _FakeSchool(tz="Africa/Lagos")
        mw.process_request(req)
        mw.process_response(req, HttpResponse())
        self.assertNotEqual(timezone.get_current_timezone_name(), "Africa/Lagos")

    def test_no_school_is_noop(self):
        req = RequestFactory().get("/")
        _mw().process_request(req)  # no request.school attribute
        self.assertEqual(timezone.get_current_timezone_name(), settings.TIME_ZONE)

    def test_bad_timezone_does_not_raise(self):
        req = RequestFactory().get("/")
        req.school = _FakeSchool(tz="Not/AReal_Zone")
        _mw().process_request(req)  # must not raise
        self.assertEqual(timezone.get_current_timezone_name(), settings.TIME_ZONE)


class LanguageActivationTests(SimpleTestCase):
    def _supported_nondefault(self):
        default = (getattr(settings, "LANGUAGE_CODE", "en") or "en").split("-")[0]
        for code, _ in getattr(settings, "LANGUAGES", []):
            if code.split("-")[0] != default:
                return code
        return None

    def test_fills_tenant_default_when_resolved_is_platform_default(self):
        lang = self._supported_nondefault()
        self.assertIsNotNone(lang)
        req = RequestFactory().get("/")
        req.school = _FakeSchool(lang=lang)
        with translation.override(settings.LANGUAGE_CODE):
            _mw().process_request(req)
            self.assertEqual(translation.get_language(), lang)

    def test_cookie_signal_is_respected(self):
        lang = self._supported_nondefault()
        req = RequestFactory().get("/")
        req.COOKIES[getattr(settings, "LANGUAGE_COOKIE_NAME", "django_language")] = "en"
        req.school = _FakeSchool(lang=lang)
        with translation.override(settings.LANGUAGE_CODE):
            _mw().process_request(req)
            # Cookie present → tenant default NOT applied; stays platform default.
            self.assertEqual(
                translation.get_language().split("-")[0],
                settings.LANGUAGE_CODE.split("-")[0],
            )

    def test_stronger_resolved_language_not_overridden(self):
        lang = self._supported_nondefault()
        req = RequestFactory().get("/")
        req.school = _FakeSchool(lang="fr")
        with translation.override(lang):  # simulate Accept-Language already won
            _mw().process_request(req)
            self.assertEqual(translation.get_language(), lang)

    def test_blank_tenant_language_is_noop(self):
        req = RequestFactory().get("/")
        req.school = _FakeSchool(lang="")
        with translation.override(settings.LANGUAGE_CODE):
            _mw().process_request(req)
            self.assertEqual(translation.get_language(), settings.LANGUAGE_CODE)


class MiddlewareRegistrationTests(SimpleTestCase):
    def test_registered_in_middleware_stacks(self):
        text = (_ROOT / "config/settings.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            text.count("apps.schools.middleware.TenantLocaleMiddleware"), 2
        )
