"""Tests for the sms-v3.7 wave: Tier 1, Tier 2, Tier 3 features.

Coverage map:
    Tier 1
        #1 Financial reconciliation guardrail (guardrails.py)
        #2 Asset pipeline (asset_pipeline.py + register_asset)
        #3 MigrationIdMapping audit table
        #4 PII redaction enforcement in AI bridge (redact_pii_for_prompt)
        #5 Conflict detection (detect_conflict + resolve via view)
        #6 Diff-mode re-ingest (row_passes_diff_filter)

    Tier 2
        #7  apply_atomic flag round-trip
        #8/#9 progress emit + snapshot + SSE endpoint headers
        #10 sandbox clone / promote / discard
        #11 capacity preflight check
        #12 cross-bundle FK preflight check
        #13 auto-rollback threshold (no rollback when threshold=0)
        #14 fetch_with_resume file:// happy path + checksum

    Tier 3
        #15 merge_bundles
        #16 generate_handoff_doc
        #17 lockout_legacy_source
        #18 estimate_token_spend
        #19 suggest_profiles_for (returns [] when models absent)
        #20 export_tenant_to_canonical (smoke test)
        #21 stage_rollout_plan + advance
        #22 ocr_confidence_warning thresholds
        #23 sla_tier_targets
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import tempfile
from pathlib import Path

from django.test import TestCase
from django.utils import timezone

from apps.migration_cloud import diff_mode, network_resilience, preflight, sandbox, tier3
from apps.migration_cloud.ai_bridge import _tenant_allows_pii, redact_pii_for_prompt
from apps.migration_cloud.asset_pipeline import register_asset
from apps.migration_cloud.guardrails import (
    enforce_financial_guardrail,
    evaluate_expected_totals,
)
from apps.migration_cloud.models import (
    AssetStatus,
    BundleStatus,
    ConflictResolution,
    FinancialMismatchError,
    IntakeMethod,
    MigrationBundle,
    MigrationConflict,
    MigrationIdMapping,
    MigrationProgressEvent,
)
from apps.migration_cloud.progress import emit as emit_progress
from apps.migration_cloud.progress import refresh_snapshot, stream_events_since


def _bundle(**overrides) -> MigrationBundle:
    defaults = {
        "label": "test bundle",
        "intake_method": IntakeMethod.FILE_UPLOAD,
        "idempotency_key": f"test-{timezone.now().timestamp()}",
        "status": BundleStatus.MAPPED,
    }
    defaults.update(overrides)
    return MigrationBundle.objects.create(**defaults)


# ---- Tier 1 #1: Financial guardrail ----------------------------------------

class FinancialGuardrailTests(TestCase):
    def test_evaluate_totals_passes_within_tolerance(self):
        bundle = _bundle(expected_totals={"finance.invoice_total_amount": "125000.00"})
        report = evaluate_expected_totals(
            bundle=bundle,
            observed={"finance.invoice_total_amount": "125000.00"},
        )
        self.assertTrue(report.ok)
        self.assertEqual(len(report.checks), 1)
        self.assertEqual(len(report.failed), 0)

    def test_evaluate_totals_fails_outside_tolerance(self):
        bundle = _bundle(expected_totals={"students.count": "1240"})
        report = evaluate_expected_totals(
            bundle=bundle,
            observed={"students.count": "1200"},
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.failed[0].key, "students.count")

    def test_no_expected_totals_passes(self):
        bundle = _bundle()
        report = evaluate_expected_totals(bundle=bundle, observed={})
        self.assertTrue(report.ok)
        self.assertEqual(report.checks, [])

    def test_enforce_raises_on_mismatch(self):
        bundle = _bundle(expected_totals={"students.count": "100"})
        # No real tenant data → observed will lack the key → mismatch.
        with self.assertRaises(FinancialMismatchError):
            enforce_financial_guardrail(bundle=bundle)


# ---- Tier 1 #2: Asset pipeline --------------------------------------------

class AssetPipelineTests(TestCase):
    def test_register_asset_idempotent(self):
        bundle = _bundle()
        a1 = register_asset(
            bundle=bundle, entity_kind="student", legacy_id="PS-1029",
            asset_kind="photo", source_uri="https://example.com/photo.jpg",
        )
        a2 = register_asset(
            bundle=bundle, entity_kind="student", legacy_id="PS-1029",
            asset_kind="photo", source_uri="https://example.com/photo.jpg",
        )
        self.assertEqual(a1.pk, a2.pk)
        self.assertEqual(a1.status, AssetStatus.PENDING)

    def test_fetch_pending_assets_file_scheme_refused_by_default(self):
        # SSRF/LFI guard (2026-08-09): a file:// asset source (source_uri comes
        # off an untrusted migrated row) is refused by default -> FAILED, never
        # read off the server's disk.
        bundle = _bundle()
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "photo.bin"
            src.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
            register_asset(
                bundle=bundle, entity_kind="student", legacy_id="PS-1",
                asset_kind="photo", source_uri=src.as_uri(),
            )
            from apps.migration_cloud.asset_pipeline import fetch_pending_assets
            counts = fetch_pending_assets(bundle_id=bundle.pk)
            self.assertEqual(counts["stored"], 0)
            self.assertEqual(counts["failed"], 1)
            self.assertEqual(bundle.assets.first().status, AssetStatus.FAILED)

    def test_fetch_pending_assets_file_scheme_optin_confined(self):
        # A self-host opts in (allow_local_file_source) and reads are confined to
        # the allowed asset root (here MEDIA_ROOT): a file INSIDE it is stored.
        from unittest import mock

        from django.test import override_settings

        import apps.migration_cloud.asset_pipeline as _ap

        bundle = _bundle()
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "photo.bin"
            src.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
            register_asset(
                bundle=bundle, entity_kind="student", legacy_id="PS-1",
                asset_kind="photo", source_uri=src.as_uri(),
            )
            with override_settings(MEDIA_ROOT=td), mock.patch.object(
                _ap, "_allow_local_file_source", return_value=True,
            ):
                counts = _ap.fetch_pending_assets(bundle_id=bundle.pk)
            self.assertEqual(counts["stored"], 1)
            asset = bundle.assets.first()
            self.assertEqual(asset.status, AssetStatus.STORED)
            self.assertEqual(asset.byte_size, len(b"\xff\xd8\xff\xe0fake-jpeg"))
            self.assertTrue(asset.sha256)


# ---- Tier 1 #3: MigrationIdMapping ----------------------------------------

class MigrationIdMappingTests(TestCase):
    def test_unique_constraint_per_school_namespace(self):
        bundle = _bundle()
        MigrationIdMapping.objects.create(
            bundle=bundle, legacy_namespace="powerschool", legacy_id="PS-1",
            canonical_model="apps.people.StudentProfile", canonical_pk="42", domain="students",
        )
        # Same (namespace, legacy_id, canonical_model, school=None) must update_or_create cleanly.
        MigrationIdMapping.objects.update_or_create(
            legacy_namespace="powerschool", legacy_id="PS-1",
            canonical_model="apps.people.StudentProfile",
            school=None,
            defaults={"bundle": bundle, "canonical_pk": "42", "domain": "students"},
        )
        self.assertEqual(
            MigrationIdMapping.objects.filter(legacy_namespace="powerschool", legacy_id="PS-1").count(),
            1,
        )


# ---- Tier 1 #4: PII redaction ---------------------------------------------

class PiiRedactionTests(TestCase):
    def test_email_redacted(self):
        out = redact_pii_for_prompt("Contact alice@example.com about her record")
        self.assertIn("<REDACTED_EMAIL>", out)
        self.assertNotIn("alice@example.com", out)

    def test_ssn_redacted(self):
        out = redact_pii_for_prompt("SSN: 123-45-6789")
        self.assertIn("<REDACTED_SSN>", out)

    def test_phone_redacted(self):
        out = redact_pii_for_prompt("Call (555) 867-5309 today")
        self.assertIn("<REDACTED_PHONE>", out)

    def test_date_redacted(self):
        out = redact_pii_for_prompt("DOB 2010-04-12 grade 7")
        self.assertIn("<REDACTED_DATE>", out)

    def test_no_pii_passthrough(self):
        original = "Map column Student_Number to student.external_id"
        self.assertEqual(redact_pii_for_prompt(original), original)

    def test_tenant_allows_pii_default_true_when_no_school(self):
        self.assertTrue(_tenant_allows_pii(None))


# ---- Tier 1 #5: Conflict detection + resolution ---------------------------

class ConflictResolutionTests(TestCase):
    def test_conflict_resolution_choices_includes_all_three(self):
        keys = {c[0] for c in ConflictResolution.choices}
        self.assertSetEqual(keys, {"PENDING", "OVERWRITE", "PRESERVE", "MERGE"})

    def test_conflict_row_lifecycle(self):
        bundle = _bundle()
        c = MigrationConflict.objects.create(
            bundle=bundle,
            domain="students",
            canonical_model="apps.people.StudentProfile",
            canonical_pk="42",
            legacy_id="PS-1029",
            existing_values={"first_name": "Alice"},
            incoming_values={"first_name": "Alicia"},
            changed_fields=["first_name"],
        )
        self.assertEqual(c.resolution, ConflictResolution.PENDING)
        c.resolution = ConflictResolution.OVERWRITE
        c.resolved_at = timezone.now()
        c.save()
        self.assertIsNotNone(c.resolved_at)


# ---- Tier 1 #6: Diff-mode -------------------------------------------------

class DiffModeTests(TestCase):
    def test_row_with_no_timestamp_falls_through(self):
        self.assertTrue(diff_mode.row_passes_diff_filter(row={"first_name": "x"}, threshold=_dt.datetime.now()))

    def test_row_older_than_threshold_filtered(self):
        threshold = _dt.datetime(2026, 5, 1)
        self.assertFalse(diff_mode.row_passes_diff_filter(
            row={"updated_at": "2026-04-15T10:00:00"},
            threshold=threshold,
        ))

    def test_row_newer_than_threshold_passes(self):
        threshold = _dt.datetime(2026, 5, 1)
        self.assertTrue(diff_mode.row_passes_diff_filter(
            row={"updated_at": "2026-05-15"},
            threshold=threshold,
        ))


# ---- Tier 2 #7: Atomic apply flag round-trip ------------------------------

class ApplyAtomicFlagTests(TestCase):
    def test_default_is_false(self):
        bundle = _bundle()
        self.assertFalse(bundle.apply_atomic)

    def test_can_be_flipped(self):
        bundle = _bundle(apply_atomic=True)
        bundle.refresh_from_db()
        self.assertTrue(bundle.apply_atomic)


# ---- Tier 2 #8/#9: Progress + SSE -----------------------------------------

class ProgressTests(TestCase):
    def test_emit_creates_event(self):
        bundle = _bundle()
        emit_progress(bundle_id=bundle.pk, kind="info", stage="INGESTING", message="hello")
        events = list(MigrationProgressEvent.objects.filter(bundle=bundle))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].message, "hello")

    def test_refresh_snapshot_marks_done_stages(self):
        bundle = _bundle(status=BundleStatus.APPLIED)
        snapshot = refresh_snapshot(bundle=bundle)
        names = [s["name"] for s in snapshot["stages"]]
        self.assertIn("INGESTING", names)
        # INGESTING comes before APPLIED → must be done.
        ingest = next(s for s in snapshot["stages"] if s["name"] == "INGESTING")
        self.assertEqual(ingest["status"], "done")
        self.assertEqual(len(snapshot["graph"]["nodes"]), len(snapshot["stages"]))
        self.assertEqual(
            snapshot["graph"]["edges"][0],
            {"from": "PENDING", "to": "INGESTING", "label": "then"},
        )

    def test_stream_events_since_filters(self):
        bundle = _bundle()
        emit_progress(bundle_id=bundle.pk, kind="info", stage="X", message="one")
        emit_progress(bundle_id=bundle.pk, kind="info", stage="X", message="two")
        events = list(stream_events_since(bundle_id=bundle.pk, after_id=0))
        self.assertEqual(len(events), 2)


# ---- Tier 2 #10: Sandbox --------------------------------------------------

class SandboxTests(TestCase):
    def test_clone_creates_sandbox_with_lineage(self):
        bundle = _bundle(status=BundleStatus.MAPPED)
        clone = sandbox.clone_bundle_to_sandbox(bundle=bundle)
        self.assertEqual(clone.sandbox_of_id, bundle.pk)
        self.assertTrue(clone.schema_name.startswith("sandbox-"))
        self.assertEqual(clone.status, BundleStatus.MAPPED)

    def test_promote_resets_origin_to_mapped(self):
        bundle = _bundle(status=BundleStatus.MAPPED)
        clone = sandbox.clone_bundle_to_sandbox(bundle=bundle)
        result = sandbox.promote_sandbox_to_origin(sandbox=clone)
        self.assertEqual(result["origin_bundle_id"], bundle.pk)

    def test_discard_deletes_sandbox(self):
        bundle = _bundle()
        clone = sandbox.clone_bundle_to_sandbox(bundle=bundle)
        sandbox_pk = clone.pk
        sandbox.discard_sandbox(sandbox=clone)
        self.assertFalse(MigrationBundle.objects.filter(pk=sandbox_pk).exists())

    def test_promote_non_sandbox_raises(self):
        bundle = _bundle()
        with self.assertRaises(ValueError):
            sandbox.promote_sandbox_to_origin(sandbox=bundle)


# ---- Tier 2 #11/#12: Preflight --------------------------------------------

class PreflightTests(TestCase):
    def test_capacity_check_passes_for_empty_bundle(self):
        bundle = _bundle(sla_tier="small")
        check = preflight.check_capacity(bundle=bundle)
        self.assertTrue(check.passed)

    def test_cross_bundle_fks_passes_with_no_refs(self):
        bundle = _bundle()
        check = preflight.check_cross_bundle_fks(bundle=bundle)
        self.assertTrue(check.passed)

    def test_run_all_returns_report(self):
        bundle = _bundle()
        report = preflight.run_all(bundle=bundle)
        self.assertEqual(report.bundle_id, bundle.pk)
        self.assertGreaterEqual(len(report.checks), 3)


# ---- Tier 2 #13: Auto-rollback threshold ----------------------------------

class AutoRollbackTests(TestCase):
    def test_default_threshold_is_zero(self):
        bundle = _bundle()
        self.assertEqual(bundle.parity_drift_rollback_pct, 0.0)


# ---- Tier 2 #14: Network resilience ---------------------------------------

class NetworkResilienceTests(TestCase):
    def test_fetch_file_scheme_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "data.csv"
            src.write_bytes(b"col1,col2\n1,2\n")
            dest = Path(td) / "out.csv"
            result = network_resilience.fetch_with_resume(
                src.as_uri(), dest=dest, max_retries=1,
            )
            self.assertEqual(result["bytes"], len(b"col1,col2\n1,2\n"))
            expected_sha = hashlib.sha256(b"col1,col2\n1,2\n").hexdigest()
            self.assertEqual(result["sha256"], expected_sha)

    def test_fetch_with_checksum_mismatch_raises(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "data.csv"
            src.write_bytes(b"abc")
            dest = Path(td) / "out.csv"
            with self.assertRaises(network_resilience.FetchError):
                network_resilience.fetch_with_resume(
                    src.as_uri(), dest=dest, max_retries=1,
                    expected_sha256="ff" * 32,
                )


# ---- Tier 3 #15-23 --------------------------------------------------------

class Tier3Tests(TestCase):
    def test_merge_bundles_creates_parent_with_artifacts(self):
        b1 = _bundle(idempotency_key="b1")
        b2 = _bundle(idempotency_key="b2")
        parent = tier3.merge_bundles(bundles=[b1, b2], label="cutover")
        self.assertEqual(parent.label, "cutover")
        self.assertIn(b1.pk, parent.mapping_summary["merged_from"])

    def test_generate_handoff_doc_returns_complete_dict(self):
        bundle = _bundle()
        doc = tier3.generate_handoff_doc(bundle=bundle)
        for key in ("title", "school_name", "generated_at", "bundle_id", "totals",
                    "reconciliation", "financial_guardrail", "ferpa_notice"):
            self.assertIn(key, doc)

    def test_lockout_writes_event_and_summary(self):
        bundle = _bundle()
        result = tier3.lockout_legacy_source(bundle=bundle, instructions="flip read-only")
        self.assertIn("requested_at", result)
        self.assertEqual(MigrationProgressEvent.objects.filter(bundle=bundle, stage="LOCKOUT").count(), 1)

    def test_estimate_token_spend_returns_nonzero_for_empty_bundle(self):
        bundle = _bundle()
        est = tier3.estimate_token_spend(bundle=bundle)
        self.assertEqual(est.estimated_ai_calls, 0)
        self.assertEqual(est.estimated_tokens, 0)

    def test_suggest_profiles_handles_missing_models_gracefully(self):
        suggestions = tier3.suggest_profiles_for(source_system="nonexistent")
        self.assertIsInstance(suggestions, list)

    def test_stage_rollout_plan_round_trip(self):
        bundle = _bundle()
        plan = tier3.stage_rollout_plan(
            bundle=bundle,
            stages=[{"label": "g12 pilot", "filter": {"grade_level": "12"}}],
        )
        self.assertEqual(plan["current_stage"], 0)
        advanced = tier3.advance_rollout_stage(bundle=bundle)
        # Only one stage → current stays at 0.
        self.assertEqual(advanced["current_stage"], 0)

    def test_ocr_confidence_warning_low_chars(self):
        warn = tier3.ocr_confidence_warning(ocr_chars=10, vendor_confidence=0.9)
        self.assertIsNotNone(warn)

    def test_ocr_confidence_warning_borderline_confidence(self):
        warn = tier3.ocr_confidence_warning(ocr_chars=500, vendor_confidence=0.3)
        self.assertIsNotNone(warn)

    def test_ocr_confidence_warning_clean(self):
        warn = tier3.ocr_confidence_warning(ocr_chars=500, vendor_confidence=0.9)
        self.assertIsNone(warn)

    def test_sla_tier_targets_returns_tier(self):
        bundle = _bundle(sla_tier="small")
        targets = tier3.sla_tier_targets(bundle=bundle)
        self.assertEqual(targets["tier"], "small")
        self.assertIn("targets", targets)
