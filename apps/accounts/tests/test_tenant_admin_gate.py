"""Wave A — the tenant-admin gate that replaces @staff_member_required.

Proves the exact production bug is fixed: a school OWNER provisioned as
``role=ADMIN`` / ``is_school_owner`` WITHOUT the ``is_staff`` bit was bounced by
``@staff_member_required`` off their own finance/reports pages (and, being
authenticated, landed on the operator-skinned login — an infinite loop). The new
``tenant_admin_required`` admits that owner, denies non-admins with a branded 403
(``PermissionDenied`` -> tenant ``handler403``), and is correctly TIGHTER than the
old gate: an ``is_staff`` teacher (whom the staff gate let in) is not tenant-admin.
"""

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.decorators import tenant_admin_required, user_is_tenant_admin
from apps.accounts.effective_access import tenant_admin_access
from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership


@tenant_admin_required
def _protected(request):
    return HttpResponse("ok")


@override_settings(ALLOWED_HOSTS=["*"])
class TenantAdminGateTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Owner School",
            slug="owner-school",
            subdomain="owner-school",
            is_active=True,
        )

    def _req(self, user):
        req = self.factory.get("/finance/")
        req.user = user
        req.school = self.school
        return req

    def test_owner_without_is_staff_is_allowed(self):
        """The exact bug: a self-service owner has role=ADMIN + is_school_owner but
        NOT is_staff, so the old @staff_member_required bounced them to login."""
        owner = User.objects.create_user(
            username="owner1",
            password="x",
            role=User.Role.ADMIN,
            is_staff=False,
            is_superuser=False,
        )
        SchoolMembership.objects.create(
            user=owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_school_owner=True,
            is_primary=True,
        )
        self.assertFalse(owner.is_staff)  # the missing bit that caused the lockout
        self.assertTrue(user_is_tenant_admin(owner, self.school))
        resp = _protected(self._req(owner))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"ok")

    def test_owner_membership_without_admin_role_is_allowed(self):
        """A pure owner (membership flag) must pass even if User.role is not admin-like
        — proves the owner flag alone grants, independent of role/settings.manage."""
        owner = User.objects.create_user(
            username="owner2", password="x", role=User.Role.TEACHER, is_staff=False
        )
        SchoolMembership.objects.create(
            user=owner,
            school=self.school,
            role=User.Role.TEACHER,
            is_school_owner=True,
            is_primary=True,
        )
        self.assertTrue(user_is_tenant_admin(owner, self.school))

    def test_admin_role_is_allowed(self):
        admin = User.objects.create_user(
            username="admin1", password="x", role=User.Role.ADMIN, is_staff=False
        )
        resp = _protected(self._req(admin))
        self.assertEqual(resp.status_code, 200)

    def test_superuser_is_allowed_god_mode(self):
        su = User.objects.create_user(
            username="su", password="x", is_superuser=True, is_staff=True
        )
        self.assertTrue(user_is_tenant_admin(su, self.school))
        resp = _protected(self._req(su))
        self.assertEqual(resp.status_code, 200)

    def test_non_admin_denied_with_permission_denied(self):
        """A random authenticated user gets PermissionDenied (-> branded 403),
        NOT a redirect to the operator-skinned login."""
        student = User.objects.create_user(
            username="stud", password="x", role=User.Role.STUDENT, is_staff=False
        )
        self.assertFalse(user_is_tenant_admin(student, self.school))
        with self.assertRaises(PermissionDenied):
            _protected(self._req(student))

    def test_is_staff_teacher_is_not_tenant_admin(self):
        """Regression guard the other way: the old is_staff gate let in an is_staff
        teacher; the tenant-admin tier correctly does NOT."""
        teacher = User.objects.create_user(
            username="t1",
            password="x",
            role=User.Role.TEACHER,
            is_staff=True,
            is_superuser=False,
        )
        self.assertFalse(user_is_tenant_admin(teacher, self.school))
        with self.assertRaises(PermissionDenied):
            _protected(self._req(teacher))

    def test_unauthenticated_redirects_to_login(self):
        resp = _protected(self._req(AnonymousUser()))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/authentication/login/", resp["Location"])

    def test_facade_matches_decorator_gate(self):
        """effective_access.tenant_admin_access is the canonical non-decorator check."""
        admin = User.objects.create_user(
            username="admin2", password="x", role=User.Role.ADMIN
        )
        self.assertTrue(tenant_admin_access(admin, self.school))
        student = User.objects.create_user(
            username="stud2", password="x", role=User.Role.STUDENT
        )
        self.assertFalse(tenant_admin_access(student, self.school))
