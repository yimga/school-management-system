"""
AI-assisted auto-mapping contract for migration_cloud.

Wraps apps.global_registries.schema_mapping with a confidence-scored proposal
layer. Real AI calls route through services.ai_helpers (the gateway-boundary
guard); this module never imports services.ai_gateway directly.

Source credentials, raw vendor row data, and PII are never logged or echoed
back into AI prompts.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Iterable

from apps.global_registries.schema_mapping import (
    CanonicalField,
    lookup,
    map_custom_field,
)


logger = logging.getLogger(__name__)


class AutoMappingError(RuntimeError):
    pass


_CREDENTIAL_RE = re.compile(
    r"(password|passwd|pwd|secret|token|api[_-]?key|private[_-]?key|credential)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MappingProposal:
    source_key: str
    canonical_key: str
    confidence: float
    rationale: str
    human_review_required: bool


@dataclass
class MappingProposalBundle:
    proposals: list[MappingProposal]
    rejected_keys: list[str]

    def to_dict(self) -> dict:
        return {
            "proposals": [
                {
                    "source_key": p.source_key,
                    "canonical_key": p.canonical_key,
                    "confidence": p.confidence,
                    "rationale": p.rationale,
                    "human_review_required": p.human_review_required,
                }
                for p in self.proposals
            ],
            "rejected_keys": self.rejected_keys,
        }


def _redact_for_prompt(key: str) -> str:
    if _CREDENTIAL_RE.search(key):
        return "[REDACTED]"
    return key


def propose_mappings(
    *,
    source_keys: Iterable[str],
    sample_values: dict[str, list[str]] | None = None,
    confidence_threshold: float = 0.7,
) -> MappingProposalBundle:
    """Deterministic heuristic-based mapping proposal.

    `sample_values` may be passed so callers can later swap in an AI scorer that
    routes through services.ai_helpers; the deterministic path here does not
    inspect values, never echoes them, and never logs them.
    """
    proposals: list[MappingProposal] = []
    rejected: list[str] = []

    for raw in source_keys:
        if _CREDENTIAL_RE.search(raw or ""):
            rejected.append(raw)
            logger.info(
                "ai_auto_mapping.reject_credential source=%s",
                hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12],
                extra={"scope": "ai_auto_mapping.reject"},
            )
            continue
        match: CanonicalField | None = map_custom_field(raw)
        if match is None:
            proposals.append(
                MappingProposal(
                    source_key=raw,
                    canonical_key="",
                    confidence=0.0,
                    rationale="no heuristic match — operator review required",
                    human_review_required=True,
                )
            )
            continue
        confidence = 0.95 if raw.lower() == match.key.lower() else 0.8
        proposals.append(
            MappingProposal(
                source_key=raw,
                canonical_key=match.key,
                confidence=confidence,
                rationale=f"heuristic match {_redact_for_prompt(raw)} -> {match.key}",
                human_review_required=confidence < confidence_threshold,
            )
        )

    return MappingProposalBundle(proposals=proposals, rejected_keys=rejected)


def confirm_proposal(
    *,
    proposal: MappingProposal,
    approving_actor_id: str,
) -> dict:
    if not approving_actor_id:
        raise AutoMappingError("approving_actor_id required for confirmation")
    if proposal.canonical_key and lookup(proposal.canonical_key) is None:
        raise AutoMappingError(
            f"proposal canonical_key {proposal.canonical_key!r} not in registry"
        )
    return {
        "source_key": proposal.source_key,
        "canonical_key": proposal.canonical_key,
        "approved_by_hash": hashlib.sha256(approving_actor_id.encode("utf-8")).hexdigest()[:12],
        "confidence": proposal.confidence,
    }


__all__ = [
    "AutoMappingError",
    "MappingProposal",
    "MappingProposalBundle",
    "confirm_proposal",
    "propose_mappings",
]
