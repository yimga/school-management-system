"""Family/student portal hats must not surface admin sidebar items."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.portal_sidebar_items import build_portal_sidebar_items

User = get_user_model()

_ADMIN_SECTIONS = frozenset(
    {
        "Financial Management",
        "Admin Panel",
        "People & Access",
        "Analytics & Reports",
    }
)


class PortalSidebarRoleGatingTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = get_platform_site_settings_record(create=True)

    def _items(self, user, *, session_role=None):
        request = self.factory.get("/portal/parent/")
        request.user = user
        request.session = {}
        if session_role:
            request.session["active_portal_role"] = session_role
        return build_portal_sidebar_items(request, self.site)

    def _sections(self, items):
        return {it.get("section") for it in items}

    def test_parent_with_is_staff_does_not_get_admin_nav(self):
        user = User.objects.create_user(
            username="parent_staff",
            email="parent_staff@example.com",
            password="Test1234!long",
            role=User.Role.PARENT,
            is_staff=True,
        )
        sections = self._sections(self._items(user, session_role=User.Role.PARENT))
        self.assertNotIn("Financial Management", sections)
        self.assertNotIn("Admin Panel", sections)
        self.assertIn("Children & Learning", sections)

    def test_admin_primary_with_parent_hat_gets_parent_only_nav(self):
        user = User.objects.create_user(
            username="admin_parent_hat",
            email="admin_parent_hat@example.com",
            password="Test1234!long",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        sections = self._sections(self._items(user, session_role=User.Role.PARENT))
        for blocked in _ADMIN_SECTIONS:
            self.assertNotIn(blocked, sections, msg=blocked)

    def test_admin_parent_session_hat_without_guardian_uses_parent_nav(self):
        """Session hat must drive sidebar even when has_parent_hat is false."""
        user = User.objects.create_user(
            username="admin_parent_hat_only",
            email="admin_parent_hat_only@example.com",
            password="Test1234!long",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        items = self._items(user, session_role=User.Role.PARENT)
        sections = self._sections(items)
        ids = {it.get("id") for it in items}
        for blocked in _ADMIN_SECTIONS:
            self.assertNotIn(blocked, sections, msg=blocked)
        self.assertIn("contact_school", ids)
        self.assertIn("my_children", ids)
        self.assertNotIn("message_groups", ids)

    def test_student_with_is_staff_does_not_get_admin_nav(self):
        user = User.objects.create_user(
            username="student_staff",
            email="student_staff@example.com",
            password="Test1234!long",
            role=User.Role.STUDENT,
            is_staff=True,
        )
        sections = self._sections(self._items(user, session_role=User.Role.STUDENT))
        self.assertNotIn("Admin Panel", sections)
        self.assertIn("Learning", sections)

    def test_no_duplicate_label_url_pairs(self):
        user = User.objects.create_superuser(
            username="sidebar_dedup_super",
            email="sidebar_dedup_super@example.com",
            password="Test1234!long",
        )
        seen = set()
        for it in self._items(user):
            key = (it.get("label"), it.get("url"))
            if key[1]:
                self.assertNotIn(key, seen, msg=f"duplicate nav: {key[0]}")
                seen.add(key)
