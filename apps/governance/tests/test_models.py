"""Basic model tests for apps.governance (Phase 2A batch 1562)."""

from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.governance.archetypes import ALLOWED_ARCHETYPE_KEYS, get_archetype
from apps.governance.models import GovernanceNode, Organization, OrgMembership
from apps.governance.operating_modes import GovernanceOperatingMode
from apps.governance.services import inherit_domain, resolve_governance_operating_mode
from apps.schools.models import School

User = get_user_model()


class GovernanceServicesTests(SimpleTestCase):
    def test_standalone_namespace_resolves_local_inheritance(self):
        school = SimpleNamespace(
            governance_operating_mode=GovernanceOperatingMode.STANDALONE,
            settings={},
        )
        self.assertEqual(resolve_governance_operating_mode(school), "standalone")
        self.assertEqual(inherit_domain(school, "curriculum"), "local")

    def test_group_member_reads_governance_inherit_without_db(self):
        school = SimpleNamespace(
            governance_operating_mode=GovernanceOperatingMode.GROUP_MEMBER,
            settings={"governance_inherit": {"curriculum": "inherit", "fees": "hybrid"}},
        )
        self.assertEqual(inherit_domain(school, "curriculum"), "inherit")
        self.assertEqual(inherit_domain(school, "fees"), "hybrid")


class OrganizationModelTests(TestCase):
    def test_create_organization_with_legal_owner_type(self):
        org = Organization.objects.create(
            name="Test Trust",
            slug="test-trust",
            legal_owner_type=Organization.LegalOwnerType.CORPORATION,
        )
        self.assertEqual(org.legal_owner_type, Organization.LegalOwnerType.CORPORATION)
        self.assertTrue(org.is_active)

    def test_governance_node_tree_under_organization(self):
        org = Organization.objects.create(name="Diocese", slug="diocese-a")
        root = GovernanceNode.objects.create(
            organization=org,
            name="Central Office",
            slug="central",
        )
        child = GovernanceNode.objects.create(
            organization=org,
            parent=root,
            name="Regional",
            slug="regional",
        )
        self.assertEqual(child.parent_id, root.pk)
        self.assertEqual(root.organization_id, org.pk)


class OrgMembershipModelTests(TestCase):
    def test_org_membership_unique_per_user_org(self):
        org = Organization.objects.create(name="Group", slug="group-a")
        user = User.objects.create_user(username="org-admin", password="Test1234!")
        OrgMembership.objects.create(
            user=user,
            organization=org,
            role=OrgMembership.Role.OWNER,
        )
        self.assertEqual(org.memberships.count(), 1)
        self.assertEqual(user.org_memberships.first().role, OrgMembership.Role.OWNER)


class SchoolGovernanceFieldTests(TestCase):
    def test_standalone_school_defaults_without_organization(self):
        school = School.objects.create(
            name="Standalone Academy",
            slug="standalone-academy",
            subdomain="standalone-academy",
        )
        self.assertIsNone(school.organization_id)
        self.assertEqual(
            school.governance_operating_mode,
            GovernanceOperatingMode.STANDALONE,
        )
        self.assertEqual(resolve_governance_operating_mode(school), "standalone")
        self.assertEqual(inherit_domain(school, "curriculum"), "local")

    def test_group_member_reads_governance_inherit_map(self):
        org = Organization.objects.create(name="MAT", slug="mat-one")
        school = School.objects.create(
            name="Member School",
            slug="member-school",
            subdomain="member-school",
            organization=org,
            governance_operating_mode=GovernanceOperatingMode.GROUP_MEMBER,
            settings={"governance_inherit": {"curriculum": "inherit", "fees": "hybrid"}},
        )
        self.assertEqual(inherit_domain(school, "curriculum"), "inherit")
        self.assertEqual(inherit_domain(school, "fees"), "hybrid")
        self.assertEqual(inherit_domain(school, "branding"), "local")


class ArchetypeCatalogTests(SimpleTestCase):
    def test_four_archetypes_registered(self):
        self.assertEqual(len(ALLOWED_ARCHETYPE_KEYS), 4)
        self.assertIsNotNone(get_archetype("state_emis_hub"))
