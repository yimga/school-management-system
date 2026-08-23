"""A rolled-back package must be re-installable for the same tenant and version.

``rollback()`` is a SOFT deactivate: it flips ``is_active``/``apply_stage``/
``reconciliation_status`` on the existing ``InstalledPackage`` row and leaves it in
place (engine.py, ``rollback``). But ``InstalledPackage`` carries
``unique_together = [["package_id", "version", "school"]]``, and ``apply_package``
issued an unconditional ``objects.create(...)``. So the second apply of the same
version to the same tenant raised ``IntegrityError`` -- caught by
``_PACKAGE_APPLY_FAILURE_ERRORS`` and returned as a generic ``ok: False``, with no
hint that the cause was the tenant's own rolled-back row.

The tenant is then permanently stuck: the only recorded install of that version is
inactive, and no re-apply can ever succeed. Rolling forward to a new version number
is not a workaround -- the operator wants the version they rolled back FROM.

Note the school must be real. ``school`` is nullable and NULL != NULL under SQL
uniqueness, so a platform-scope install (``tenant_id=None``) silently side-steps the
constraint and merely accumulates duplicate rows -- which is why this went unnoticed.
"""

import uuid

from django.test import TestCase

from apps.packages.engine import apply_package, rollback
from apps.packages.models import InstalledPackage
from apps.schools.models import School


class ReinstallAfterRollbackTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Reinstall School",
            slug=f"reinst-{uuid.uuid4().hex[:8]}",
            subdomain=f"reinst-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )

    def _apply(self):
        return apply_package(
            tenant_id=self.school.pk,
            package_id="ci-reinstall-pack",
            version="1.0",
            payload_sections={"policy": {"entity_codes": ["student"]}},
            mode="production",
            actor_id=None,
        )

    def test_reapply_after_rollback_succeeds_and_reactivates(self):
        first = self._apply()
        self.assertTrue(first["ok"], first)

        inst = InstalledPackage.objects.get(pk=first["installed_id"])
        self.assertTrue(rollback(inst, actor_id=None)["ok"])
        inst.refresh_from_db()
        self.assertFalse(inst.is_active)

        second = self._apply()
        self.assertTrue(
            second["ok"],
            "re-applying a rolled-back package must succeed; the tenant's own "
            f"inactive row is not a reason to refuse. Got: {second}",
        )
        self.assertEqual(second.get("apply_state"), "committed")

        # One install row per (package, version, tenant) -- the constraint's shape.
        rows = InstalledPackage.objects.filter(
            school=self.school, package_id="ci-reinstall-pack", version="1.0"
        )
        self.assertEqual(rows.count(), 1, "re-apply must reuse the row, not duplicate it")

        live = rows.get()
        self.assertTrue(live.is_active, "re-apply must clear the rolled-back state")
        self.assertEqual(live.apply_stage, "production")
        self.assertEqual(live.reconciliation_status, "reconciled")
        self.assertEqual(
            live.rollback_token,
            second["rollback_token"],
            "the row must carry the NEW rollback token, or the caller cannot roll "
            "back the install it just made",
        )

    def test_reapply_at_a_different_stage_does_not_collide(self):
        # scope/apply_stage are not part of the unique key, so a sandbox install
        # followed by a production install of the same version is the same clash.
        sandbox = apply_package(
            tenant_id=self.school.pk,
            package_id="ci-stage-pack",
            version="2.0",
            payload_sections={"policy": {}},
            mode="sandbox",
            actor_id=None,
        )
        self.assertTrue(sandbox["ok"], sandbox)

        prod = apply_package(
            tenant_id=self.school.pk,
            package_id="ci-stage-pack",
            version="2.0",
            payload_sections={"policy": {}},
            mode="production",
            actor_id=None,
        )
        self.assertTrue(prod["ok"], f"sandbox install must not block production: {prod}")
        live = InstalledPackage.objects.get(
            school=self.school, package_id="ci-stage-pack", version="2.0"
        )
        self.assertEqual(live.apply_stage, "production")
        self.assertEqual(live.scope, "tenant")
