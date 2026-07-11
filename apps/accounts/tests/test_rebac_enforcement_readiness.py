"""
End-to-end parity proof for ReBAC sensitive-resource enforcement.

Unlike ``test_rebac_enforce_sensitive`` (which mocks ``has_feature_permission``
to prove the AND-gate mechanics), these tests exercise the REAL
``has_feature_permission`` against REAL relationship tuples produced by the REAL
sync path — proving that colon RBAC and ReBAC actually agree, that operational
drift is detected before a flip, that the enforce-deny is logged, and that a
re-sync heals the drift.
"""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import Permission
from apps.accounts.models_rebac import RelationshipTuple
from apps.accounts.rebac import enforce_permission_token
from apps.accounts.rebac_readiness import (
    SENSITIVE_ENFORCED_CODES,
    enforcement_readiness,
    is_enforcement_ready,
)
from apps.accounts.rebac_sync import sync_user_roles_for_school
from apps.schools.models import School, SchoolMembership

User = get_user_model()


@override_settings(RMC_REBAC_ENFORCE_SENSITIVE=True, RMC_REBAC_ENABLED=True)
class EnforcementReadinessTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Readiness School",
            slug=f"rdy-{uuid.uuid4().hex[:10]}",
            subdomain=f"rdy-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.code = "finance.view"

    def _member_with_direct_perm(self, code: str):
        """Realistic ordering: grant a permission to an EXISTING member so the
        m2m signal writes the ``can`` tuple, exactly as at runtime."""
        user = User.objects.create_user(
            username=f"u-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.local",
            password="x",
            role=User.Role.BURSAR,
        )
        SchoolMembership.objects.create(
            user=user, school=self.school, role=User.Role.BURSAR,
        )
        perm, _ = Permission.objects.get_or_create(
            code=code, defaults={"name": code},
        )
        user.feature_permissions.add(perm)  # fires rebac sync signal
        return user

    def _can_tuples(self, user, code: str):
        return RelationshipTuple.objects.filter(
            school=self.school,
            subject_type="user",
            subject_id=str(user.pk),
            relation="can",
            object_type="permission",
            object_id=code,
        )

    # --- constant is the enforcement SOT --------------------------------------
    def test_sensitive_codes_match_wired_surface(self):
        self.assertEqual(
            set(SENSITIVE_ENFORCED_CODES),
            {"finance.view", "finance.manage", "grade.submit", "attendance.mark"},
        )

    # --- parity holds end-to-end, unmocked ------------------------------------
    def test_real_sync_yields_ready_and_enforcement_allows(self):
        user = self._member_with_direct_perm(self.code)
        # The real sync wrote the tuple, so real RBAC and real ReBAC agree.
        self.assertTrue(self._can_tuples(user, self.code).exists())
        report = enforcement_readiness(self.school)
        self.assertTrue(report.ready)
        self.assertEqual(report.would_be_denied, ())
        # And the real enforcement path (no mocks) allows.
        self.assertTrue(
            enforce_permission_token(user, self.code, school=self.school)
        )

    # --- drift is detected AND enforcement denies AND it is logged ------------
    def test_missing_tuple_is_reported_denied_and_logged(self):
        user = self._member_with_direct_perm(self.code)
        # Simulate an un-backfilled / stale tenant: RBAC grant stands, tuple gone.
        self._can_tuples(user, self.code).delete()

        report = enforcement_readiness(self.school)
        self.assertFalse(report.ready)
        denied = {(g.user_id, g.code) for g in report.would_be_denied}
        self.assertIn((user.pk, self.code), denied)

        with self.assertLogs("apps.accounts.rebac", level="WARNING") as logs:
            allowed = enforce_permission_token(user, self.code, school=self.school)
        self.assertFalse(allowed)
        self.assertTrue(
            any("rebac_enforce_denied" in line for line in logs.output),
            logs.output,
        )

    # --- re-sync heals the drift ----------------------------------------------
    def test_resync_heals_drift(self):
        user = self._member_with_direct_perm(self.code)
        self._can_tuples(user, self.code).delete()
        self.assertFalse(is_enforcement_ready(self.school))

        sync_user_roles_for_school(user, school=self.school)

        self.assertTrue(self._can_tuples(user, self.code).exists())
        self.assertTrue(is_enforcement_ready(self.school))
        self.assertTrue(
            enforce_permission_token(user, self.code, school=self.school)
        )

    # --- superusers never false-flag as a lockout ----------------------------
    def test_superuser_member_is_ready_without_tuples(self):
        su = User.objects.create_user(
            username=f"su-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@test.local",
            password="x",
            role=User.Role.ADMIN,
        )
        su.is_superuser = True
        su.is_staff = True
        su.save(update_fields=["is_superuser", "is_staff"])
        SchoolMembership.objects.create(
            user=su, school=self.school, role=User.Role.ADMIN,
        )
        # No `can` tuples for the sensitive codes, yet superuser passes both sides.
        report = enforcement_readiness(self.school)
        self.assertTrue(report.ready)
        self.assertTrue(
            enforce_permission_token(su, "finance.manage", school=self.school)
        )

    # --- tenant scoping: drift in school A doesn't taint school B -------------
    def test_readiness_is_tenant_scoped(self):
        user = self._member_with_direct_perm(self.code)
        self._can_tuples(user, self.code).delete()  # school A has drift

        other = School.objects.create(
            name="Other School",
            slug=f"oth-{uuid.uuid4().hex[:10]}",
            subdomain=f"oth-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        # School B has no members at all → trivially ready, unaffected by A.
        self.assertFalse(is_enforcement_ready(self.school))
        self.assertTrue(is_enforcement_ready(other))
