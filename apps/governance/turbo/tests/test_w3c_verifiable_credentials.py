"""Tests for w3c_verifiable_credentials runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import w3c_verifiable_credentials as vc


class VCTests(unittest.TestCase):
    def test_issue_and_verify_roundtrip(self) -> None:
        v = vc.issue_vc(issuer_did="did:key:issuer", subject_did="did:key:subject", claims={"transcript_hash": "abc"}, secret="s")
        result = vc.verify_vc(v, secret="s")
        self.assertTrue(result["valid"])

    def test_tampered_payload_fails_verification(self) -> None:
        v = vc.issue_vc(issuer_did="did:key:issuer", subject_did="did:key:subject", claims={"transcript_hash": "abc"}, secret="s")
        v["credentialSubject"]["transcript_hash"] = "tampered"
        result = vc.verify_vc(v, secret="s")
        self.assertFalse(result["valid"])

    def test_wrong_secret_fails_verification(self) -> None:
        v = vc.issue_vc(issuer_did="did:key:issuer", subject_did="did:key:subject", claims={"x": 1}, secret="s")
        result = vc.verify_vc(v, secret="other")
        self.assertFalse(result["valid"])
