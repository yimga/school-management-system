"""Identity migration must recreate users + memberships + MFA on a fresh box.

The tenant bundle excludes the shared/public identity parents (User, SchoolMembership,
django_otp devices), so the cloud's real admins/staff never reached the edge box. This
suite proves the dedicated identity bundle carries them faithfully: passwords (hash
copied -> existing credentials still work), owner authority, and confirmed TOTP + backup
codes (authenticator apps keep working). Fail-closed on a tampered signature; idempotent
on re-run.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid

from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.test import TestCase

from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.lifecycle.tenant_identity_portability import (
    export_tenant_identities,
    import_tenant_identities,
    read_identity_payload,
)
from apps.schools.models import School, SchoolMembership
from apps.schools.rls_context import rls_bypass

User = get_user_model()

_OWNER_PW = "Owner-Str0ng-Pass99"
_STAFF_PW = "Staff-Str0ng-Pass88"
_TOTP_KEY = "3132333435363738393031323334353637383930"  # fixed hex secret


class TenantIdentityPortabilityTests(TestCase):
    SLUG = "gilead-tech"

    def _make_school(self):
        with rls_bypass():
            School.objects.filter(slug=self.SLUG).delete()
        return School.objects.create(
            id=uuid.uuid4(),
            name="Gilead Technical High School",
            slug=self.SLUG,
            subdomain=self.SLUG,
            is_active=True,
            is_approved=True,
            country_code="CM",
            settings={},
        )

    def _seed_identities(self, school):
        # Owner: SUPERADMIN role + is_superuser + confirmed TOTP + backup codes.
        owner = User.objects.create_user(
            username="owner1", email="owner1@gilead.school.lan", password=_OWNER_PW
        )
        owner.role = "SUPERADMIN"
        owner.is_superuser = True
        owner.is_staff = True
        owner.save()
        SchoolMembership.objects.create(
            user=owner, school=school, role="ADMIN", is_school_owner=True, is_primary=True
        )
        TOTPDevice.objects.create(user=owner, name="default", key=_TOTP_KEY, confirmed=True)
        sd = StaticDevice.objects.create(user=owner, name="backup", confirmed=True)
        StaticToken.objects.create(device=sd, token="AAAA1111")
        StaticToken.objects.create(device=sd, token="BBBB2222")

        # Second admin: plain, no MFA, not an owner.
        staff = User.objects.create_user(
            username="admin2", email="admin2@gilead.school.lan", password=_STAFF_PW
        )
        staff.role = "ADMIN"
        staff.save()
        SchoolMembership.objects.create(
            user=staff, school=school, role="ADMIN", is_school_owner=False
        )
        return owner, staff

    def _wipe_identities(self, school, usernames):
        with rls_bypass():
            SchoolMembership.objects.filter(school=school).delete()
            for uname in usernames:
                u = User.objects.filter(username=uname).first()
                if u:
                    TOTPDevice.objects.filter(user=u).delete()
                    StaticDevice.objects.filter(user=u).delete()
                    u.delete()

    def test_export_import_recreates_users_memberships_and_mfa(self):
        school = self._make_school()
        self._seed_identities(school)
        blob = export_tenant_identities(school)

        # Simulate the fresh box: none of these identities exist (School stays).
        self._wipe_identities(school, ["owner1", "admin2"])
        self.assertFalse(User.objects.filter(username="owner1").exists())

        result = import_tenant_identities(blob, expected_school_id=str(school.id))
        self.assertEqual(result["users"], 2)
        self.assertEqual(result["owners"], 1)

        # (1) Users recreated + passwords preserved (login with EXISTING creds).
        self.assertIsNotNone(authenticate(username="owner1", password=_OWNER_PW))
        self.assertIsNotNone(authenticate(username="admin2", password=_STAFF_PW))

        # (2) Owner role normalized SUPERADMIN -> ADMIN, is_superuser preserved.
        owner = User.objects.get(username="owner1")
        self.assertEqual(owner.role, "ADMIN")
        self.assertTrue(owner.is_superuser)

        # (3) Membership + active-owner authority restored.
        self.assertTrue(
            SchoolMembership.objects.filter(
                user=owner, school=school, is_school_owner=True
            ).exists()
        )
        self.assertTrue(SchoolMembership.has_active_owner(school))

        # (4) MFA carried: confirmed TOTP with the SAME secret + both backup codes.
        totp = TOTPDevice.objects.filter(user=owner, confirmed=True).first()
        self.assertIsNotNone(totp)
        self.assertEqual(totp.key, _TOTP_KEY)
        self.assertEqual(StaticToken.objects.filter(device__user=owner).count(), 2)

    def test_reimport_is_idempotent(self):
        school = self._make_school()
        self._seed_identities(school)
        blob = export_tenant_identities(school)
        # Import over the EXISTING identities (no wipe): must not duplicate anything.
        import_tenant_identities(blob, expected_school_id=str(school.id))
        self.assertEqual(
            User.objects.filter(username__in=["owner1", "admin2"]).count(), 2
        )
        self.assertEqual(SchoolMembership.objects.filter(school=school).count(), 2)
        self.assertEqual(TOTPDevice.objects.filter(user__username="owner1").count(), 1)
        self.assertEqual(
            StaticToken.objects.filter(device__user__username="owner1").count(), 2
        )

    def test_signature_tamper_fails_closed(self):
        school = self._make_school()
        self._seed_identities(school)
        blob = export_tenant_identities(school)
        container = json.loads(blob)
        container["sig"] = ("00" + container["sig"][2:]) if container["sig"] else "00"
        tampered = json.dumps(container).encode("utf-8")
        with self.assertRaises(ValueError):
            read_identity_payload(tampered, expected_school_id=str(school.id))

    def test_command_dry_run_writes_nothing(self):
        school = self._make_school()
        self._seed_identities(school)
        blob = export_tenant_identities(school)
        self._wipe_identities(school, ["owner1", "admin2"])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gilead.rmcidentity")
            with open(path, "wb") as fh:
                fh.write(blob)
            call_command(
                "import_tenant_identities", in_path=path, slug=self.SLUG, dry_run=True
            )
        self.assertFalse(User.objects.filter(username="owner1").exists())
