"""Unit tests for School.get_child_schools (nested tenancy / me/schools child_schools)."""

from django.test import TestCase

from apps.schools.models import School


class SchoolGetChildSchoolsTests(TestCase):
    def test_returns_direct_active_children_ordered_by_name(self):
        parent = School.objects.create(
            name="Zeta Parent",
            slug="zeta-parent",
            subdomain="zeta-parent",
            is_active=True,
        )
        c_b = School.objects.create(
            name="Beta Child",
            slug="beta-child",
            subdomain="beta-child",
            is_active=True,
            parent_school=parent,
        )
        c_a = School.objects.create(
            name="Alpha Child",
            slug="alpha-child",
            subdomain="alpha-child",
            is_active=True,
            parent_school=parent,
        )
        School.objects.create(
            name="Inactive Child",
            slug="inactive-child",
            subdomain="inactive-child",
            is_active=False,
            parent_school=parent,
        )
        other = School.objects.create(
            name="Other root",
            slug="other-root",
            subdomain="other-root",
            is_active=True,
        )
        School.objects.create(
            name="Other child",
            slug="other-child",
            subdomain="other-child",
            is_active=True,
            parent_school=other,
        )
        qs = list(parent.get_child_schools())
        self.assertEqual([s.id for s in qs], [c_a.id, c_b.id])

    def test_empty_when_no_children(self):
        root = School.objects.create(
            name="Lonely",
            slug="lonely",
            subdomain="lonely",
            is_active=True,
        )
        self.assertEqual(list(root.get_child_schools()), [])
