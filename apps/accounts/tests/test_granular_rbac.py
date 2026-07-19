"""Behavioural tests for the additive granular-RBAC gate (2026-07-05).

Proves the property the whole program rests on: converting a surface to
``@require_permission(...)`` PRESERVES-or-WIDENS access, never narrows it — a bursar/HR
user granted a granular code reaches a surface a coarse ``@tenant_admin_required`` denied,
while the admin tier still passes and an unrelated role is still refused.

The logic tests are ``SimpleTestCase`` (no DB) using a fake user; one ``TestCase`` proves the
end-to-end AccessRole grant path with a real seeded Permission.
"""

from django.core.exceptions import PermissionDenied
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.accounts.decorators import require_permission, user_has_permission
from apps.accounts.effective_access import permission_access


class _FakeUser:
    def __init__(self, *, authed=True, superuser=False, role="", codes=()):
        self.is_authenticated = authed
        self.is_superuser = superuser
        self.role = role
        self._codes = set(codes)
        self.pk = 1

    def has_feature_permission(self, code, *, school=None):
        return code in self._codes


class ResolverAdditiveTest(SimpleTestCase):
    """user_has_permission is a UNION: code OR admin-tier OR role OR superuser."""

    def test_superuser_always_passes(self):
        u = _FakeUser(superuser=True)
        self.assertTrue(user_has_permission(u, None, ("finance.manage",)))

    def test_bursar_with_code_reaches_finance(self):
        # role=BURSAR is NOT admin-like, but the finance.manage grant admits them —
        # exactly the surface a bare @tenant_admin_required used to deny.
        u = _FakeUser(role="BURSAR", codes=("finance.manage",))
        self.assertTrue(
            user_has_permission(u, None, ("finance.view", "finance.manage"))
        )

    def test_hr_with_payroll_code_reaches_payroll(self):
        u = _FakeUser(role="CUSTOM_HR", codes=("payroll.manage",))
        self.assertTrue(user_has_permission(u, None, ("payroll.view", "payroll.manage")))

    def test_admin_tier_still_passes_without_code(self):
        # ADMIN is admin-like -> allow_admin path admits even with no granular code.
        u = _FakeUser(role="ADMIN", codes=())
        self.assertTrue(user_has_permission(u, None, ("finance.view",)))

    def test_unrelated_role_denied(self):
        u = _FakeUser(role="TEACHER", codes=())
        self.assertFalse(user_has_permission(u, None, ("finance.view", "finance.manage")))

    def test_unauthenticated_denied(self):
        u = _FakeUser(authed=False)
        self.assertFalse(user_has_permission(u, None, ("finance.view",)))

    def test_allow_admin_false_requires_code(self):
        u = _FakeUser(role="ADMIN", codes=())
        self.assertFalse(
            user_has_permission(u, None, ("finance.manage",), allow_admin=False)
        )

    def test_allow_roles_additive(self):
        u = _FakeUser(role="REGISTRAR", codes=())
        self.assertTrue(
            user_has_permission(
                u, None, ("grades.manage",), allow_admin=False, allow_roles=("REGISTRAR",)
            )
        )

    def test_facade_delegates(self):
        u = _FakeUser(role="BURSAR", codes=("finance.view",))
        self.assertTrue(permission_access(u, None, ("finance.view", "finance.manage")))
        self.assertFalse(permission_access(_FakeUser(role="TEACHER"), None, ("finance.view",)))


class DecoratorDenialSemanticsTest(SimpleTestCase):
    """Unauth -> login bounce; authed-deny -> PermissionDenied (branded 403), never a bounce."""

    def setUp(self):
        self.rf = RequestFactory()

        @require_permission("finance.view", "finance.manage")
        def view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        self.view = view

    def _req(self, user):
        req = self.rf.get("/finance/")
        req.user = user
        req.school = None
        return req

    def test_authenticated_allowed(self):
        resp = self.view(self._req(_FakeUser(role="BURSAR", codes=("finance.manage",))))
        self.assertEqual(resp.status_code, 200)

    def test_authenticated_denied_raises_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            self.view(self._req(_FakeUser(role="TEACHER", codes=())))

    def test_unauthenticated_redirects_to_login(self):
        resp = self.view(self._req(_FakeUser(authed=False)))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url.lower())


class TemplateTagTest(SimpleTestCase):
    """can_access_permission drives per-section hide/show in config surfaces."""

    def _render(self, user):
        req = RequestFactory().get("/school/configuration/")
        req.user = user
        req.school = None
        tpl = Template(
            "{% load accounts_extras %}"
            "{% can_access_permission 'finance.view' 'finance.manage' as ok %}"
            "{% if ok %}SHOW{% else %}HIDE{% endif %}"
        )
        return tpl.render(Context({"request": req}))

    def test_grantee_sees_section(self):
        self.assertEqual(self._render(_FakeUser(role="BURSAR", codes=("finance.view",))), "SHOW")

    def test_non_grantee_hidden(self):
        self.assertEqual(self._render(_FakeUser(role="TEACHER", codes=())), "HIDE")

    def test_admin_sees_section(self):
        self.assertEqual(self._render(_FakeUser(role="ADMIN", codes=())), "SHOW")


class EndToEndGrantTest(TestCase):
    """A real AccessRole grant of a seeded code unlocks the surface (DB-backed)."""

    def test_custom_role_grant_reaches_surface(self):
        from django.contrib.auth import get_user_model
        from apps.accounts.models import AccessRole, Permission

        User = get_user_model()
        perm, _ = Permission.objects.get_or_create(
            code="payroll.manage", defaults={"name": "Payroll management", "description": "x"}
        )
        role, _ = AccessRole.objects.get_or_create(
            code="CUSTOM_HR", defaults={"name": "HR Officer", "description": "x"}
        )
        role.permissions.add(perm)
        user = User.objects.create_user(
            username="hr_officer", email="hr@example.com", password="x", role="CUSTOM_HR"
        )
        user.roles.add(role)

        self.assertTrue(user.has_feature_permission("payroll.manage"))
        # Not admin-like, no owner membership, but the granular grant admits them.
        self.assertTrue(
            user_has_permission(user, None, ("payroll.view", "payroll.manage"))
        )
        self.assertFalse(user_has_permission(user, None, ("finance.manage",)))
