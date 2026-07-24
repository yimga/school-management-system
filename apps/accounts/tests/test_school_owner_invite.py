"""Additional school owners use a password -> mandatory MFA invite flow."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.management import CommandError, call_command
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import TenantStaffInvite, User
from apps.accounts.tenant_staff_invites import create_tenant_staff_invite
from apps.accounts.views_tenant_identity import (
    tenant_identity_invite,
    tenant_staff_invite_accept,
)
from apps.schools.models import School, SchoolMembership

UserModel = get_user_model()


class SchoolOwnerInviteTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            id="f984ea95-d2ad-4900-b513-66a345928316",
            name="Gilead Tech",
            slug="gilead-tech",
            subdomain="gilead-tech",
            is_active=True,
        )
        self.owner = UserModel.objects.create_user(
            username="existing-owner@example.com",
            email="existing-owner@example.com",
            password="ExistingOwner123!",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
            is_school_owner=True,
        )

    def _request(self, method, path, *, user, data=None):
        request = (
            self.factory.post(path, data or {})
            if method == "POST"
            else self.factory.get(path)
        )
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request.user = user
        request.school = self.school
        request._messages = FallbackStorage(request)
        return request

    def test_owner_invite_is_idempotently_refreshed(self):
        first, created = create_tenant_staff_invite(
            school=self.school,
            email="yimgah@yahoo.com",
            role=User.Role.ADMIN,
            invited_by=self.owner,
            is_school_owner=True,
        )
        second, created_again = create_tenant_staff_invite(
            school=self.school,
            email="YIMGAH@YAHOO.COM",
            role=User.Role.ADMIN,
            invited_by=self.owner,
            is_school_owner=True,
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertTrue(second.is_school_owner)
        self.assertEqual(second.role, User.Role.ADMIN)

    def test_only_an_owner_can_create_owner_invite(self):
        admin = UserModel.objects.create_user(
            username="plain-admin@example.com",
            email="plain-admin@example.com",
            password="PlainAdmin123!",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=admin,
            school=self.school,
            role=User.Role.ADMIN,
        )
        response = tenant_identity_invite(
            self._request(
                "POST",
                "/authentication/backend/identity/invite/",
                user=admin,
                data={
                    "email": "yimgah@yahoo.com",
                    "role": User.Role.ADMIN,
                    "is_school_owner": "1",
                },
            )
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            TenantStaffInvite.objects.filter(email="yimgah@yahoo.com").exists()
        )

    def test_accept_owner_invite_uses_email_username_and_routes_to_mfa(self):
        invite = TenantStaffInvite.objects.create(
            school=self.school,
            email="yimgah@yahoo.com",
            role=User.Role.ADMIN,
            is_school_owner=True,
            invited_by=self.owner,
            expires_at=timezone.now() + timedelta(days=7),
        )
        request = self._request(
            "POST",
            f"/authentication/staff-invite/{invite.token}/",
            user=AnonymousUser(),
            data={
                "password": "GileadOwner-Strong-2026!",
                "password2": "GileadOwner-Strong-2026!",
            },
        )
        response = tenant_staff_invite_accept(request, token=invite.token)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/mfa/setup", response.url)
        user = UserModel.objects.get(email__iexact="yimgah@yahoo.com")
        self.assertEqual(user.username, "yimgah@yahoo.com")
        self.assertTrue(user.check_password("GileadOwner-Strong-2026!"))
        membership = SchoolMembership.objects.get(user=user, school=self.school)
        self.assertEqual(membership.role, User.Role.ADMIN)
        self.assertTrue(membership.is_school_owner)
        self.assertEqual(str(request.session[SESSION_KEY]), str(user.pk))
        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)

    def test_accept_owner_invite_preserves_existing_platform_authority(self):
        operator = UserModel.objects.create_user(
            username="operator-owner",
            email="operator-owner@example.com",
            password="ExistingOperator123!",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )
        invite = TenantStaffInvite.objects.create(
            school=self.school,
            email=operator.email,
            role=User.Role.ADMIN,
            is_school_owner=True,
            invited_by=self.owner,
            expires_at=timezone.now() + timedelta(days=7),
        )
        response = tenant_staff_invite_accept(
            self._request(
                "POST",
                f"/authentication/staff-invite/{invite.token}/",
                user=AnonymousUser(),
                data={
                    "password": "L8v!Q2m#Z9p@W4x",
                    "password2": "L8v!Q2m#Z9p@W4x",
                },
            ),
            token=invite.token,
        )

        self.assertEqual(response.status_code, 302)
        operator.refresh_from_db()
        self.assertEqual(operator.role, User.Role.SUPERADMIN)
        self.assertTrue(operator.is_superuser)
        membership = SchoolMembership.objects.get(
            user=operator, school=self.school
        )
        self.assertEqual(membership.role, User.Role.ADMIN)
        self.assertTrue(membership.is_school_owner)

    def test_command_dry_run_requires_exact_id_and_slug_and_changes_nothing(self):
        out = StringIO()
        call_command(
            "invite_school_owner",
            "--school-id",
            str(self.school.pk),
            "--slug",
            self.school.slug,
            "--email",
            "yimgah@yahoo.com",
            "--dry-run",
            stdout=out,
        )
        self.assertIn("Dry run", out.getvalue())
        self.assertFalse(
            TenantStaffInvite.objects.filter(email="yimgah@yahoo.com").exists()
        )

    def test_command_creates_owner_invite_and_attempts_delivery(self):
        from unittest.mock import patch

        out = StringIO()
        with patch(
            "apps.accounts.tenant_staff_invites.send_tenant_staff_invite",
            return_value=True,
        ) as send:
            call_command(
                "invite_school_owner",
                "--school-id",
                str(self.school.pk),
                "--slug",
                self.school.slug,
                "--email",
                "YIMGAH@YAHOO.COM",
                stdout=out,
            )
        invite = TenantStaffInvite.objects.get(email="yimgah@yahoo.com")
        self.assertTrue(invite.is_school_owner)
        self.assertEqual(invite.role, User.Role.ADMIN)
        send.assert_called_once()
        self.assertIn("delivered or queued", out.getvalue())

    def test_command_fails_closed_without_exposing_url_when_email_not_queued(self):
        from unittest.mock import patch

        out = StringIO()
        with patch(
            "apps.accounts.tenant_staff_invites.send_tenant_staff_invite",
            return_value=False,
        ), self.assertRaises(CommandError) as raised:
            call_command(
                "invite_school_owner",
                "--school-id",
                str(self.school.pk),
                "--slug",
                self.school.slug,
                "--email",
                "yimgah@yahoo.com",
                stdout=out,
            )
        message = str(raised.exception)
        self.assertIn("not delivered or queued", message)
        self.assertNotIn("/authentication/staff-invite/", message)
        self.assertNotIn("/authentication/staff-invite/", out.getvalue())
        self.assertEqual(
            TenantStaffInvite.objects.filter(
                school=self.school,
                email="yimgah@yahoo.com",
                is_school_owner=True,
            ).count(),
            1,
        )
