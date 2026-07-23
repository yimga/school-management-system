"""role_feedback_center must not 500 on the control-plane (manager) host.

The page extends the tenant portal shell (portal_base.html), which reverses
``{% url 'portal:...' %}`` — a namespace absent on the manager host. Rendering it
there was a NoReverseMatch 500. On the control-plane host the view now sends the
operator to their own feedback console instead. This fires against the pre-fix
code (which 500'd).
"""

from __future__ import annotations

from importlib import import_module

from django.conf import settings as django_settings
from django.test import RequestFactory, TestCase
from django.contrib.auth import get_user_model

from apps.feedback.views import role_feedback_center

User = get_user_model()


def _fresh_session():
    return import_module(django_settings.SESSION_ENGINE).SessionStore()


class RoleFeedbackControlPlaneTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="fbcp", email="fbcp@example.com", password="pass12345678"
        )

    def _req(self, path, host_kind):
        request = self.factory.get(path)
        request.user = self.user
        request.public_host_kind = host_kind
        request.school = None
        request.session = _fresh_session()
        return request

    def test_manager_host_redirects_instead_of_500(self):
        for role in ("teacher", "parent", "student"):
            request = self._req(f"/{role}/feedback/", "manager")
            resp = role_feedback_center(request, role)
            self.assertEqual(
                resp.status_code,
                302,
                f"{role} feedback must redirect (not render the tenant shell) on manager",
            )

    def test_tenant_host_still_renders(self):
        # On a tenant host the guard is skipped — the page renders as before.
        request = self._req("/teacher/feedback/", "tenant")
        resp = role_feedback_center(request, "teacher")
        self.assertEqual(resp.status_code, 200)
