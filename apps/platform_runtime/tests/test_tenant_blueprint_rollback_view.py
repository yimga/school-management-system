"""A tenant admin can roll back a blueprint they applied — without an operator.

Rollback used to be operator-only (``blueprint_rollback_view`` is
``@require_control_plane_access``); the tenant blueprint page showed a static
"Tracked after approved apply" string and no affordance. These lock the new
tenant-host self-rollback view: it is gated on tenant-admin eligibility (not
control-plane), hard-scoped to the requesting school (a foreign installation is a
404, never a cross-tenant undo), and still confirmation-gated.
"""
from __future__ import annotations

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.http import Http404, HttpResponseForbidden
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.models import BlueprintInstallation
from apps.platform_runtime.views_administration import tenant_blueprint_rollback
from apps.schools.models import School

BLUEPRINT = "private-primary-school"


def _post(school, user, installation_id):
    request = RequestFactory().post(
        f"/school/setup/blueprints/installations/{installation_id}/rollback/",
        {"confirm": "yes"},
    )
    request.school = school
    request.user = user
    request.session = SessionStore()
    request._messages = FallbackStorage(request)
    return request


@override_settings(ROOT_URLCONF="config.tenant_urls")
class TenantBlueprintRollbackViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Rollback View School",
            slug="rollback-view-school",
            subdomain="rollback-view-school",
            is_active=True,
        )
        self.admin = User.objects.create_superuser(
            username="rollback_admin", email="a@b.co", password="x"
        )

    def _apply(self, school):
        apply_blueprint(BLUEPRINT, school=school, actor=None, confirmed=True, platform_operator=True)
        return (
            BlueprintInstallation.objects.filter(school=school).order_by("-id").first()
        )

    def test_route_resolves_on_tenant_host(self):
        url = reverse("tenant_blueprint_rollback", kwargs={"installation_id": 1})
        self.assertTrue(url.endswith("/rollback/"))

    def test_tenant_admin_can_roll_back_own_installation(self):
        installation = self._apply(self.school)
        self.assertEqual(installation.status, BlueprintInstallation.Status.APPLIED)
        resp = tenant_blueprint_rollback(
            _post(self.school, self.admin, installation.id), installation.id
        )
        self.assertEqual(resp.status_code, 302)
        installation.refresh_from_db()
        self.assertEqual(installation.status, BlueprintInstallation.Status.ROLLED_BACK)

    def test_foreign_school_installation_is_a_404(self):
        other = School.objects.create(
            name="Other", slug="other-rbk", subdomain="other-rbk", is_active=True
        )
        foreign = self._apply(other)
        with self.assertRaises(Http404):
            tenant_blueprint_rollback(
                _post(self.school, self.admin, foreign.id), foreign.id
            )
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, BlueprintInstallation.Status.APPLIED)

    def test_ineligible_user_is_forbidden(self):
        installation = self._apply(self.school)
        nobody = User.objects.create_user(
            username="nobody_rbk", password="x", role=User.Role.STUDENT
        )
        resp = tenant_blueprint_rollback(
            _post(self.school, nobody, installation.id), installation.id
        )
        self.assertIsInstance(resp, HttpResponseForbidden)
        installation.refresh_from_db()
        self.assertEqual(installation.status, BlueprintInstallation.Status.APPLIED)
