"""Durable model-backed proof-before-publish approvals (Phase 3 promotion).

DB-backed: exercises the ``ExperienceRegionApproval`` path taken when a real
tenant School is in context (durable across sessions + auditable ``approved_by``).
The session fallback path (no school / stand-in request) is covered no-DB in
test_experience_rollout.py. RLS is Postgres-only and skipped on the SQLite test
DB; per-school isolation here is proven via the always-``school=``-scoped
service queryset.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.schools.models import School
from apps.studio_os.experience_regions import (
    STUDIO_EXPERIENCE_REGIONS,
    resolve_selected_region,
)
from apps.studio_os.experience_rollout import (
    approve_region,
    build_rollout_status,
    compute_region_fingerprint,
    get_region_approvals,
    reset_region_approval,
    rollout_publish_block,
)
from apps.studio_os.models import ExperienceRegionApproval

User = get_user_model()
HEADER = resolve_selected_region("header")


class _Req:
    """Minimal request stand-in carrying a real tenant School + user."""

    def __init__(self, school, user):
        self.school = school
        self.user = user
        self.session = {}


class ExperienceRegionApprovalModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Rollout Test School",
            slug="rollout-test",
            subdomain="rollout-test",
            is_active=True,
        )
        cls.user = User.objects.create_user(
            username="rollout-approver",
            email="rollout-approver@example.com",
            password="password",
            role=User.Role.IT_ADMIN,
        )

    def _req(self):
        return _Req(self.school, self.user)

    def test_approve_persists_durable_row_with_actor(self):
        req = self._req()
        approve_region(
            req, "header", compute_region_fingerprint(HEADER, {"primary_color": "#2fbcff"})
        )
        row = ExperienceRegionApproval.objects.get(school=self.school, region_key="header")
        self.assertEqual(row.approved_by, self.user)
        self.assertTrue(row.draft_fingerprint)
        approvals = get_region_approvals(req)
        self.assertIn("header", approvals)
        self.assertEqual(approvals["header"]["actor"], "rollout-approver")

    def test_reapprove_updates_not_duplicates(self):
        req = self._req()
        approve_region(req, "header", "aaaa")
        approve_region(req, "header", "bbbb")
        rows = ExperienceRegionApproval.objects.filter(
            school=self.school, region_key="header"
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().draft_fingerprint, "bbbb")

    def test_status_approved_then_stale_on_drift(self):
        req = self._req()
        values = {"primary_color": "#2fbcff"}
        approve_region(req, "header", compute_region_fingerprint(HEADER, values))
        header = next(r for r in build_rollout_status(req, values) if r["key"] == "header")
        self.assertTrue(header["approved"])
        header2 = next(
            r
            for r in build_rollout_status(req, {"primary_color": "#000000"})
            if r["key"] == "header"
        )
        self.assertFalse(header2["approved"])
        self.assertTrue(header2["stale"])

    def test_reset_deletes_row(self):
        req = self._req()
        approve_region(req, "header", "aaaa")
        reset_region_approval(req, "header")
        self.assertFalse(
            ExperienceRegionApproval.objects.filter(
                school=self.school, region_key="header"
            ).exists()
        )

    def test_isolated_per_school(self):
        other = School.objects.create(
            name="Other School", slug="other-sch", subdomain="other-sch", is_active=True
        )
        approve_region(self._req(), "header", "aaaa")
        # A different school's context sees none of this school's approvals.
        self.assertEqual(get_region_approvals(_Req(other, self.user)), {})

    @override_settings(STUDIO_EXPERIENCE_ROLLOUT_ENFORCEMENT="enforce")
    def test_enforce_blocks_until_all_regions_approved(self):
        req = self._req()
        values = {"primary_color": "#2fbcff"}
        self.assertTrue(rollout_publish_block(req, values))  # nothing approved yet
        for region in STUDIO_EXPERIENCE_REGIONS:
            approve_region(req, region["key"], compute_region_fingerprint(region, values))
        self.assertEqual(rollout_publish_block(req, values), [])
