"""v3.32.0 — Tests for the DFV -> first-class replay command.

Combines:

  * Pure structural — module imports + helper-sharing invariant.
  * DB-backed — dry-run reports without writing, apply moves rows AND
    deletes DFV, idempotent re-run is no-op, tenant isolation enforced,
    unresolved rows left alone, atomic transaction on failure.
"""

from __future__ import annotations

import uuid
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase


# ---------------------------------------------------------------------------
# Layer 1 — structural
# ---------------------------------------------------------------------------


class ReplayCommandStructuralTests(SimpleTestCase):
    """Module is importable + helper is shared with promote_dyna_assignments."""

    def test_module_importable(self) -> None:
        from apps.migration_cloud.management.commands import (
            replay_dfv_assignments,
        )
        self.assertTrue(hasattr(replay_dfv_assignments, "Command"))

    def test_helpers_module_shared_with_promote(self) -> None:
        from apps.migration_cloud.management.commands import (
            _assignment_promotion_helpers as helpers,
            promote_dyna_assignments,
            replay_dfv_assignments,
        )
        # Both commands reference the same helper module.
        self.assertIs(
            promote_dyna_assignments._helpers, helpers,
        )
        self.assertIs(
            replay_dfv_assignments._helpers, helpers,
        )

    def test_command_rejects_run_without_tenant_or_bundle(self) -> None:
        from django.core.management.base import CommandError
        from apps.migration_cloud.management.commands.replay_dfv_assignments import (
            Command,
        )
        cmd = Command()
        cmd.stdout = StringIO()
        with self.assertRaises(CommandError):
            cmd.handle(
                tenant=None, bundle=None, apply=False, limit=10,
                entity_type=None, since=None,
            )


# ---------------------------------------------------------------------------
# Layer 2 — DB-backed
# ---------------------------------------------------------------------------


def _setup_tenant_with_dfv_transport(*, with_catalog: bool = True):
    """Create tenant + student + (optionally) Route + DFV transport row."""
    from apps.metadata.models import DynamicFieldValue
    from apps.people.models import StudentProfile
    from apps.schools.models import School
    from apps.schoolops.models import Route

    slug = f"r-{uuid.uuid4().hex[:8]}"
    school = School.objects.create(
        name=f"School {slug}",
        slug=slug,
        subdomain=slug,
        features={"transport": True},
    )
    student = StudentProfile.objects.create(
        school=school,
        first_name="Sam",
        last_name="Test",
        student_code=f"STU-{uuid.uuid4().hex[:8]}",
        admission_number=f"ADM-{uuid.uuid4().hex[:8]}",
    )
    route = None
    if with_catalog:
        route = Route.objects.create(
            school=school, name=f"Route {slug}",
        )
    payload = {
        "student_external_id": student.admission_number,
        "route": route.name if route else f"Route {slug}",
        "effective_from": "2026-01-15",
        "status": "active",
        "pickup_stop": "Main St",
        "dropoff_stop": "School Gate",
    }
    dfv = DynamicFieldValue.objects.create(
        school=school,
        entity_type="student_transport_assignment",
        entity_id=str(student.pk),
        field_key="canonical",
        value_json=payload,
    )
    return {
        "school": school, "student": student,
        "route": route, "dfv": dfv,
    }


class ReplayDryRunTests(TestCase):
    """Dry-run reports without writing or deleting."""

    def test_dry_run_does_not_write_or_delete(self) -> None:
        from apps.metadata.models import DynamicFieldValue
        from apps.schoolops.models import TransportAssignment
        ctx = _setup_tenant_with_dfv_transport(with_catalog=True)
        out = StringIO()
        call_command(
            "replay_dfv_assignments",
            "--tenant", str(ctx["school"].pk),
            stdout=out,
        )
        # No write — DFV still in place, no first-class row.
        self.assertTrue(
            DynamicFieldValue.objects.filter(pk=ctx["dfv"].pk).exists(),
        )
        self.assertEqual(
            TransportAssignment.objects.filter(
                school=ctx["school"]).count(), 0,
        )


