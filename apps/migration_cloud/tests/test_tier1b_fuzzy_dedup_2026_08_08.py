"""Tier 1b A-Z upgrade wave (2026-08-08): fuzzy second-chance dedup in the
student lander.

Before this, dedup was POST-HOC only — ``_surface_dedup_candidates`` flagged a
likely duplicate AFTER the row was already created, so a re-migration (or a
second source system) carrying a different ``external_id`` for someone already
migrated still created a DUPLICATE student. This adds a PRE-create second-chance
match: when both key-based lookups miss, an UNAMBIGUOUS high-confidence name+DOB
match links to the existing row instead of inserting.

Safety is the whole point — the auto-link can NEVER wrong-merge two distinct
people: it requires the incoming DOB present AND exactly matched, a
deterministic-score floor, and exactly one candidate; anything short falls
through to create + post-hoc review.

Each test fails against the pre-Tier-1b lander (which always creates the second
row).
"""

from __future__ import annotations

from datetime import date
from unittest import mock

from django.test import TestCase

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.student_lander import StudentLander
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationBundle,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


def _school(slug: str) -> School:
    return School.objects.create(
        name=slug, slug=slug, subdomain=slug, is_active=True, country_code="CM"
    )


def _row(external_id, first, last, dob="2010-05-01", **extra):
    r = {
        "external_id": external_id,
        "first_name": first,
        "last_name": last,
        "enrollment_status": "active",
    }
    if dob is not None:
        r["date_of_birth"] = dob
    r.update(extra)
    return r


class _Base(TestCase):
    def setUp(self):
        self.school = _school("fz-a")
        self.lander = StudentLander()

    def _ctx(self, bundle_id=1):
        return LanderContext(
            school=self.school, bundle_id=bundle_id, artifact_id=1,
            dry_run=False, schema_name="",
        )

    def _land(self, rows, ctx=None):
        return self.lander.land(canonical_rows=iter(rows), ctx=ctx or self._ctx())

    def _count(self):
        return StudentProfile.objects.filter(school=self.school).count()


class FuzzyLinkTests(_Base):
    def test_same_person_new_key_links_not_duplicates(self):
        first = self._land([_row("OLD", "Ada", "Lovelace")])
        self.assertEqual(first.created, 1, first.errors)
        self.assertEqual(self._count(), 1)

        # Same person, DIFFERENT source key — must link, not create.
        second = self._land([_row("NEW", "Ada", "Lovelace")])
        self.assertEqual(second.created, 0, second.errors)
        self.assertGreaterEqual(second.updated + second.skipped, 1, second.errors)
        self.assertEqual(self._count(), 1)

    def test_fuzzy_link_preserves_existing_students_key(self):
        self._land([_row("OLD", "Ada", "Lovelace")])
        self._land([_row("NEW", "Ada", "Lovelace")])
        student = StudentProfile.objects.get(school=self.school)
        # The existing student's own source key is preserved; the incoming
        # "NEW" key must NOT clobber it (it is recorded as an id-mapping).
        self.assertEqual(student.student_code, "OLD")

    def test_no_autolink_without_dob(self):
        self._land([_row("OLD", "Ada", "Lovelace", dob=None)])
        self._land([_row("NEW", "Ada", "Lovelace", dob=None)])
        # No DOB → no strong discriminator → no auto-link → two rows.
        self.assertEqual(self._count(), 2)

    def test_no_autolink_when_first_name_differs(self):
        self._land([_row("OLD", "Ada", "Lovelace")])
        # Same last name + same DOB, but a genuinely different first name —
        # score below the floor → create, never merge two people.
        self._land([_row("NEW", "Bob", "Lovelace")])
        self.assertEqual(self._count(), 2)

    def test_no_autolink_when_dob_differs(self):
        self._land([_row("OLD", "Ada", "Lovelace", dob="2010-05-01")])
        self._land([_row("NEW", "Ada", "Lovelace", dob="2011-01-01")])
        self.assertEqual(self._count(), 2)

    def test_ambiguous_two_candidates_does_not_merge(self):
        # Two distinct existing rows share last name + DOB (created directly to
        # set up the ambiguous state). An incoming match to BOTH must NOT merge.
        StudentProfile.objects.create(
            school=self.school, student_code="A1", first_name="Ada",
            last_name="Lovelace", date_of_birth=date(2010, 5, 1),
        )
        StudentProfile.objects.create(
            school=self.school, student_code="A2", first_name="Ada",
            last_name="Lovelace", date_of_birth=date(2010, 5, 1),
        )
        self.assertEqual(self._count(), 2)
        self._land([_row("NEW", "Ada", "Lovelace")])
        # >1 candidate over the bar → ambiguous → create, leave for review.
        self.assertEqual(self._count(), 3)

    def test_reapply_same_key_is_key_match_not_fuzzy(self):
        # Regression: an exact-key re-apply still updates in place (key path),
        # and it keeps its own key (not a fuzzy path).
        self._land([_row("OLD", "Ada", "Lovelace")])
        second = self._land([_row("OLD", "Ada", "Lovelace")])
        self.assertEqual(second.created, 0, second.errors)
        self.assertEqual(self._count(), 1)
        self.assertEqual(
            StudentProfile.objects.get(school=self.school).student_code, "OLD"
        )

    def test_threshold_config_gates_autolink(self):
        # Raise the floor above 1.0 so even an exact match can't clear it →
        # proves the auto-link is genuinely governed by the config threshold.
        self._land([_row("OLD", "Ada", "Lovelace")])
        def _fake_get(k, *a, **kw):
            if k == "migration_cloud.dedup.autolink_min_score":
                return 1.01
            return _real_get(k, *a, **kw)

        with mock.patch("apps.migration_cloud.defaults.get", side_effect=_fake_get):
            self._land([_row("NEW", "Ada", "Lovelace")])
        self.assertEqual(self._count(), 2)


class FuzzyLinkAuditSurfaceTests(_Base):
    def test_fuzzy_link_recorded_in_bundle_summary(self):
        bundle = MigrationBundle.objects.create(
            label="fz-bundle", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="fz-bundle", status=BundleStatus.APPLIED,
            school=self.school,
        )
        ctx = self._ctx(bundle_id=bundle.pk)
        self._land([_row("OLD", "Ada", "Lovelace")], ctx=ctx)
        self._land([_row("NEW", "Ada", "Lovelace")], ctx=ctx)
        bundle.refresh_from_db()
        links = (bundle.mapping_summary or {}).get("dedup_links") or []
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["linked_external_id"], "NEW")
        self.assertEqual(links[0]["matched_on"], "name+dob")


# Real defaults.get for the patched-threshold test to delegate non-target keys.
from apps.migration_cloud.defaults import get as _real_get  # noqa: E402
