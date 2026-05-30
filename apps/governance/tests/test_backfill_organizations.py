"""Phase 6B — Organization backfill from hierarchy silos."""

from __future__ import annotations

from django.test import TestCase

from apps.governance.backfill_organizations import (
    backfill_from_parent_school_trees,
    backfill_organizations_from_hierarchy,
)
from apps.governance.models import Organization
from apps.governance.operating_modes import GovernanceOperatingMode
from apps.schools.models import School


class BackfillOrganizationsFromHierarchyTests(TestCase):
    def test_parent_school_tree_dry_run_does_not_write(self):
        root = School.objects.create(
            name="Trust Root",
            slug="trust-root",
            subdomain="trust-root",
        )
        School.objects.create(
            name="Member One",
            slug="member-one",
            subdomain="member-one",
            parent_school=root,
        )
        result = backfill_from_parent_school_trees(apply=False)
        self.assertEqual(result.organizations_created, 1)
        self.assertEqual(result.schools_linked, 2)
        self.assertEqual(Organization.objects.count(), 0)
        self.assertIsNone(root.organization_id)

    def test_parent_school_tree_apply_links_schools(self):
        root = School.objects.create(
            name="Trust Root",
            slug="trust-root-apply",
            subdomain="trust-root-apply",
        )
        child = School.objects.create(
            name="Member Apply",
            slug="member-apply",
            subdomain="member-apply",
            parent_school=root,
        )
        result = backfill_from_parent_school_trees(apply=True)
        self.assertEqual(result.organizations_created, 1)
        self.assertEqual(result.schools_linked, 2)
        org = Organization.objects.get(slug="trust-root-apply")
        root.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(root.organization_id, org.pk)
        self.assertEqual(child.organization_id, org.pk)
        self.assertEqual(root.governance_operating_mode, GovernanceOperatingMode.STANDALONE)

    def test_promote_group_mode_when_flag_set(self):
        root = School.objects.create(
            name="Promote Root",
            slug="promote-root",
            subdomain="promote-root",
        )
        School.objects.create(
            name="Promote Child",
            slug="promote-child",
            subdomain="promote-child",
            parent_school=root,
        )
        backfill_from_parent_school_trees(apply=True, promote_group_mode=True)
        root.refresh_from_db()
        self.assertEqual(root.governance_operating_mode, GovernanceOperatingMode.GROUP_MEMBER)

    def test_idempotent_second_run_skips_linked(self):
        root = School.objects.create(
            name="Idempotent Root",
            slug="idempotent-root",
            subdomain="idempotent-root",
        )
        School.objects.create(
            name="Idempotent Child",
            slug="idempotent-child",
            subdomain="idempotent-child",
            parent_school=root,
        )
        first = backfill_organizations_from_hierarchy(apply=True)
        second = backfill_organizations_from_hierarchy(apply=True)
        self.assertEqual(first.organizations_created, 1)
        self.assertEqual(second.organizations_created, 0)
        self.assertEqual(second.schools_skipped, 2)
