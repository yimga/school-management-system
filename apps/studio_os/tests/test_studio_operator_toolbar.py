"""Manager Studio operator toolbar — tenant switcher + mode heroes."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School
from apps.schools.tests.manager_client import bind_manager_session, _manager_session_store
from apps.studio_os.services import get_studio_mode_hero_context, get_studio_operator_toolbar


def _manager_session(client) -> SessionStore:
    """
    Session state after manager-host requests lives on MANAGER_SESSION_COOKIE_NAME
    (ManagerCookieIsolationMiddleware rewrites sessionid on the response).
    """
    cookie_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    manager_cookie = client.cookies.get(cookie_name)
    if manager_cookie:
        store = SessionStore(session_key=manager_cookie.value)
        store.load()
        return store
    return client.session


def _set_manager_session_school_id(client, school_id: str) -> None:
    bind_manager_session(client)
    store = _manager_session_store(client)
    store["school_id"] = school_id
    store.modified = True
    store.save()
    bind_manager_session(client)


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.manager_urls",
)
class StudioOperatorToolbarTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="studio_toolbar_op",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        cls.school = School.objects.create(
            name="Toolbar Test School",
            slug="toolbar-test",
            subdomain="toolbar-test",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="manager.runmycampus.com")
        self.client.login(username="studio_toolbar_op", password="x" * 8)
        bind_manager_session(self.client)

    def test_set_operator_school_sets_session(self):
        url = reverse("studio_os:set_operator_school", urlconf="config.manager_urls")
        studio = reverse("studio_os:shell", urlconf="config.manager_urls")
        resp = self.client.post(
            url,
            {"school_id": str(self.school.pk), "next": studio},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            _manager_session(self.client).get("school_id"),
            str(self.school.pk),
        )

    def test_experience_renders_mode_hero_and_toolbar(self):
        url = reverse("studio_os:experience", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-studio-operator-toolbar", body)
        self.assertIn("studio-mode-hero-shell", body)
        self.assertIn("Brand identity", body)

    def test_launch_renders_mode_hero(self):
        url = reverse("studio_os:launch", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("studio-mode-hero-shell", body)
        self.assertIn("Guided onboarding", body)

    def test_live_preview_when_session_school(self):
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.http import HttpResponse
        from django.test import RequestFactory

        _set_manager_session_school_id(self.client, str(self.school.pk))
        store = _manager_session_store(self.client)
        req = RequestFactory().get(
            "/studio/experience/",
            HTTP_HOST="manager.runmycampus.com",
        )
        req.user = self.user
        req.public_host_kind = "manager"
        req.urlconf = "config.manager_urls"
        SessionMiddleware(lambda _req: HttpResponse()).process_request(req)
        for key, value in store.items():
            req.session[key] = value
        req.session.save()
        cookie_name = getattr(
            settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid"
        )
        req.COOKIES[cookie_name] = store.session_key
        toolbar = get_studio_operator_toolbar(req, current_mode="experience")
        self.assertIsNotNone(toolbar)
        assert toolbar is not None
        self.assertIsNotNone(toolbar.get("live_preview"))
        self.assertEqual(
            toolbar["live_preview"]["school_name"],
            "Toolbar Test School",
        )

    def test_mode_hero_warns_without_tenant(self):
        request = self.client.get("/studio/experience/").wsgi_request
        request.urlconf = "config.manager_urls"
        hero = get_studio_mode_hero_context("experience", request, legacy_urls={})
        self.assertEqual(hero.get("mode_health_status"), "warn")
