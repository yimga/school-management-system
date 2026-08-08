"""Field-level apply audit (2026-08-08).

Tier-1a made conflict-resolution DECISIONS tamper-evident. This extends the
field-level audit to the APPLY path: the ``migration.bundle.applied`` event now
carries a per-domain rollup — created / updated / quarantined counts AND the
NAMES of the fields overwritten on existing records — so there is a tamper-
evident record of WHAT a re-apply actually mutated, not just how many rows.

Discipline (mirrors Tier-1a): field NAMES ride as list VALUES, never dict keys,
so ``_sanitize_payload`` — which rejects sensitive-keyword dict KEYS like
``email`` / ``date_of_birth`` / ``ssn`` — accepts a legitimate field name; the
raw values never leave the tenant schema.

Each test fails against the pre-wave orchestrator (no ``domains`` field-level
rollup; the helper did not exist).
"""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.landers.base import LanderResult
from apps.migration_cloud.models_audit import (
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
    _sanitize_payload,
)
from apps.migration_cloud.orchestrator import (
    _APPLY_AUDIT_FIELD_CAP,
    ArtifactApplyOutcome,
    _field_level_apply_summary,
)
from apps.migration_cloud.services.bundle_lifecycle_audit import safe_bundle_audit
from apps.schools.models import School


def _outcome(domain, *, created=0, updated=0, quarantined=0, updated_olds=None):
    r = LanderResult(created=created, updated=updated, quarantined=quarantined)
    for old in updated_olds or []:
        r.updated_ids_with_old_values.append({"pk": 1, "old": old})
    return ArtifactApplyOutcome(
        artifact_id=1, path_within_bundle="a.csv", domain=domain,
        migration_run_id=None, result=r,
    )


class FieldLevelApplySummaryTests(TestCase):
    def test_rollup_aggregates_counts_and_field_names_per_domain(self):
        outcomes = [
            _outcome("students", created=2, updated=1,
                     updated_olds=[{"first_name": "A", "email": "x@y"}]),
            # A SECOND students artifact — counts + field names must aggregate.
            _outcome("students", updated=1,
                     updated_olds=[{"last_name": "B", "date_of_birth": "2011-01-01"}]),
            _outcome("finance", created=3, quarantined=1),
        ]
        by = {d["domain"]: d for d in _field_level_apply_summary(outcomes)}
        self.assertEqual(by["students"]["created"], 2)
        self.assertEqual(by["students"]["updated"], 2)  # 1 + 1 across artifacts
        self.assertEqual(
            by["students"]["updated_fields"],
            ["date_of_birth", "email", "first_name", "last_name"],  # sorted union
        )
        self.assertFalse(by["students"]["updated_fields_truncated"])
        self.assertEqual(by["finance"]["created"], 3)
        self.assertEqual(by["finance"]["quarantined"], 1)
        self.assertEqual(by["finance"]["updated_fields"], [])

    def test_field_name_list_is_capped_and_flagged(self):
        many = {f"field_{i}": i for i in range(_APPLY_AUDIT_FIELD_CAP + 5)}
        outcomes = [_outcome("students", updated=1, updated_olds=[many])]
        s = {d["domain"]: d for d in _field_level_apply_summary(outcomes)}["students"]
        self.assertEqual(len(s["updated_fields"]), _APPLY_AUDIT_FIELD_CAP)
        self.assertTrue(s["updated_fields_truncated"])


class ApplyAuditChainTests(TestCase):
    def test_field_names_ride_as_values_and_survive_the_chain(self):
        # date_of_birth / email / ssn are sensitive-KEY tokens; as the NAMES of
        # overwritten fields they must land on the append-only chain (as list
        # values), proving the field-name-as-value discipline end to end.
        outcomes = [
            _outcome("students", updated=1,
                     updated_olds=[{"email": "a@b", "date_of_birth": "2011", "ssn": "x"}]),
        ]
        payload = {
            "bundle_id": "1", "dry_run": False, "status": "applied",
            "created": 0, "updated": 1, "quarantined": 0,
            "domains": _field_level_apply_summary(outcomes),
        }
        # Must NOT raise — the whole payload is sanitize-clean.
        self.assertIs(_sanitize_payload(payload), payload)

        school = School.objects.create(name="AF", subdomain="af-apply-audit")
        bundle = type("B", (), {"pk": 77, "school": school})()
        before = MigrationCloudAuditEvent.objects.count()
        safe_bundle_audit(
            bundle, MigrationCloudAuditEventType.BUNDLE_APPLIED.value,
            payload_summary=payload,
        )
        self.assertEqual(MigrationCloudAuditEvent.objects.count(), before + 1)
        ev = MigrationCloudAuditEvent.objects.order_by("-created_at").first()
        self.assertEqual(ev.event_type, "migration.bundle.applied")
        dom = {d["domain"]: d for d in ev.payload_summary["domains"]}
        self.assertIn("email", dom["students"]["updated_fields"])
        self.assertIn("date_of_birth", dom["students"]["updated_fields"])
        self.assertIn("ssn", dom["students"]["updated_fields"])
        self.assertTrue(ev.integrity_hash)  # hash-chained

    def test_same_field_names_as_dict_keys_would_be_rejected(self):
        # Locks WHY the design puts field names in a list, not as keys: the same
        # tokens used as dict KEYS trip the sensitive-key rejection.
        with self.assertRaises(ValueError):
            _sanitize_payload({"domains": [{"email": 1, "date_of_birth": 2}]})
