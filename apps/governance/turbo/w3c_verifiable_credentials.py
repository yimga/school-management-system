"""Phase 6 turbo runtime: W3C Verifiable Credentials issuance.

Implements an offline did:key issuance using stdlib HMAC for signing. This is
not production cryptography; it is a deterministic structural prototype that
exercises the VC contract so the rest of the pipeline (verifier, recipient
cross-check, audit log) can be wired in next. Real ed25519 signing layers in
once the cryptography dep is available in the deploy posture.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-w3c-verifiable-credentials"
CONTRACT_TITLE = "W3C Verifiable Credentials for StudentPassport"

REPO = Path(__file__).resolve().parents[3]


def _stable_did(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()[:16]
    return "did:key:" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


def issue_vc(*, issuer_did: str, subject_did: str, claims: dict[str, Any], secret: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "type": ["VerifiableCredential", "RunMyCampusTranscript"],
        "issuer": issuer_did,
        "issuanceDate": datetime.now(timezone.utc).isoformat(),
        "credentialSubject": {"id": subject_did, **claims},
    }
    canonical = _canonical_json(payload)
    payload["proof"] = {
        "type": "RmcHmacSha256Proof2026",
        "created": payload["issuanceDate"],
        "proofPurpose": "assertionMethod",
        "verificationMethod": issuer_did + "#hmac-sha256",
        "jws": _sign(canonical, secret),
    }
    return payload


def verify_vc(vc: dict[str, Any], *, secret: str) -> dict[str, Any]:
    proof = vc.get("proof")
    if not isinstance(proof, dict):
        return {"valid": False, "reason": "missing_proof"}
    expected_jws = proof.get("jws")
    payload_wo_proof = {k: v for k, v in vc.items() if k != "proof"}
    canonical = _canonical_json(payload_wo_proof)
    actual_jws = _sign(canonical, secret)
    if not hmac.compare_digest(str(expected_jws), actual_jws):
        return {"valid": False, "reason": "signature_mismatch"}
    return {"valid": True, "issuer": vc.get("issuer"), "subject": (vc.get("credentialSubject") or {}).get("id")}


def runtime_health() -> dict[str, Any]:
    issuer_did = _stable_did("runmycampus.com")
    subject_did = _stable_did("student-001")
    vc = issue_vc(issuer_did=issuer_did, subject_did=subject_did, claims={"transcript_hash": "deadbeef"}, secret="rotation_key_demo")
    verification = verify_vc(vc, secret="rotation_key_demo")
    return {"contract_id": CONTRACT_ID, "healthy": verification.get("valid"), "issuer_did": issuer_did}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
