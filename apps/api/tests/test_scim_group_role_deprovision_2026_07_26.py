"""F5a — SCIM group->role mapping + tenant-safe deprovisioning (2026-07-26).

Covers the two enterprise-rails gaps closed in ``apps/api/scim_views.py``:

* an IdP group (SCIM Group / AccessRole) can now set a member's tenant role via
  ``config["group_role_map"]``, guarded by the provisionable-role deny set; and
* SCIM DELETE defaults to a tenant-safe per-school suspend (``SchoolMembership.
  suspended_at``) instead of flipping the shared ``User.is_active`` across every
  school the user belongs to.
"""

import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import AccessRole, User
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import ServiceIntegration

USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"


class ScimGroupRoleAndDeprovisionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Group Role School",
            slug="group-role-school",
            subdomain="group-role-school",
            is_active=True,
        )
        self.integration = ServiceIntegration.objects.create(
            school=self.school,
            service_name="SCIM Directory",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            client_secret="tok-a",
            config={
                "bearer_token": "tok-a",
                "default_role": User.Role.PARENT,
                "group_role_map": {"Teachers": User.Role.HOD},
            },
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="member.one",
            email="member.one@example.com",
            password="x",
            role=User.Role.PARENT,
        )
        self.membership = SchoolMembership.objects.create(
            school=self.school,
            user=self.user,
            role=User.Role.PARENT,
            is_primary=True,
        )
        self.group = AccessRole.objects.create(code="idp_teachers", name="Teachers")

    # ---- helpers ----------------------------------------------------------

    def _headers(self, token="tok-a"):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _url(self, name, *args):
        base = reverse(name, args=args)
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}school_slug={self.school.slug}"

    def _patch_group_members(self, group, op, user, group_id=None):
        payload = {
            "schemas": [PATCH_SCHEMA],
            "Operations": [
                {"op": op, "path": "members", "value": [{"value": str(user.pk)}]}
            ],
        }
        return self.client.patch(
            self._url("api:scim-group-detail", group_id or group.pk),
            data=json.dumps(payload),
            content_type="application/json",
            **self._headers(),
        )

    def _delete_user(self, user):
        return self.client.delete(
            self._url("api:scim-user-detail", user.pk), **self._headers()
        )

    # ---- group -> role mapping -------------------------------------------

    def test_group_role_map_sets_membership_role(self):
        resp = self._patch_group_members(self.group, "add", self.user)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, User.Role.HOD)
        # And it surfaces in the SCIM user payload (roles reads membership.role).
        detail = self.client.get(
            self._url("api:scim-user-detail", self.user.pk), **self._headers()
        )
        self.assertEqual(detail.json()["roles"][0]["value"], User.Role.HOD)

    def test_group_role_map_matches_on_code_too(self):
        # Map keyed on the AccessRole *code* rather than its display name.
        self.integration.config = {
            "bearer_token": "tok-a",
            "group_role_map": {"idp_teachers": User.Role.TEACHER},
        }
        self.integration.save(update_fields=["config"])
        resp = self._patch_group_members(self.group, "add", self.user)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, User.Role.TEACHER)

    def test_group_role_map_denies_non_provisionable_role(self):
        # A group must not be able to escalate a member to SUPERADMIN.
        self.integration.config = {
            "bearer_token": "tok-a",
            "group_role_map": {"Teachers": User.Role.SUPERADMIN},
        }
        self.integration.save(update_fields=["config"])
        resp = self._patch_group_members(self.group, "add", self.user)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, User.Role.PARENT)  # unchanged

    def test_group_with_no_map_leaves_role_untouched(self):
        self.integration.config = {"bearer_token": "tok-a"}
        self.integration.save(update_fields=["config"])
        resp = self._patch_group_members(self.group, "add", self.user)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, User.Role.PARENT)
        # The AccessRole M2M is still attached (existing behavior preserved).
        self.assertTrue(self.user.roles.filter(pk=self.group.pk).exists())

    # ---- tenant-safe deprovisioning --------------------------------------

    def test_delete_suspends_only_this_school_for_multi_school_user(self):
        # THE cross-tenant bug fix: the user also belongs to a second school.
        other = School.objects.create(
            name="Other School",
            slug="other-school-dp",
            subdomain="other-school-dp",
            is_active=True,
        )
        other_membership = SchoolMembership.objects.create(
            school=other, user=self.user, role=User.Role.PARENT
        )
        resp = self._delete_user(self.user)
        self.assertEqual(resp.status_code, 204)
        self.membership.refresh_from_db()
        other_membership.refresh_from_db()
        self.user.refresh_from_db()
        self.assertIsNotNone(self.membership.suspended_at)  # this school suspended
        self.assertIsNone(other_membership.suspended_at)  # other school untouched
        self.assertTrue(self.user.is_active)  # shared account NOT disabled

    def test_delete_deactivates_user_when_last_active_membership(self):
        resp = self._delete_user(self.user)
        self.assertEqual(resp.status_code, 204)
        self.membership.refresh_from_db()
        self.user.refresh_from_db()
        self.assertIsNotNone(self.membership.suspended_at)
        self.assertFalse(self.user.is_active)  # no other membership -> locked out

    def test_delete_mode_deactivate_user_flips_shared_account(self):
        self.integration.config = {
            "bearer_token": "tok-a",
            "scim_deprovision_mode": "deactivate_user",
        }
        self.integration.save(update_fields=["config"])
        resp = self._delete_user(self.user)
        self.assertEqual(resp.status_code, 204)
        self.user.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertIsNone(self.membership.suspended_at)  # membership row kept as-is

    def test_delete_mode_hard_delete_removes_membership(self):
        self.integration.config = {
            "bearer_token": "tok-a",
            "scim_deprovision_mode": "hard_delete_membership",
        }
        self.integration.save(update_fields=["config"])
        resp = self._delete_user(self.user)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(
            SchoolMembership.objects.filter(pk=self.membership.pk).exists()
        )

    def test_delete_legacy_hard_delete_boolean_still_honored(self):
        self.integration.config = {
            "bearer_token": "tok-a",
            "scim_hard_delete_membership": True,
        }
        self.integration.save(update_fields=["config"])
        resp = self._delete_user(self.user)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(
            SchoolMembership.objects.filter(pk=self.membership.pk).exists()
        )
