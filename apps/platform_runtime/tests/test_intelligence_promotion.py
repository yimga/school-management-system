from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from apps.platform_runtime.intelligence_promotion import (
    evaluate_catalog,
    evaluate_promotion,
    load_catalog,
    sign_external_evidence_body,
    validate_catalog,
    verify_external_evidence,
)


def _evidence_body(
    feature_id: str,
    *,
    scope: str = "pilot",
    approved_stage: str | None = None,
    status: str = "passed",
    expires_delta: timedelta = timedelta(days=30),
) -> dict:
    catalog = load_catalog()
    now = datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "feature_id": feature_id,
        "approved_stage": approved_stage
        or {
            "repository": "repository_verified",
            "pilot": "internal_pilot",
            "production": "limited_production",
        }[scope],
        "evidence": [
            {
                "dimension": dimension,
                "scope": scope,
                "status": status,
                "source": f"evidence://{feature_id}/{dimension}",
                "verified_by": "operator@example.invalid",
                "observed_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + expires_delta).isoformat(),
            }
            for dimension in catalog["evidence_dimensions"]
        ],
    }


@override_settings(INTELLIGENCE_PROMOTION_SIGNING_KEY="promotion-test-key")
class IntelligencePromotionTests(SimpleTestCase):
    def test_catalog_is_complete_and_sources_exist(self):
        self.assertEqual(validate_catalog(), [])

    def test_repository_report_is_honest(self):
        report = evaluate_catalog(target_stage="repository_verified")
        self.assertEqual(report["eligible_count"], 9)
        self.assertEqual(report["blocked_count"], 0)
        blocked = {
            row["feature_id"] for row in report["decisions"] if not row["eligible"]
        }
        self.assertEqual(blocked, set())

    def test_browser_and_voice_cannot_skip_repository_stage(self):
        for feature_id in ("browser_slm", "voice_ai"):
            decision = evaluate_promotion(
                feature_id, target_stage="internal_pilot"
            )
            self.assertFalse(decision["eligible"])
            self.assertIn("exceeds catalog maximum", " ".join(decision["blockers"]))

    def test_repository_evidence_cannot_promote_to_pilot(self):
        decision = evaluate_promotion("marksheet_ocr", target_stage="internal_pilot")
        self.assertFalse(decision["eligible"])
        self.assertIn("below internal_pilot", " ".join(decision["blockers"]))

    def test_catalog_maximum_blocks_production(self):
        envelope = sign_external_evidence_body(
            _evidence_body("edge_ai", scope="production")
        )
        decision = evaluate_promotion(
            "edge_ai",
            target_stage="limited_production",
            external_evidence=envelope,
        )
        self.assertFalse(decision["eligible"])
        self.assertIn("exceeds catalog maximum", " ".join(decision["blockers"]))

    def test_signed_complete_pilot_evidence_promotes_to_pilot(self):
        envelope = sign_external_evidence_body(_evidence_body("edge_ai"))
        decision = evaluate_promotion(
            "edge_ai",
            target_stage="internal_pilot",
            external_evidence=envelope,
        )
        self.assertTrue(decision["eligible"], decision["blockers"])

    def test_tampering_invalidates_external_evidence(self):
        envelope = sign_external_evidence_body(_evidence_body("edge_ai"))
        envelope["body"]["evidence"][0]["source"] = "evidence://tampered"
        _rows, errors = verify_external_evidence(
            envelope,
            feature_id="edge_ai",
            target_stage="internal_pilot",
            allowed_dimensions=set(load_catalog()["evidence_dimensions"]),
        )
        self.assertTrue(any("checksum" in error for error in errors))

    def test_expired_evidence_is_rejected(self):
        envelope = sign_external_evidence_body(
            _evidence_body("edge_ai", expires_delta=timedelta(days=-1))
        )
        decision = evaluate_promotion(
            "edge_ai",
            target_stage="internal_pilot",
            external_evidence=envelope,
        )
        self.assertFalse(decision["eligible"])
        self.assertIn("expired", " ".join(decision["blockers"]))

    def test_feature_mismatch_is_rejected(self):
        envelope = sign_external_evidence_body(_evidence_body("marksheet_ocr"))
        decision = evaluate_promotion(
            "edge_ai",
            target_stage="internal_pilot",
            external_evidence=envelope,
        )
        self.assertFalse(decision["eligible"])
        self.assertIn("feature_id mismatch", " ".join(decision["blockers"]))

    def test_limited_production_approval_cannot_promote_to_ga(self):
        body = _evidence_body(
            "governed_ai_gateway",
            scope="production",
            approved_stage="limited_production",
        )
        decision = evaluate_promotion(
            "governed_ai_gateway",
            target_stage="general_availability",
            external_evidence=sign_external_evidence_body(body),
        )
        self.assertFalse(decision["eligible"])
        self.assertIn(
            "approved only through limited_production",
            " ".join(decision["blockers"]),
        )

    def test_ga_approval_can_promote_to_ga(self):
        body = _evidence_body(
            "governed_ai_gateway",
            scope="production",
            approved_stage="general_availability",
        )
        decision = evaluate_promotion(
            "governed_ai_gateway",
            target_stage="general_availability",
            external_evidence=sign_external_evidence_body(body),
        )
        self.assertTrue(decision["eligible"], decision["blockers"])

    def test_failed_external_dimension_blocks(self):
        body = _evidence_body("edge_ai")
        body["evidence"][0]["status"] = "failed"
        envelope = sign_external_evidence_body(body)
        decision = evaluate_promotion(
            "edge_ai",
            target_stage="internal_pilot",
            external_evidence=envelope,
        )
        self.assertFalse(decision["eligible"])
        self.assertIn("task_quality", " ".join(decision["blockers"]))

    def test_unknown_dimension_is_rejected(self):
        body = _evidence_body("edge_ai")
        body["evidence"][0]["dimension"] = "marketing_claim"
        envelope = sign_external_evidence_body(body)
        decision = evaluate_promotion(
            "edge_ai",
            target_stage="internal_pilot",
            external_evidence=envelope,
        )
        self.assertFalse(decision["eligible"])
        self.assertIn("unknown external evidence dimension", " ".join(decision["blockers"]))

    def test_timezone_naive_timestamp_is_rejected_without_raising(self):
        body = _evidence_body("edge_ai")
        body["evidence"][0]["observed_at"] = "2026-06-08T12:00:00"
        envelope = sign_external_evidence_body(body)
        decision = evaluate_promotion(
            "edge_ai",
            target_stage="internal_pilot",
            external_evidence=envelope,
        )
        self.assertFalse(decision["eligible"])
        self.assertIn("observed_at is invalid", " ".join(decision["blockers"]))

    def test_sign_command_and_verify_command_round_trip(self):
        body = _evidence_body("edge_ai")
        with tempfile.TemporaryDirectory() as tmp:
            body_path = Path(tmp) / "body.json"
            envelope_path = Path(tmp) / "envelope.json"
            body_path.write_text(json.dumps(body), encoding="utf-8")
            call_command(
                "sign_intelligence_evidence",
                "--body",
                str(body_path),
                "--output",
                str(envelope_path),
                stdout=StringIO(),
            )
            out = StringIO()
            call_command(
                "verify_intelligence_promotion",
                "--feature",
                "edge_ai",
                "--stage",
                "internal_pilot",
                "--evidence-file",
                str(envelope_path),
                "--strict",
                stdout=out,
            )
        self.assertTrue(json.loads(out.getvalue())["eligible"])

    def test_missing_signing_key_fails_closed(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with override_settings(INTELLIGENCE_PROMOTION_SIGNING_KEY=""):
                with self.assertRaises(ValueError):
                    sign_external_evidence_body(_evidence_body("edge_ai"))

    def test_sign_command_rejects_unknown_feature(self):
        body = _evidence_body("edge_ai")
        body["feature_id"] = "invented_feature"
        with tempfile.TemporaryDirectory() as tmp:
            body_path = Path(tmp) / "body.json"
            output_path = Path(tmp) / "signed.json"
            body_path.write_text(json.dumps(body), encoding="utf-8")
            from django.core.management.base import CommandError

            with self.assertRaises(CommandError):
                call_command(
                    "sign_intelligence_evidence",
                    "--body",
                    str(body_path),
                    "--output",
                    str(output_path),
                    stdout=StringIO(),
                )
