from __future__ import annotations

import json
from io import StringIO
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from services.edge_hardware import (
    GIB,
    EdgeHardwareProfile,
    classify_capability,
    model_admission,
    normalize_architecture,
    recommend_web_workers,
)
from services.edge_model_certification import (
    benchmark_model,
    catalog_model,
    sign_evidence,
    validate_model_catalog,
    verify_evidence,
    verify_evidence_checksum,
)


class EdgeHardwareProfileTests(SimpleTestCase):
    def test_normalizes_supported_architectures(self):
        self.assertEqual(normalize_architecture("AMD64"), "x86_64")
        self.assertEqual(normalize_architecture("aarch64"), "arm64")

    def test_capability_profiles_use_memory_and_storage(self):
        self.assertEqual(classify_capability(4 * GIB, 40 * GIB), "unsupported")
        self.assertEqual(
            classify_capability(8 * GIB, 12 * GIB), "constrained_pilot"
        )
        self.assertEqual(classify_capability(16 * GIB, 40 * GIB), "standard_edge")
        self.assertEqual(
            classify_capability(64 * GIB, 100 * GIB), "high_capacity_edge"
        )

    def test_worker_recommendation_is_bounded_and_memory_aware(self):
        self.assertEqual(recommend_web_workers(64, 8 * GIB), 2)
        self.assertEqual(recommend_web_workers(64, 128 * GIB), 8)
        self.assertEqual(recommend_web_workers(0.5, 32 * GIB), 1)

    def test_model_admission_rejects_wrong_architecture(self):
        profile = EdgeHardwareProfile(
            architecture="riscv64",
            capability_profile="standard_edge",
            logical_cpu_count=8,
            effective_cpu_count=8,
            cpu_limit_source="host",
            effective_memory_bytes=16 * GIB,
            memory_limit_source="host",
            storage_path=".",
            storage_free_bytes=40 * GIB,
            recommended_web_workers=4,
            recommendation_only=True,
            supports_edge_ai_pilot=False,
            warnings=(),
        )
        decision = model_admission(profile, catalog_model("qwen2.5:1.5b"))
        self.assertFalse(decision["admitted_for_pilot"])
        self.assertIn("architecture riscv64", decision["reasons"][0])


class EdgeModelCatalogTests(SimpleTestCase):
    def test_catalog_contract_is_complete(self):
        self.assertEqual(validate_model_catalog(), [])

    @override_settings(
        DEBUG=True,
        RUNNING_TESTS=True,
        SECRET_KEY="unit-test-edge-signing-key",
    )
    def test_evidence_signature_detects_tampering(self):
        envelope = sign_evidence({"schema_version": 1, "model": "candidate"})
        self.assertTrue(verify_evidence(envelope))
        self.assertTrue(verify_evidence_checksum(envelope))
        envelope["body"]["model"] = "tampered"
        self.assertFalse(verify_evidence(envelope))
        self.assertFalse(verify_evidence_checksum(envelope))

    @patch(
        "services.edge_model_certification.ollama_model_runtime",
        return_value={
            "model_id": "qwen2.5:1.5b",
            "digest": "sha256:abc",
            "artifact_size_bytes": 123,
        },
    )
    @patch(
        "services.edge_model_certification._invoke_once",
        return_value={"ok": True, "latency_ms": 25.0},
    )
    @patch("services.edge_model_certification.profile_edge_hardware")
    def test_benchmark_aggregates_concurrent_results(
        self, mock_profile, _mock_invoke, _mock_runtime
    ):
        mock_profile.return_value = EdgeHardwareProfile(
            architecture="x86_64",
            capability_profile="standard_edge",
            logical_cpu_count=8,
            effective_cpu_count=8,
            cpu_limit_source="host",
            effective_memory_bytes=16 * GIB,
            memory_limit_source="host",
            storage_path=".",
            storage_free_bytes=40 * GIB,
            recommended_web_workers=4,
            recommendation_only=True,
            supports_edge_ai_pilot=True,
            warnings=(),
        )
        result = benchmark_model("qwen2.5:1.5b", concurrency=2, runs=4)
        self.assertEqual(result["benchmark"]["successes"], 4)
        self.assertEqual(result["benchmark"]["latency_p95_ms"], 25.0)
        self.assertTrue(result["benchmark"]["performance_gate_passed"])
        self.assertFalse(result["certification"]["production_certified"])


@override_settings(
    DEBUG=True,
    RUNNING_TESTS=True,
    SECRET_KEY="unit-test-edge-signing-key",
)
class EdgeCertificationCommandTests(SimpleTestCase):
    @patch("apps.platform_runtime.management.commands.certify_edge_ai.benchmark_model")
    def test_certify_command_writes_verifiable_evidence(self, mock_benchmark):
        mock_benchmark.return_value = {
            "schema_version": 1,
            "runtime": {"digest": "sha256:abc"},
            "benchmark": {"performance_gate_passed": True},
            "certification": {"production_certified": False},
        }
        with TemporaryDirectory() as directory:
            output = Path(directory) / "edge-evidence.json"
            stdout = StringIO()
            call_command(
                "certify_edge_ai",
                model="qwen2.5:1.5b",
                concurrency=1,
                runs=1,
                output=str(output),
                strict_signing=True,
                stdout=stdout,
            )
            envelope = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(verify_evidence(envelope))
        self.assertIn("pilot_performance_passed=true", stdout.getvalue())
        self.assertIn("production_certified=false", stdout.getvalue())
