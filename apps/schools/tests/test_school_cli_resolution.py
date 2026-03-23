"""Tests for management-command school resolution (UUID vs slug vs legacy int)."""

from django.test import TestCase

from apps.schools.models import School
from apps.schools.school_cli_resolution import resolve_school_arg


class ResolveSchoolArgTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="CLI Resolve",
            slug="cli-resolve-school",
            subdomain="cli-resolve-school",
            is_active=True,
        )

    def test_empty_returns_none(self):
        self.assertIsNone(resolve_school_arg(None))
        self.assertIsNone(resolve_school_arg(""))
        self.assertIsNone(resolve_school_arg("   "))

    def test_resolves_by_slug(self):
        self.assertEqual(resolve_school_arg("cli-resolve-school").pk, self.school.pk)

    def test_resolves_by_uuid_string(self):
        self.assertEqual(
            resolve_school_arg(str(self.school.pk)).pk, self.school.pk
        )
