"""Wave C — sudo-style step-up re-authentication."""

from types import SimpleNamespace
from unittest import mock

from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.step_up import (
    STEP_UP_SESSION_KEY,
    has_recent_step_up,
    mark_step_up,
    require_step_up,
    step_up_max_age,
)


def _with_session(request):
    SessionMiddleware(lambda r: HttpResponse()).process_request(request)
    return request


@require_step_up()
def _protected(request):
    return HttpResponse("ok")


@override_settings(STEP_UP_REAUTH_MAX_AGE_SECONDS=600)
class StepUpPrimitiveTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _req(self, authenticated=True):
        r = self.factory.get("/finance/payment-setup/")
        _with_session(r)
        r.user = SimpleNamespace(is_authenticated=authenticated)
        return r

    def test_mark_then_recent(self):
        r = self._req()
        self.assertFalse(has_recent_step_up(r))
        mark_step_up(r)
        self.assertTrue(has_recent_step_up(r))
        self.assertIn(STEP_UP_SESSION_KEY, r.session)

    def test_mark_revives_pii_reauth_window(self):
        from apps.accounts.pii_masking import PII_REAUTH_SESSION_KEY

        r = self._req()
        mark_step_up(r)
        self.assertIn(PII_REAUTH_SESSION_KEY, r.session)

    def test_expired_step_up(self):
        r = self._req()
        r.session[STEP_UP_SESSION_KEY] = int(timezone.now().timestamp()) - (
            step_up_max_age() + 5
        )
        self.assertFalse(has_recent_step_up(r))

    def test_decorator_redirects_without_step_up(self):
        resp = _protected(self._req())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/authentication/step-up/", resp["Location"])
        self.assertIn("next=", resp["Location"])

    def test_decorator_allows_with_step_up(self):
        r = self._req()
        mark_step_up(r)
        self.assertEqual(_protected(r).status_code, 200)

    def test_decorator_ignores_unauthenticated(self):
        # Unauthenticated requests fall through to the auth decorator beneath.
        self.assertEqual(_protected(self._req(authenticated=False)).status_code, 200)


@override_settings(ALLOWED_HOSTS=["*"])
class StepUpChallengeViewTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User

        self.user = User.objects.create_user(
            username="cu", password="rightpass", role=User.Role.ADMIN
        )

    def test_get_renders(self):
        self.client.force_login(self.user)
        with mock.patch(
            "apps.accounts.views_step_up.render", return_value=HttpResponse("challenge")
        ):
            resp = self.client.get("/authentication/step-up/?next=/finance/")
        self.assertEqual(resp.status_code, 200)

    def test_post_correct_password_marks_and_redirects(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/authentication/step-up/", {"password": "rightpass", "next": "/finance/"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/finance/")
        self.assertIn(STEP_UP_SESSION_KEY, self.client.session)

    def test_post_wrong_password_no_step_up(self):
        self.client.force_login(self.user)
        with mock.patch(
            "apps.accounts.views_step_up.render", return_value=HttpResponse("challenge")
        ):
            resp = self.client.post(
                "/authentication/step-up/", {"password": "wrong", "next": "/finance/"}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(STEP_UP_SESSION_KEY, self.client.session)

    def test_post_open_redirect_is_neutralized(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/authentication/step-up/",
            {"password": "rightpass", "next": "https://evil.example.com/"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/")  # external next dropped
