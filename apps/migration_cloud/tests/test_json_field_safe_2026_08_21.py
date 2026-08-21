"""JSONField-safe snapshots for migration apply audit (2026-08-21).

Landers snapshot FK fields via getattr(obj, "school") which returns a School
instance. Saving that raw into MigrationRun.rollback_snapshot raised
``TypeError: Object of type School is not JSON serializable`` and failed the
whole apply.
"""

from __future__ import annotations

import json

from django.test import TestCase

from apps.migration_cloud.landers._helpers import _jsonable, json_field_safe
from apps.migration_cloud.landers.base import LanderResult
from apps.migration_cloud.orchestrator import (
    ArtifactApplyOutcome,
    _finalize_audit_run,
    _json_safe,
)
from apps.schools.models import School


class JsonFieldSafeTests(TestCase):
    def test_jsonable_coerces_model_instances_to_pk(self):
        school = School.objects.create(name="JSON Safe School", slug="json-safe-school")
        self.assertEqual(_jsonable(school), str(school.pk))

    def test_json_field_safe_nested_school_in_old_snapshot(self):
        school = School.objects.create(name="Rollback School", slug="rollback-school")
        payload = {
            "updated_ids_with_old_values": [
                {"pk": 1, "old": {"school": school, "name": "Ada"}},
            ],
        }
        safe = json_field_safe(payload)
        json.dumps(safe)  # must not raise
        self.assertEqual(
            safe["updated_ids_with_old_values"][0]["old"]["school"], str(school.pk)
        )

    def test_finalize_audit_run_persists_rollback_snapshot_with_fk_old_values(self):
        school = School.objects.create(name="Audit Run School", slug="audit-run-school")
        try:
            from apps.automation.models import MigrationRun
        except ImportError:
            self.skipTest("automation app unavailable")

        run = MigrationRun.objects.create(
            school=school,
            migration_type="students:test.csv",
            dry_run=False,
        )
        result = LanderResult(created=1, updated=1)
        result.created_ids.append(99)
        result.updated_ids_with_old_values.append(
            {"pk": 42, "old": {"school": school, "first_name": "Before"}},
        )
        outcome = ArtifactApplyOutcome(
            artifact_id=1,
            path_within_bundle="test.csv",
            domain="students",
            migration_run_id=run.pk,
            result=result,
            status="SUCCESS",
        )
        _finalize_audit_run(run, outcome, status="SUCCESS")
        run.refresh_from_db()
        self.assertEqual(run.rollback_snapshot["created_ids"], [99])
        old = run.rollback_snapshot["updated_ids_with_old_values"][0]["old"]
        self.assertEqual(old["school"], str(school.pk))
        self.assertEqual(old["first_name"], "Before")
        json.dumps(run.rollback_snapshot)

    def test_orchestrator_json_safe_delegates_to_helper(self):
        school = School.objects.create(name="Delegate School", slug="delegate-school")
        out = _json_safe({"school": school})
        self.assertEqual(out["school"], str(school.pk))
