"""Phase 6 — Organization-derived mat_groups registry tests."""

from __future__ import annotations

from django.test import TestCase

from apps.governance.mat_groups_sync import (
    build_mat_groups_payload_from_organizations,
    merge_mat_groups_payloads,
    resolve_mat_groups_payload,
)
from apps.governance.models import Organization
from apps.governance.operating_modes import GovernanceOperatingMode
from apps.schools.mat_group_hub import load_registry_from_operator_settings, parse_mat_registry
from apps.schools.models import School


class MatGroupsOrganizationSyncTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Greenwich Trust",
            slug="greenwich-trust",
            legal_owner_type=Organization.LegalOwnerType.CORPORATION,
        )
        self.school_a = School.objects.create(
            name="Greenwich Park",
            slug="greenwich-park",
            subdomain="greenwich-park",
            organization=self.org,
            governance_operating_mode=GovernanceOperatingMode.GROUP_MEMBER,
        )
        self.school_b = School.objects.create(
            name="Meridian Primary",
            slug="meridian-primary",
            subdomain="meridian-primary",
            organization=self.org,
            governance_operating_mode=GovernanceOperatingMode.GROUP_MEMBER_SOVEREIGN,
        )
        School.objects.create(
            name="Standalone Academy",
            slug="standalone-academy",
            subdomain="standalone-academy",
            organization=self.org,
            governance_operating_mode=GovernanceOperatingMode.STANDALONE,
        )

    def test_build_payload_from_organization_members(self):
        payload = build_mat_groups_payload_from_organizations()
        self.assertIn("greenwich-trust", payload)
        group = payload["greenwich-trust"]
        self.assertEqual(group["display_name"], "Greenwich Trust")
        slugs = {m["tenant_slug"] for m in group["members"]}
        self.assertEqual(slugs, {"greenwich-park", "meridian-primary"})

    def test_merge_prefers_derived_over_legacy_same_group_id(self):
        derived = {
            "greenwich-trust": {
                "display_name": "Derived Trust",
                "members": [{"tenant_slug": "greenwich-park", "display_name": "GP"}],
            }
        }
        legacy = {
            "greenwich-trust": {
                "display_name": "Legacy Trust",
                "members": [{"tenant_slug": "old-slug", "display_name": "Old"}],
            },
            "legacy-only": {
                "display_name": "Legacy Only",
                "members": [{"tenant_slug": "x", "display_name": "X"}],
            },
        }
        merged = merge_mat_groups_payloads(derived, legacy)
        self.assertEqual(merged["greenwich-trust"]["display_name"], "Derived Trust")
        self.assertIn("legacy-only", merged)

    def test_load_registry_includes_organization_backed_group(self):
        groups = load_registry_from_operator_settings()
        self.assertTrue(any(g.group_id == "greenwich-trust" for g in groups))
        group = next(g for g in groups if g.group_id == "greenwich-trust")
        self.assertEqual(len(group.members), 2)

    def test_resolve_payload_is_parseable(self):
        payload = resolve_mat_groups_payload()
        groups = parse_mat_registry(payload)
        self.assertGreaterEqual(len(groups), 1)
