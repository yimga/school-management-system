"""A superadmin holds every permission — including ones invented after they were.

The report was blunt: an account with superuser privileges must never be told it
does not have enough permissions. Two things stood between the platform and that:

* ``ROLE_TEMPLATES`` mapped ``SUPERADMIN -> ["ADMIN"]``, so the top role was
  materialised as the ADMIN access role — which does not carry
  ``settings.feature_control``, ``api_center.manage``, ``accounting.*``,
  ``stock.*``, ``discipline.manage``, ``exam_registration.manage``,
  ``cahier.verify`` or the ``portal.documents/forums/video`` codes; and
* coverage was SEEDED. Migrations 0019, 0048, 0049, 0050 and 0057 each re-listed
  SUPERADMIN by hand, and ``iam.request_access`` shows what one omission costs.

So the load-bearing test here is ``test_a_code_invented_after_the_role_is_still_held``:
it creates a permission that no migration has ever heard of and asserts the
superadmin holds it anyway. That is the difference between a fixed list and a
structural guarantee.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import AccessRole, Permission, TemporaryRoleGrant, User
from apps.accounts.superadmin import SUPERADMIN_ROLE_CODE
from apps.schools.models import School


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class SuperadminCoverageTests(TestCase):
    def setUp(self):
        self.superadmin_role, _ = AccessRole.objects.get_or_create(
            code=SUPERADMIN_ROLE_CODE,
            school=None,
            defaults={"name": "Super Administrator"},
        )
        self.novel_code = _unique("novel.capability").replace("_", ".")
        self.novel = Permission.objects.create(
            code=self.novel_code, name="A capability invented today"
        )

    def _user(self, **kwargs):
        return User.objects.create_user(
            username=_unique("u"), password="Test1234", **kwargs
        )

    def test_a_django_superuser_holds_a_code_invented_after_them(self):
        user = self._user(role=User.Role.PARENT, is_superuser=True)
        self.assertTrue(user.has_feature_permission(self.novel_code))

    def test_a_code_invented_after_the_role_is_still_held(self):
        """The whole point: coverage is structural, not seeded.

        This user is NOT a Django superuser. Nothing granted them the code —
        it did not exist when any migration ran.
        """
        user = self._user(role=User.Role.SUPERADMIN)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.has_feature_permission(self.novel_code))

    def test_the_superadmin_access_role_alone_is_enough(self):
        """No primary role, no Django flag — just the global access role."""
        user = self._user(role=User.Role.TEACHER)
        user.roles.add(self.superadmin_role)
        self.assertTrue(user.has_feature_permission(self.novel_code))

    def test_a_superadmin_holds_every_code_in_the_catalog(self):
        user = self._user(role=User.Role.SUPERADMIN)
        for code in Permission.objects.values_list("code", flat=True):
            with self.subTest(code=code):
                self.assertTrue(
                    user.has_feature_permission(code),
                    f"a superadmin was denied {code}",
                )

    def test_the_codes_the_old_admin_mapping_was_short_are_held(self):
        """Exactly the set SUPERADMIN lost by being materialised as ADMIN."""
        user = self._user(role=User.Role.SUPERADMIN)
        for code in (
            "settings.feature_control",
            "api_center.manage",
            "accounting.manage",
            "stock.manage",
            "discipline.manage",
            "exam_registration.manage",
            "cahier.verify",
            "portal.documents",
            "portal.forums",
            "portal.video",
            "iam.request_access",
        ):
            if not Permission.objects.filter(code=code).exists():
                continue
            with self.subTest(code=code):
                self.assertTrue(user.has_feature_permission(code))

    def test_coverage_holds_when_scoped_to_a_school(self):
        school = School.objects.create(
            name=_unique("Sch"), slug=_unique("s"), subdomain=_unique("sd"), is_active=True
        )
        user = self._user(role=User.Role.SUPERADMIN)
        self.assertTrue(user.has_feature_permission(self.novel_code, school=school))

    def test_an_ordinary_role_is_still_denied(self):
        """God-mode must not have leaked into everyone."""
        user = self._user(role=User.Role.TEACHER)
        self.assertFalse(user.has_feature_permission(self.novel_code))

    def test_a_tenant_minted_superadmin_row_does_not_escalate(self):
        """A tenant can create a catalog row coded SUPERADMIN — it must stay local.

        AccessRole is unique per (school, code), so any tenant admin who can
        create a role could otherwise mint platform god-mode for themselves.
        """
        school = School.objects.create(
            name=_unique("Sch"), slug=_unique("s"), subdomain=_unique("sd"), is_active=True
        )
        rogue = AccessRole.objects.create(
            code=SUPERADMIN_ROLE_CODE, school=school, name="Totally legit"
        )
        user = self._user(role=User.Role.TEACHER)
        user.roles.add(rogue)
        self.assertFalse(
            user.has_feature_permission(self.novel_code, school=school),
            "a tenant-created role coded SUPERADMIN escalated to platform god-mode",
        )

    def test_a_temporary_superadmin_grant_confers_it_and_expires(self):
        from datetime import timedelta

        from django.utils import timezone

        user = self._user(role=User.Role.TEACHER)
        grant = TemporaryRoleGrant.objects.create(
            user=user,
            role=self.superadmin_role,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(user.has_feature_permission(self.novel_code))
        grant.expires_at = timezone.now() - timedelta(hours=1)
        grant.save(update_fields=["expires_at"])
        self.assertFalse(user.has_feature_permission(self.novel_code))


class RoleTemplateIsNotDestructiveTests(TestCase):
    """A role edit used to delete every additionally granted role."""

    def setUp(self):
        self.extra, _ = AccessRole.objects.get_or_create(
            code="IT_ADMIN", school=None, defaults={"name": "IT Administrator"}
        )
        AccessRole.objects.get_or_create(
            code="TEACHER", school=None, defaults={"name": "Teacher"}
        )
        AccessRole.objects.get_or_create(
            code="BURSAR", school=None, defaults={"name": "Bursar"}
        )

    def test_changing_the_primary_role_keeps_deliberately_granted_roles(self):
        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", role=User.Role.TEACHER
        )
        user.roles.add(self.extra)
        self.assertIn("IT_ADMIN", set(user.roles.values_list("code", flat=True)))

        user.role = User.Role.BURSAR
        user.save()

        codes = set(user.roles.values_list("code", flat=True))
        self.assertIn(
            "IT_ADMIN",
            codes,
            "the additionally granted role was silently deleted by a role edit",
        )
        self.assertIn("BURSAR", codes, "the new primary role was not applied")

    def test_the_previous_primary_role_is_withdrawn(self):
        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", role=User.Role.TEACHER
        )
        user.role = User.Role.BURSAR
        user.save()
        self.assertNotIn("TEACHER", set(user.roles.values_list("code", flat=True)))

    def test_a_superadmin_account_materialises_the_superadmin_role(self):
        AccessRole.objects.get_or_create(
            code=SUPERADMIN_ROLE_CODE, school=None, defaults={"name": "Super Administrator"}
        )
        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", role=User.Role.SUPERADMIN
        )
        self.assertIn(
            SUPERADMIN_ROLE_CODE, set(user.roles.values_list("code", flat=True))
        )

    def test_the_template_never_attaches_another_tenants_catalog_row(self):
        """Unscoped, it attached EVERY school's row of the same code."""
        school = School.objects.create(
            name=_unique("Sch"), slug=_unique("s"), subdomain=_unique("sd"), is_active=True
        )
        AccessRole.objects.create(code="TEACHER", school=school, name="Teacher (local)")
        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", role=User.Role.TEACHER
        )
        attached = list(user.roles.filter(code="TEACHER").values_list("school_id", flat=True))
        self.assertEqual(
            attached,
            [None],
            "the role template pulled in a tenant catalog row the user has no claim to",
        )


