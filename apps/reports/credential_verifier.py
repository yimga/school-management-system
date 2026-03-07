"""
Plan VIII: Blockchain-backed credentials scaffold.
CredentialVerifier abstraction for verifying transcript/diploma hashes on-chain.
Production needs a blockchain gateway (e.g. Ethereum, Polygon, or L3).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of on-chain credential verification."""
    verified: bool
    on_chain_status: Optional[str] = None  # e.g. "anchored", "pending", "revoked"
    tx_id: Optional[str] = None
    message: Optional[str] = None


class CredentialVerifier(ABC):
    """Abstract base for verifying credential hashes on-chain."""

    @abstractmethod
    def verify(self, credential_hash: str) -> VerificationResult:
        """Verify a credential hash (e.g. ReportDocumentHash.sha256_hash) on-chain."""
        pass

    def health_check(self) -> bool:
        """Optional: verify gateway connectivity."""
        return True


def get_credential_verifier(school=None):
    """
    Return the active CredentialVerifier for the tenant, or None if not configured.
    Configure via ServiceIntegration (e.g. blockchain gateway URL + API key).
    """
    from apps.siteconfig.integration_registry import resolve_active_integration
    rec = resolve_active_integration(school, "blockchain") if school else None
    if not rec or not getattr(rec, "is_active", True) or not getattr(rec, "config", None):
        return None
    # Stub: no concrete implementation; production would instantiate EthereumVerifier etc.
    return None


def verify_credential_hash(credential_hash: str, school=None) -> VerificationResult:
    """
    Verify a credential hash. Uses get_credential_verifier(school); if no verifier,
    returns verified=False with message "No blockchain verifier configured".
    """
    verifier = get_credential_verifier(school)
    if not verifier:
        return VerificationResult(verified=False, message="No blockchain verifier configured")
    return verifier.verify(credential_hash)