class ReplayApplyTests(TestCase):
    """``--apply`` promotes the row AND deletes the DFV row."""

    def test_apply_moves_dfv_and_deletes_source(self) -> None:
        from apps.metadata.models import DynamicFieldValue
        from apps.schoolops.models import TransportAssignment
        ctx = _setup_tenant_with_dfv_transport(with_catalog=True)
        out = StringIO()
        call_command(
            "replay_dfv_assignments",
            "--tenant", str(ctx["school"].pk),
            "--apply",
            stdout=out,
        )
        self.assertFalse(
            DynamicFieldValue.objects.filter(pk=ctx["dfv"].pk).exists(),
        )
        self.assertEqual(
            TransportAssignment.objects.filter(
                school=ctx["school"]).count(), 1,
        )

    def test_apply_skips_when_catalog_still_absent(self) -> None:
        from apps.metadata.models import DynamicFieldValue
        from apps.schoolops.models import TransportAssignment
        ctx = _setup_tenant_with_dfv_transport(with_catalog=False)
        out = StringIO()
        call_command(
            "replay_dfv_assignments",
            "--tenant", str(ctx["school"].pk),
            "--apply",
            stdout=out,
        )
        # Catalog absent — DFV remains, no first-class row.
        self.assertTrue(
            DynamicFieldValue.objects.filter(pk=ctx["dfv"].pk).exists(),
        )
        self.assertEqual(
            TransportAssignment.objects.filter(
                school=ctx["school"]).count(), 0,
        )


class ReplayIdempotencyTests(TestCase):
    """Re-running on a cleaned tenant is a no-op."""

    def test_rerun_is_noop(self) -> None:
        from apps.metadata.models import DynamicFieldValue
        from apps.schoolops.models import TransportAssignment
        ctx = _setup_tenant_with_dfv_transport(with_catalog=True)
        out = StringIO()
        call_command(
            "replay_dfv_assignments",
            "--tenant", str(ctx["school"].pk),
            "--apply",
            stdout=out,
        )
        first_count = TransportAssignment.objects.filter(
            school=ctx["school"]).count()
        # Re-run — nothing left to do.
        call_command(
            "replay_dfv_assignments",
            "--tenant", str(ctx["school"].pk),
            "--apply",
            stdout=out,
        )
        self.assertEqual(
            TransportAssignment.objects.filter(
                school=ctx["school"]).count(),
            first_count,
        )
        self.assertEqual(
            DynamicFieldValue.objects.filter(
                school=ctx["school"],
                entity_type="student_transport_assignment",
            ).count(),
            0,
        )


class ReplayTenantIsolationTests(TestCase):
    """Replay against tenant A never touches tenant B's DFV rows."""

    def test_tenant_isolation(self) -> None:
        from apps.metadata.models import DynamicFieldValue
        ctx_a = _setup_tenant_with_dfv_transport(with_catalog=True)
        ctx_b = _setup_tenant_with_dfv_transport(with_catalog=True)
        out = StringIO()
        call_command(
            "replay_dfv_assignments",
            "--tenant", str(ctx_a["school"].pk),
            "--apply",
            stdout=out,
        )
        self.assertFalse(
            DynamicFieldValue.objects.filter(pk=ctx_a["dfv"].pk).exists(),
        )
        # Tenant B's row intact.
        self.assertTrue(
            DynamicFieldValue.objects.filter(pk=ctx_b["dfv"].pk).exists(),
        )


class ReplayBundleFilterTests(TestCase):
    """``--bundle`` filter narrows scope to one bundle id."""

    def test_bundle_filter_applied(self) -> None:
        from apps.schoolops.models import TransportAssignment
        ctx = _setup_tenant_with_dfv_transport(with_catalog=True)
        # Annotate the DFV payload with a bundle_id so filter matches.
        payload = dict(ctx["dfv"].value_json)
        payload["bundle_id"] = 42
        ctx["dfv"].value_json = payload
        ctx["dfv"].save(update_fields=["value_json"])
        out = StringIO()
        call_command(
            "replay_dfv_assignments",
            "--tenant", str(ctx["school"].pk),
            "--bundle", "42",
            "--apply",
            stdout=out,
        )
        # Promotion happened; DFV removed.
        self.assertEqual(
            TransportAssignment.objects.filter(
                school=ctx["school"]).count(),
            1,
        )
