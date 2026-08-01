"""Client offline proof is resolved from evidence, and never asserted.

``browser_proof_status`` used to be the literal ``PARTIAL_CLIENT_HARNESS_REQUIRED``
baked into every blueprint's local-first manifest. It was written before a browser
harness existed and never revisited after one landed, so it capped blueprint
readiness at 80 no matter what the platform proved — the hardcoded-"72" defect
wearing a different label.

These tests lock the replacement: a real artifact, written only by a full
harness pass, that self-invalidates when the code it vouches for changes.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from apps.platform_runtime import offline_proof_evidence as proof


def _evidence(**overrides) -> dict:
    payload = {
        "harness": "verify_client_offline_endurance/1",
        "result": "pass",
        "generated_at": "2026-07-31T00:00:00+00:00",
        "legs": {"restart_persistence": True, "storage_pressure": True},
        "source_fingerprint": proof.source_fingerprint(),
    }
    payload.update(overrides)
    return payload


class BrowserProofResolutionTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "proof.json"
        self.addCleanup(proof.reset_cache)

    def _resolve(self, payload=None) -> dict:
        if payload is not None:
            self.path.write_text(json.dumps(payload), encoding="utf-8")
        proof.reset_cache()
        with override_settings(RMC_OFFLINE_CLIENT_PROOF_PATH=str(self.path)):
            return proof.browser_proof_detail()

    def test_absent_evidence_is_pending_with_a_reason(self):
        detail = self._resolve()

        self.assertEqual(detail["status"], proof.BROWSER_PROOF_PENDING)
        self.assertEqual(detail["reason"], "no_evidence_recorded")
        self.assertFalse(detail["verified"])

    def test_valid_evidence_verifies(self):
        detail = self._resolve(_evidence())

        self.assertEqual(detail["status"], proof.BROWSER_PROOF_VERIFIED)
        self.assertTrue(detail["verified"])

    def test_failed_harness_run_is_not_a_proof(self):
        detail = self._resolve(_evidence(result="fail"))

        self.assertEqual(detail["status"], proof.BROWSER_PROOF_PENDING)
        self.assertEqual(detail["reason"], "harness_failed")

    def test_missing_leg_is_not_a_proof(self):
        detail = self._resolve(
            _evidence(legs={"restart_persistence": True, "storage_pressure": False})
        )

        self.assertEqual(detail["status"], proof.BROWSER_PROOF_PENDING)
        self.assertEqual(detail["reason"], "missing_legs")
        self.assertEqual(detail["missing_legs"], ["storage_pressure"])

    def test_unreadable_evidence_is_not_a_proof(self):
        self.path.write_text("{not json", encoding="utf-8")
        proof.reset_cache()
        with override_settings(RMC_OFFLINE_CLIENT_PROOF_PATH=str(self.path)):
            detail = proof.browser_proof_detail()

        self.assertEqual(detail["status"], proof.BROWSER_PROOF_PENDING)
        self.assertEqual(detail["reason"], "unreadable_evidence")

    def test_proof_goes_stale_when_the_proven_source_changes(self):
        # MUST-FIRE: a passing run recorded against yesterday's vault must not
        # vouch for today's. Without this the artifact would be a one-time
        # rubber stamp — exactly the "green forever" failure the literal had.
        stale = _evidence(
            source_fingerprint={
                rel: "0" * 64 for rel in proof.PROVEN_SOURCES
            }
        )
        detail = self._resolve(stale)

        self.assertEqual(detail["status"], proof.BROWSER_PROOF_PENDING)
        self.assertEqual(detail["reason"], "source_changed_since_proof")
        self.assertEqual(detail["drifted_sources"], list(proof.PROVEN_SOURCES))

    def test_source_fingerprint_covers_real_files(self):
        prints = proof.source_fingerprint()

        self.assertEqual(sorted(prints), sorted(proof.PROVEN_SOURCES))
        for rel, digest in prints.items():
            self.assertEqual(len(digest), 64, msg=f"{rel} did not hash")


class LiveTreeProofTests(SimpleTestCase):
    """The tree's own evidence must be internally consistent.

    Deliberately does not demand VERIFIED: the harness needs Chrome and is not
    CI-wired, so requiring a pass here would redden CI on machines that cannot
    run it. What must always hold is that the resolver never claims more than
    the artifact supports.
    """

    def test_resolution_is_consistent_with_the_recorded_artifact(self):
        proof.reset_cache()
        detail = proof.browser_proof_detail()

        if detail["status"] == proof.BROWSER_PROOF_VERIFIED:
            payload = json.loads(proof.evidence_path().read_text(encoding="utf-8"))
            self.assertEqual(payload["result"], "pass")
            self.assertEqual(payload["source_fingerprint"], proof.source_fingerprint())
            for leg in proof.REQUIRED_LEGS:
                self.assertIs(payload["legs"][leg], True)
        else:
            self.assertEqual(detail["status"], proof.BROWSER_PROOF_PENDING)
            self.assertTrue(detail["reason"], msg="Pending must always name a reason.")
