"""Wave F: tenant lexicon settings UI tests."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.test import RequestFactory, TestCase, override_settings

from apps.portal.views_lexicon import (
    _collect_post,
    _current_overrides,
    _save_overrides,
    lexicon_settings,
)
from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig

User = get_user_model()


def _make_school(plan, region, settings=None):
    slug = f"lex-ui-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=slug, slug=slug, subdomain=slug, is_active=True,
        plan=plan, default_region=region, settings=settings or {},
    )


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class LexiconSettingsTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="UI", slug="ui-plan", included_features=["core"], is_active=True)
        cls.region = RegionConfig.objects.create(code="UI", name="UIland", timezone="UTC", default_currency="USD")

    def setUp(self):
        self.factory = RequestFactory()

    def _admin(self):
        user = User.objects.create_user(username=f"adm-{uuid.uuid4().hex[:6]}", password="pw")
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        return user

    def _student_role_user(self):
        user = User.objects.create_user(username=f"stu-{uuid.uuid4().hex[:6]}", password="pw")
        return user  # no admin role

    def _build_request(self, method, user, school, post=None):
        if method == "POST":
            req = self.factory.post("/portal/configure/lexicon/", data=post or {})
        else:
            req = self.factory.get("/portal/configure/lexicon/")
        req.user = user
        req.school = school
        # Bypass Django messages middleware in unit tests by attaching a stub.
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, "session", {})
        req._messages = FallbackStorage(req)
        # Stub resolver_match so portal_base.html template (used by render()) can
        # reach request.resolver_match.url_name without going through URL resolution.
        from django.urls.resolvers import ResolverMatch
        req.resolver_match = ResolverMatch(
            func=lambda r: None, args=(), kwargs={},
            url_name="portal_lexicon_settings",
        )
        return req

    def test_get_renders_for_admin(self):
        school = _make_school(self.plan, self.region)
        req = self._build_request("GET", self._admin(), school)
        resp = lexicon_settings(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("Terminology", body)
        self.assertIn("data-rmc-lexicon-row=\"student\"", body)
        self.assertIn("data-rmc-lexicon-row=\"class\"", body)

    def test_get_forbidden_for_non_admin(self):
        school = _make_school(self.plan, self.region)
        req = self._build_request("GET", self._student_role_user(), school)
        resp = lexicon_settings(req)
        self.assertEqual(resp.status_code, 403)

    def test_get_400_when_no_tenant(self):
        req = self.factory.get("/portal/configure/lexicon/")
        req.user = self._admin()
        # No request.school
        # Stub resolver_match (same reason as _build_request).
        from django.urls.resolvers import ResolverMatch
        req.resolver_match = ResolverMatch(
            func=lambda r: None, args=(), kwargs={},
            url_name="portal_lexicon_settings",
        )
        resp = lexicon_settings(req)
        self.assertEqual(resp.status_code, 400)

    def test_post_saves_overrides(self):
        school = _make_school(self.plan, self.region)
        admin = self._admin()
        req = self._build_request("POST", admin, school, post={
            "term[student][singular]": "Scholar",
            "term[student][plural]": "Scholars",
            "term[class][singular]": "Cohort",
        })
        resp = lexicon_settings(req)
        self.assertEqual(resp.status_code, 302)  # redirect after save
        school.refresh_from_db()
        terms = school.settings.get("terminology") or {}
        self.assertEqual(terms["student"], {"singular": "Scholar", "plural": "Scholars"})
        self.assertEqual(terms["class"], {"singular": "Cohort"})

    def test_post_omits_keys_equal_to_default(self):
        school = _make_school(self.plan, self.region)
        admin = self._admin()
        req = self._build_request("POST", admin, school, post={
            "term[student][singular]": "Student",   # equals default → drop
            "term[student][plural]": "Students",    # equals default → drop
            "term[teacher][singular]": "Sensei",
        })
        lexicon_settings(req)
        school.refresh_from_db()
        terms = school.settings.get("terminology") or {}
        self.assertNotIn("student", terms)
        self.assertEqual(terms["teacher"], {"singular": "Sensei"})

    def test_collect_post_ignores_unknown_keys(self):
        post = QueryDict("", mutable=True)
        post["term[student][singular]"] = "Scholar"
        post["term[bogus_key][singular]"] = "Garbage"
        overrides, warnings = _collect_post(post)
        self.assertIn("student", overrides)
        self.assertNotIn("bogus_key", overrides)
        self.assertTrue(any("bogus_key" in w for w in warnings))

    def test_save_overrides_strips_terminology_when_empty(self):
        school = _make_school(self.plan, self.region, settings={"terminology": {"student": "Scholar"}})
        _save_overrides(school, {})
        school.refresh_from_db()
        self.assertNotIn("terminology", school.settings or {})

    def test_current_overrides_normalises_legacy_string_form(self):
        school = _make_school(self.plan, self.region, settings={"terminology": {"student": "Scholar"}})
        overrides = _current_overrides(school)
        self.assertEqual(overrides, {"student": {"singular": "Scholar"}})
