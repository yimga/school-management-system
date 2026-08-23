"""A school without a subdomain must be an ordinary state, not a privilege of the first one.

``subdomain`` was ``blank=True`` AND ``unique=True``. Blank stores ``""``, which both
Postgres and SQLite treat as an ordinary value under a unique index, while NULLs are
distinct from one another. The field therefore read as optional and behaved as "optional
exactly once" -- the second school created without one raised IntegrityError.

That the field is genuinely optional is not an assumption: every consumer in the tree reads
``school.subdomain or school.slug`` and falls back to ``/t/<slug>/``. Schools are created
without one by the OneRoster importer, the schools API, CSV imports, and any
``School.objects.create()`` naming only what it knows.

The tests below are ordered the way the bug was found: prove two subdomain-less schools can
coexist, prove real subdomains are still unique, then pin the normalisation that makes it
true for every WRITER rather than only for code that remembers to pass None.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.schools.models import School


class TwoSchoolsWithoutASubdomainTests(TestCase):
    """The defect itself."""

    def test_a_second_school_can_be_created_without_a_subdomain(self):
        first = School.objects.create(name="First", slug="first-school")
        second = School.objects.create(name="Second", slug="second-school")
        self.assertIsNone(first.subdomain)
        self.assertIsNone(second.subdomain)

    def test_many_schools_can_be_created_without_a_subdomain(self):
        """Two could be a fluke of ordering; a district's worth cannot."""
        for index in range(5):
            School.objects.create(name=f"S{index}", slug=f"s-{index}")
        self.assertEqual(School.objects.filter(subdomain__isnull=True).count(), 5)

    def test_an_explicit_empty_string_also_lands_as_null(self):
        """The shape a ModelForm hands back for an untouched CharField."""
        school = School.objects.create(name="Blank", slug="blank-school", subdomain="")
        school.refresh_from_db()
        self.assertIsNone(school.subdomain)

    def test_two_explicit_empty_strings_do_not_collide(self):
        School.objects.create(name="A", slug="blank-a", subdomain="")
        School.objects.create(name="B", slug="blank-b", subdomain="")
        self.assertEqual(School.objects.filter(subdomain__isnull=True).count(), 2)

    def test_whitespace_is_not_a_subdomain(self):
        school = School.objects.create(name="WS", slug="ws-school", subdomain="   ")
        school.refresh_from_db()
        self.assertIsNone(school.subdomain)


class RealSubdomainsAreStillUniqueTests(TestCase):
    """Calibration. Without this, "no collision" could mean the constraint was dropped."""

    def test_a_duplicate_subdomain_is_still_refused(self):
        School.objects.create(name="One", slug="one-school", subdomain="taken")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                School.objects.create(name="Two", slug="two-school", subdomain="taken")

    def test_a_real_subdomain_is_preserved_exactly(self):
        school = School.objects.create(name="Kept", slug="kept", subdomain="ghs-limbe")
        school.refresh_from_db()
        self.assertEqual(school.subdomain, "ghs-limbe")

    def test_a_padded_subdomain_is_stored_trimmed(self):
        """Otherwise " ghs" and "ghs" are two different tenants at the same address."""
        school = School.objects.create(name="Pad", slug="pad", subdomain="  ghs-buea  ")
        school.refresh_from_db()
        self.assertEqual(school.subdomain, "ghs-buea")


class NormalisationHoldsOnUpdateTests(TestCase):
    """Clearing a subdomain must free it, not park "" in the unique slot."""

    def test_clearing_a_subdomain_stores_null(self):
        school = School.objects.create(name="Clear", slug="clear", subdomain="was-here")
        school.subdomain = ""
        school.save()
        school.refresh_from_db()
        self.assertIsNone(school.subdomain)

    def test_a_cleared_subdomain_can_be_taken_by_another_school(self):
        first = School.objects.create(name="Old", slug="old-owner", subdomain="shared")
        first.subdomain = ""
        first.save()
        second = School.objects.create(name="New", slug="new-owner", subdomain="shared")
        self.assertEqual(second.subdomain, "shared")

    def test_two_schools_can_both_clear_their_subdomains(self):
        """The update path has the same collision as create, and the same fix."""
        a = School.objects.create(name="A", slug="clear-a", subdomain="a-sub")
        b = School.objects.create(name="B", slug="clear-b", subdomain="b-sub")
        a.subdomain = ""
        a.save()
        b.subdomain = ""
        b.save()
        self.assertIsNone(School.objects.get(pk=a.pk).subdomain)
        self.assertIsNone(School.objects.get(pk=b.pk).subdomain)


class ConsumerFallbackTests(TestCase):
    """A NULL must behave like the blank the readers were already written for."""

    def test_the_slug_fallback_still_works(self):
        school = School.objects.create(name="Fallback", slug="fallback-school")
        self.assertEqual(school.subdomain or school.slug, "fallback-school")

    def test_the_fqdn_helper_falls_back_rather_than_building_none_dot_host(self):
        """`f"{None}.runmycampus.com"` is a real host string that resolves nowhere."""
        from apps.schools.domain_sync import school_subdomain_fqdn

        school = School.objects.create(name="NoSub", slug="nosub-school")
        fqdn = school_subdomain_fqdn(school)
        self.assertNotIn("None", fqdn)
        if fqdn:
            self.assertTrue(fqdn.startswith("nosub-school."), fqdn)

    def test_a_subdomain_lookup_does_not_match_a_school_without_one(self):
        """An empty host segment must never resolve to a tenant."""
        School.objects.create(name="NoSub", slug="nosub-2")
        self.assertFalse(School.objects.filter(subdomain="").exists())