class ProfileShowsWhatYouActuallyHoldTests(TestCase):
    """The profile said almost nothing true about a user's own access."""

    def setUp(self):
        from apps.accounts.access_summary import effective_access_summary

        self.summarise = effective_access_summary
        self.teacher_role, _ = AccessRole.objects.get_or_create(
            code="TEACHER", school=None, defaults={"name": "Teacher"}
        )
        self.it_role, _ = AccessRole.objects.get_or_create(
            code="IT_ADMIN", school=None, defaults={"name": "IT Administrator"}
        )

    def test_a_superuser_is_not_shown_an_empty_permission_list(self):
        """It listed explicit grant rows only, so god-mode rendered as nothing."""
        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", is_superuser=True
        )
        summary = self.summarise(user)
        self.assertTrue(summary["is_superadmin"])
        self.assertEqual(summary["permission_count"], Permission.objects.count())
        self.assertGreater(summary["permission_count"], 0)
        self.assertTrue(summary["superadmin_label"])

    def test_every_assigned_role_is_listed_not_just_the_primary_one(self):
        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", role=User.Role.TEACHER
        )
        user.roles.add(self.it_role)
        summary = self.summarise(user)
        codes = {r["code"] for r in summary["roles"]}
        self.assertIn("TEACHER", codes)
        self.assertIn("IT_ADMIN", codes)

    def test_a_role_is_labelled_with_where_it_came_from(self):
        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", role=User.Role.TEACHER
        )
        user.roles.add(self.it_role)
        by_code = {r["code"]: r for r in self.summarise(user)["roles"]}
        self.assertEqual(by_code["TEACHER"]["source"], "primary")
        self.assertEqual(by_code["IT_ADMIN"]["source"], "assigned")

    def test_a_permission_names_the_role_that_grants_it(self):
        perm, _ = Permission.objects.get_or_create(
            code="attendance.manage", defaults={"name": "Attendance management"}
        )
        self.teacher_role.permissions.add(perm)
        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", role=User.Role.TEACHER
        )
        entry = next(
            p
            for p in self.summarise(user)["permissions"]
            if p["code"] == "attendance.manage"
        )
        self.assertIn("TEACHER", entry["sources"])

    def test_a_directly_granted_permission_is_shown(self):
        perm = Permission.objects.create(
            code=_unique("direct.code").replace("_", "."), name="Direct"
        )
        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", role=User.Role.PARENT
        )
        user.feature_permissions.add(perm)
        entry = next(
            p for p in self.summarise(user)["permissions"] if p["code"] == perm.code
        )
        self.assertIn("direct", entry["sources"])

    def test_an_active_temporary_grant_appears_on_the_profile(self):
        """It was effective for every permission check and invisible on the page."""
        from datetime import timedelta

        from django.utils import timezone

        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", role=User.Role.PARENT
        )
        TemporaryRoleGrant.objects.create(
            user=user,
            role=self.it_role,
            expires_at=timezone.now() + timedelta(days=2),
        )
        summary = self.summarise(user)
        entry = next(r for r in summary["roles"] if r["code"] == "IT_ADMIN")
        self.assertEqual(entry["source"], "temporary")
        self.assertIsNotNone(entry["expires_at"])

    def test_the_permission_list_is_not_truncated(self):
        """It was sliced [:20] with nothing saying so."""
        user = User.objects.create_user(
            username=_unique("u"), password="Test1234", is_superuser=True
        )
        summary = self.summarise(user)
        if Permission.objects.count() > 20:
            self.assertGreater(len(summary["permissions"]), 20)
        self.assertEqual(len(summary["permissions"]), summary["permission_count"])

    def test_an_anonymous_visitor_gets_an_empty_summary_not_an_error(self):
        from django.contrib.auth.models import AnonymousUser

        summary = self.summarise(AnonymousUser())
        self.assertFalse(summary["available"])
        self.assertEqual(summary["roles"], [])
