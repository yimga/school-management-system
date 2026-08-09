"""Seals: provisioning must be savepoint-isolated; apply-claim guards preserved.

1. ``resolve_or_provision_user`` / guardian ``_resolve_or_provision_user`` called
   ``User.objects.create_user`` OUTSIDE any savepoint. Under the forced-atomic
   finance apply, a real create_user IntegrityError (a concurrent apply racing
   the same email-derived username) marks the WHOLE connection needs_rollback,
   so the lander's per-row try/except cannot continue -- every GOOD row rolls
   back with the one bad one instead of quarantining it. Wrapping provisioning in
   ``row_savepoint()`` isolates the failure.

2. ``_apply_bundle_inner`` now claims the bundle under ``select_for_update`` +
   ``transaction.atomic`` so two concurrent applies cannot both flip
   MAPPED->APPLYING. The row-lock race is Postgres-only (SQLite has no row-level
   locking, so select_for_update is a documented no-op there); these tests lock
   the CLAIM-GUARD behavior the refactor must preserve.
"""

from __future__ import annotations

from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import User
from apps.migration_cloud import orchestrator
from apps.migration_cloud.landers._helpers import resolve_or_provision_user
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationBundle,
)
from apps.schools.models import School


class ProvisioningSavepointTests(TestCase):
    def test_provisioning_failure_isolated_by_savepoint(self):
        # A user already owns the username create_user will collide on.
        User.objects.create_user(username="taken", email="existing@example.com")

        with transaction.atomic():  # simulate the forced-atomic finance apply
            with mock.patch(
                "apps.migration_cloud.landers._helpers._free_username",
                return_value="taken",
            ):
                with self.assertRaises(IntegrityError):
                    resolve_or_provision_user(
                        User=User, username_hint="", email="new@example.com",
                        first_name="New", last_name="Person", role="", dry_run=False,
                    )
            # The savepoint rolled back ONLY the failed provisioning; the outer
            # transaction is NOT poisoned, so a real query still works. Pre-fix
            # (no savepoint) this raises TransactionManagementError.
            self.assertEqual(User.objects.filter(username="taken").count(), 1)

    def test_normal_provisioning_still_works(self):
        user, reason = resolve_or_provision_user(
            User=User, username_hint="", email="teacher@example.com",
            first_name="Grace", last_name="Hopper", role="", dry_run=False,
        )
        self.assertEqual(reason, "")
        self.assertIsNotNone(user)
        self.assertEqual(user.email, "teacher@example.com")
        self.assertFalse(user.has_usable_password())


class ApplyClaimGuardTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Claim", slug="claim-seal", subdomain="claim-seal",
            is_active=True, country_code="CM",
        )

    def _bundle(self, status):
        return MigrationBundle.objects.create(
            label="claim", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"claim-{status}", status=status, school=self.school,
        )

    def test_claim_noops_on_already_applied(self):
        bundle = self._bundle(BundleStatus.APPLIED)
        result = orchestrator._apply_bundle_inner(bundle_id=bundle.pk, dry_run=False)
        bundle.refresh_from_db()
        self.assertEqual(bundle.status, BundleStatus.APPLIED)
        self.assertEqual(result.total_created, 0)

    def test_claim_raises_on_non_mapped(self):
        bundle = self._bundle(BundleStatus.PROFILED)
        with self.assertRaises(ValueError):
            orchestrator._apply_bundle_inner(bundle_id=bundle.pk, dry_run=False)
        bundle.refresh_from_db()
        # Status is untouched by the refused apply.
        self.assertEqual(bundle.status, BundleStatus.PROFILED)
