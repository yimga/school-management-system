"""The platform SUPERADMIN template must not be assignable from a tenant form.

``roles_queryset_for_school`` is the assignable-roles catalog for every tenant
role surface: ``OwnerBulkRolesForm``, ``UserRoleForm``, ``BulkUserRolesForm`` and
``TemporaryRoleGrantForm`` all bind their choice field to it. It returned every
``school IS NULL`` AccessRole with no exclusions -- and accounts migration 0058
creates exactly such a row, ``code="SUPERADMIN"``, holding
``Permission.objects.all()``.

So a school owner on ``/authentication/owner/people/`` saw a checkbox labelled
"Super Administrator" and could tick it for themselves. ``user.roles.add()`` then
makes ``superadmin_reason()`` return ``assigned-role``, so ``is_platform_superadmin``
is True and ``has_feature_permission(<any code>, school=<any school>)`` returns
True unconditionally -- including at schools where the account is only a PARENT.
``role_applies_to_school`` cannot stop it: a ``school IS NULL`` row applies
everywhere by design.

Promotion to platform super-admin has one sanctioned path (``superadmin_service``
/ ``manage.py promote_superadmin``). A tenant form must not be a second one.

Uses RequestFactory and calls the view directly, matching
test_access_role_school_scope.py: the tenant MFA middleware otherwise redirects a
privileged view to /mfa/setup/ and the assertion becomes vacuous.
"""

from __future__ import annotations

import uuid

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.access_roles import roles_queryset_for_school
from apps.accounts.models import AccessRole, User
from apps.accounts.superadmin import SUPERADMIN_ROLE_CODE, is_platform_superadmin
from apps.accounts.views_owner_console_people import owner_console_people
from apps.schools.models import School, SchoolMembership


@override_settings(POLICY_PDP_ENFORCEMENT_MODE="off")
class SuperadminIsNotTenantAssignableTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        tag = uuid.uuid4().hex[:10]
        self.school = School.objects.create(
            name="Assignable High",
            slug=f"asg-{tag}",
            subdomain=f"asg-{tag}",
            is_active=True,
        )
        # Seeded by accounts migration 0058; get_or_create so the test does not
        # depend on migration state it does not own.
        self.superadmin_role, _ = AccessRole.objects.get_or_create(
            code=SUPERADMIN_ROLE_CODE,
            school=None,
            defaults={"name": "Super Administrator"},
        )
        # A benign platform-global template. Its presence in the same POST is the
        # guard against a vacuous pass: if the form silently rejected everything
        # (bad prefix, missing field, dead view) this role would not land either.
        self.benign_role, _ = AccessRole.objects.get_or_create(
            code="TEACHER",
            school=None,
            defaults={"name": "Teacher"},
        )
        self.owner = User.objects.create_user(
            username=f"owner-{tag}",
            email=f"owner-{tag}@example.com",
            password="pass12345678",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role="ADMIN",
            is_school_owner=True,
            is_primary=True,
        )

    def _post(self, role_pks):
        request = self.factory.post(
            "/authentication/owner/people/",
            {
                "users": [str(self.owner.pk)],
                "roles": [str(pk) for pk in role_pks],
            },
        )
        request.user = self.owner
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        return owner_console_people(request)

    def test_owner_console_reaches_the_bulk_role_form(self) -> None:
        """Guard: the owner gate passes and a global template IS assignable.

        Without this, "SUPERADMIN did not land" would also pass against a view
        that 403'd on the owner check or a form that rejected every POST.
        """
        response = self._post([self.benign_role.pk])
        self.assertEqual(response.status_code, 302)
        self.owner.refresh_from_db()
        self.assertIn(
            self.benign_role.pk,
            set(self.owner.roles.values_list("pk", flat=True)),
        )

    def test_owner_cannot_grant_themselves_the_global_superadmin_role(self) -> None:
        response = self._post([self.superadmin_role.pk, self.benign_role.pk])
        # The form's ModelMultipleChoiceField rejects a pk outside its queryset,
        # so the whole POST is refused and the page re-renders with an error.
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        self.assertNotIn(
            self.superadmin_role.pk,
            set(self.owner.roles.values_list("pk", flat=True)),
        )
        self.assertFalse(is_platform_superadmin(self.owner))
        # And the escalation the role would have bought is not held either.
        self.assertFalse(
            self.owner.has_feature_permission(
                "settings.feature_control", school=self.school
            )
        )

    def test_catalog_excludes_the_global_superadmin_row(self) -> None:
        codes = set(
            roles_queryset_for_school(self.school).values_list("code", flat=True)
        )
        self.assertNotIn(SUPERADMIN_ROLE_CODE, codes)
        # Guard: other platform-global templates are still offered -- the
        # exclusion must be surgical, not "drop the globals".
        self.assertIn("TEACHER", codes)

    def test_catalog_excludes_it_on_the_operator_no_school_branch_too(self) -> None:
        codes = set(roles_queryset_for_school(None).values_list("code", flat=True))
        self.assertNotIn(SUPERADMIN_ROLE_CODE, codes)
        self.assertIn("TEACHER", codes)

    def test_a_school_scoped_row_coded_superadmin_is_still_offered(self) -> None:
        """Only the PLATFORM template is withheld.

        A tenant's own catalog row happening to be coded SUPERADMIN grants exactly
        the permissions attached to it (see apps.accounts.superadmin's docstring),
        so it stays assignable.
        """
        local = AccessRole.objects.create(
            code=SUPERADMIN_ROLE_CODE,
            name="Local super",
            school=self.school,
        )
        self.assertIn(
            local.pk,
            set(roles_queryset_for_school(self.school).values_list("pk", flat=True)),
        )
