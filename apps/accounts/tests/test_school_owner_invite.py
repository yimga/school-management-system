"""Additional school owners use a password -> mandatory MFA invite flow."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import TenantStaffInvite, User
from apps.accounts.tenant_staff_invites import (
    create_tenant_staff_invite,
    send_tenant_staff_invite,
)
from apps.accounts.views_tenant_identity import (
    tenant_identity_invite,
    tenant_staff_invite_accept,
)
from apps.platform_runtime.models import PlatformEventLog
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

    def _production_command_args(self):
        return [
            "--confirm-production",
            self.school.slug,
            "--confirm-hostname",
            "gilead-tech.runmycampus.com",
            "--confirm-database",
            str(connection.settings_dict["NAME"]),
            "--expected-revision",
            "a" * 40,
        ]

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
        self.assertEqual(first.expires_at, second.expires_at)
        self.assertEqual(
            TenantStaffInvite.objects.filter(
                school=self.school,
                email__iexact="yimgah@yahoo.com",
                accepted_at__isnull=True,
            ).count(),
            1,
        )
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="tenant_staff_invite_created",
                school_id=str(self.school.pk),
            ).exists()
        )

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

    def test_expired_or_used_owner_invite_fails_closed(self):
        for accepted_at, expires_at in (
            (None, timezone.now() - timedelta(seconds=1)),
            (
                timezone.now(),
                timezone.now() + timedelta(days=7),
            ),
        ):
            with self.subTest(accepted=accepted_at is not None):
                invite = TenantStaffInvite.objects.create(
                    school=self.school,
                    email=f"closed-{accepted_at is not None}@example.com",
                    role=User.Role.ADMIN,
                    is_school_owner=True,
                    expires_at=expires_at,
                    accepted_at=accepted_at,
                )
                response = tenant_staff_invite_accept(
                    self._request(
                        "GET",
                        f"/authentication/staff-invite/{invite.token}/",
                        user=AnonymousUser(),
                    ),
                    token=invite.token,
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, "/authentication/login/")

    def test_inactive_school_owner_invite_fails_closed(self):
        self.school.is_active = False
        self.school.save(update_fields=["is_active"])
        invite = TenantStaffInvite.objects.create(
            school=self.school,
            email="inactive-owner@example.com",
            role=User.Role.ADMIN,
            is_school_owner=True,
            expires_at=timezone.now() + timedelta(days=7),
        )
        response = tenant_staff_invite_accept(
            self._request(
                "GET",
                f"/authentication/staff-invite/{invite.token}/",
                user=AnonymousUser(),
            ),
            token=invite.token,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/authentication/login/")

    def test_wrong_school_host_redirects_to_canonical_tenant(self):
        invite = TenantStaffInvite.objects.create(
            school=self.school,
            email="right-host@example.com",
            role=User.Role.ADMIN,
            is_school_owner=True,
            expires_at=timezone.now() + timedelta(days=7),
        )
        other = School.objects.create(
            name="Wrong Host",
            slug="wrong-host",
            subdomain="wrong-host",
            is_active=True,
        )
        request = self._request(
            "GET",
            f"/authentication/staff-invite/{invite.token}/",
            user=AnonymousUser(),
        )
        request.school = other
        response = tenant_staff_invite_accept(request, token=invite.token)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("https://gilead-tech."))
        self.assertIn(str(invite.token), response.url)

    def test_delivery_idempotency_key_never_contains_secret_token(self):
        invite, _created = create_tenant_staff_invite(
            school=self.school,
            email="delivery-audit@example.com",
            role=User.Role.ADMIN,
            invited_by=self.owner,
            is_school_owner=True,
        )
        with patch(
            "apps.schoolops.email_delivery.send_transactional",
            return_value={"queued": True},
        ) as send:
            self.assertTrue(send_tenant_staff_invite(invite))
        key = send.call_args.kwargs["idempotency_key"]
        self.assertNotIn(str(invite.token), key)
        self.assertIn(str(invite.pk), key)
        self.assertFalse(send.call_args.kwargs.get("allow_suppressed", False))
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="tenant_staff_invite_delivery_queued",
                school_id=str(self.school.pk),
            ).exists()
        )

    def test_delivery_failure_expires_invite_so_retry_can_rotate_token(self):
        invite, _created = create_tenant_staff_invite(
            school=self.school,
            email="suppressed-owner@example.com",
            role=User.Role.ADMIN,
            invited_by=self.owner,
            is_school_owner=True,
        )
        with patch(
            "apps.schoolops.email_delivery.send_transactional",
            return_value={"ok": False, "suppressed": True},
        ):
            self.assertFalse(send_tenant_staff_invite(invite))
        invite.refresh_from_db()
        self.assertLessEqual(invite.expires_at, timezone.now())

        retry, created = create_tenant_staff_invite(
            school=self.school,
            email="suppressed-owner@example.com",
            role=User.Role.ADMIN,
            invited_by=self.owner,
            is_school_owner=True,
        )
        self.assertTrue(created)
        self.assertNotEqual(invite.pk, retry.pk)
        self.assertEqual(
            TenantStaffInvite.objects.filter(
                school=self.school,
                email="suppressed-owner@example.com",
                accepted_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).count(),
            1,
        )

    def test_command_dry_run_requires_exact_id_and_slug_and_changes_nothing(self):
        out = StringIO()
        with patch.dict(
            "os.environ",
            {
                "RMC_ENVIRONMENT": "production",
                "RENDER": "true",
                "RENDER_GIT_COMMIT": "a" * 40,
            },
        ), patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            return_value=True,
        ):
            call_command(
                "invite_school_owner",
                "--school-id",
                str(self.school.pk),
                "--slug",
                self.school.slug,
                "--email",
                "yimgah@yahoo.com",
                "--dry-run",
                *self._production_command_args(),
                stdout=out,
            )
        self.assertIn("Dry run", out.getvalue())
        self.assertFalse(
            TenantStaffInvite.objects.filter(email="yimgah@yahoo.com").exists()
        )

    def test_command_refuses_to_mutate_outside_confirmed_production(self):
        with patch.dict(
            "os.environ",
            {"RMC_ENVIRONMENT": "development", "RENDER": "false"},
        ), self.assertRaises(CommandError) as raised:
            call_command(
                "invite_school_owner",
                "--school-id",
                str(self.school.pk),
                "--slug",
                self.school.slug,
                "--email",
                "yimgah@yahoo.com",
                *self._production_command_args(),
            )
        self.assertIn("production-guarded", str(raised.exception))
        self.assertFalse(
            TenantStaffInvite.objects.filter(email="yimgah@yahoo.com").exists()
        )

    def test_command_creates_owner_invite_and_attempts_delivery(self):
        out = StringIO()
        with patch.dict(
            "os.environ",
            {
                "RMC_ENVIRONMENT": "production",
                "RENDER": "true",
                "RENDER_GIT_COMMIT": "a" * 40,
            },
        ), patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            return_value=True,
        ), patch(
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
                *self._production_command_args(),
                stdout=out,
            )
        invite = TenantStaffInvite.objects.get(email="yimgah@yahoo.com")
        self.assertTrue(invite.is_school_owner)
        self.assertEqual(invite.role, User.Role.ADMIN)
        send.assert_called_once()
        self.assertIn("delivered or queued", out.getvalue())

    def test_command_fails_closed_without_exposing_url_when_email_not_queued(self):
        out = StringIO()
        with patch.dict(
            "os.environ",
            {
                "RMC_ENVIRONMENT": "production",
                "RENDER": "true",
                "RENDER_GIT_COMMIT": "a" * 40,
            },
        ), patch(
            "apps.schoolops.email_delivery.transactional_email_configured",
            return_value=True,
        ), patch(
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
                *self._production_command_args(),
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
