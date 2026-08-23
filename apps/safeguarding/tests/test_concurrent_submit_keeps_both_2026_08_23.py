"""Two concerns raised close together must both survive.

``submit_concern_for_school`` reads ``school.settings`` off the object it was
HANDED, appends its concern to the in-memory copy, and writes the whole blob back:

    settings = dict(getattr(school, "settings", None) or {})
    settings = append_to_school_settings(school_settings=settings, concern=entry)
    ...
    school.settings = settings
    school.save(update_fields=["settings"])

Nothing re-reads the row and nothing locks it. Two submissions that overlap -- two
teachers filing after the same assembly, or one request racing a Celery sweep --
each start from the settings they last saw and each write the WHOLE blob, so the
second save erases the first concern. There is no error and no log: the reporter
is told it was recorded.

The same read-modify-write also clobbers unrelated keys. ``School.settings`` is the
platform's general per-tenant blob, so a concern submitted while, say, a wizard
step was saving takes the wizard's write with it.

This is DETERMINISTIC to test without threads, because the defect is not really
about timing: it is that the function trusts a possibly-stale in-memory object. A
caller holding a School instance loaded before another write has exactly the stale
copy a racing request would have.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.safeguarding.services import find_concern, submit_concern_for_school
from apps.schools.models import School, SchoolMembership


class ConcurrentSubmitKeepsBothTests(TestCase):
    def setUp(self):
        slug = f"sgrace-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Race School", slug=slug, subdomain=slug
        )
        self.reporter = User.objects.create_user(username=f"rep_{slug}", password="x")
        self.admin = User.objects.create_user(username=f"adm_{slug}", password="x")
        self.admin.role = "ADMIN"
        self.admin.save(update_fields=["role"])
        for user, role in ((self.reporter, "TEACHER"), (self.admin, "ADMIN")):
            SchoolMembership.objects.create(user=user, school=self.school, role=role)

    def _submit(self, school, narrative):
        return submit_concern_for_school(
            school=school,
            reporter_user_id=self.reporter.pk,
            category_key="physical_abuse",
            narrative=narrative,
        )

    def test_two_sequential_concerns_both_persist(self):
        # Calibration: the sequential path always worked. If this fails the
        # function is broken outright and the race test below proves nothing.
        first = self._submit(self.school, "First disclosure.")
        fresh = School.objects.get(pk=self.school.pk)
        second = self._submit(fresh, "Second disclosure.")

        latest = School.objects.get(pk=self.school.pk)
        self.assertIsNotNone(find_concern(latest, first.concern_id))
        self.assertIsNotNone(find_concern(latest, second.concern_id))

    def test_a_stale_school_object_does_not_erase_the_other_concern(self):
        """The racing case, made deterministic.

        ``stale`` is loaded BEFORE the first concern is written, so it carries
        exactly the settings a concurrent request would have been holding.
        """
        stale = School.objects.get(pk=self.school.pk)

        first = self._submit(School.objects.get(pk=self.school.pk), "First disclosure.")
        second = self._submit(stale, "Second disclosure.")

        latest = School.objects.get(pk=self.school.pk)
        self.assertIsNotNone(
            find_concern(latest, second.concern_id),
            "the second concern was not recorded at all",
        )
        self.assertIsNotNone(
            find_concern(latest, first.concern_id),
            "the second submission erased the first child-protection disclosure",
        )

    def test_an_unrelated_settings_key_written_meanwhile_survives(self):
        """School.settings is the shared per-tenant blob, not safeguarding's own."""
        stale = School.objects.get(pk=self.school.pk)

        fresh = School.objects.get(pk=self.school.pk)
        fresh.settings = dict(fresh.settings or {}, wizard_step="branding")
        fresh.save(update_fields=["settings"])

        self._submit(stale, "Disclosure during a wizard save.")

        latest = School.objects.get(pk=self.school.pk)
        self.assertEqual(
            (latest.settings or {}).get("wizard_step"),
            "branding",
            "the concern write clobbered an unrelated tenant setting",
        )
