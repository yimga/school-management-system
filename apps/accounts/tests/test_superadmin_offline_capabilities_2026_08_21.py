"""God-mode has to hold offline too.

``flatten_capabilities`` feeds the offline permission snapshot and the device
capability bitmap. It read ONLY ReBAC ``can`` tuples, so a platform superadmin
with no tuples written for them — the normal state for an operator identity that
carries no access-role rows — was minted an EMPTY offline capability list.

The bitmap is not enforced server-side yet, so this was latent rather than a live
denial. It is resolved with the same rule the online gate uses, because two
resolvers answering the same question differently is how the original bug
(``role == "SUPERADMIN"`` meaning one thing online and another everywhere else)
happened in the first place.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import AccessRole, Permission, User
from apps.accounts.rebac import flatten_capabilities
from apps.accounts.superadmin import SUPERADMIN_ROLE_CODE
from apps.schools.models import School


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class OfflineCapabilitiesFollowTheSameRuleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name=_unique("Sch"),
            slug=_unique("s"),
            subdomain=_unique("sd"),
            is_active=True,
        )
        self.novel = Permission.objects.create(
            code=_unique("offline.novel").replace("_", "."),
            name="A capability invented today",
        )

    def _user(self, **kwargs):
        return User.objects.create_user(
            username=_unique("u"), password="Test1234", **kwargs
        )

    def test_a_superuser_with_no_tuples_still_gets_the_catalog(self):
        """The exact shape that minted an empty bitmap."""
        user = self._user(role=User.Role.PARENT, is_superuser=True)
        caps = flatten_capabilities(user, school=self.school)
        self.assertEqual(len(caps), Permission.objects.count())
        self.assertIn(self.novel.code, caps)

    def test_the_superadmin_role_alone_is_enough_offline(self):
        user = self._user(role=User.Role.SUPERADMIN)
        self.assertFalse(user.is_superuser)
        self.assertIn(self.novel.code, flatten_capabilities(user, school=self.school))

    def test_the_global_access_role_is_enough_offline(self):
        role, _ = AccessRole.objects.get_or_create(
            code=SUPERADMIN_ROLE_CODE,
            school=None,
            defaults={"name": "Super Administrator"},
        )
        user = self._user(role=User.Role.TEACHER)
        user.roles.add(role)
        self.assertIn(self.novel.code, flatten_capabilities(user, school=self.school))

    def test_an_ordinary_user_gains_nothing(self):
        """God-mode must not have leaked into the offline path for everyone."""
        user = self._user(role=User.Role.TEACHER)
        self.assertEqual(flatten_capabilities(user, school=self.school), [])

    def test_a_missing_school_still_returns_nothing(self):
        """The token is tenant-scoped; no school, no capabilities — even for god."""
        user = self._user(role=User.Role.PARENT, is_superuser=True)
        self.assertEqual(flatten_capabilities(user, school=None), [])

    def test_the_device_bitmap_reflects_it(self):
        """The bitmap is what a device actually carries offline."""
        from apps.accounts.iam_snapshot import offline_capability_bitmap

        user = self._user(role=User.Role.PARENT, is_superuser=True)
        bitmap = offline_capability_bitmap(user, school=self.school)
        self.assertIn(self.novel.code, bitmap)
        self.assertLessEqual(len(bitmap), 64, "the bitmap is capped at 64 entries")
