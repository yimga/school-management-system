"""Source-system classifier.

Signal stack (cheapest first):

1. **Operator hint.** ``bundle.source_hint`` set in the wizard wins at
   confidence 1.0. The classifier still runs and stores its own ranking
   on the bundle for audit, but the hint is the chosen value.

2. **Header signature.** Each vendor exports columns in characteristic
   shapes (e.g. PowerSchool typically emits ``Student_Number``,
   ``Enroll_Status``, ``LastFirst``; Veracross uses ``personId``,
   ``schoolLevel``). The signature table is data — extend it without
   touching code via ``apps.migration_cloud.classifiers.signatures``.

3. **AI tiebreaker.** When no signature exceeds the
   ``migration_cloud.classifier.source_min_confidence`` threshold, the
   AI bridge gets a single prompt with headers + 3 sample rows and is
   asked to pick from the known-source allow-list.

Output: a list of ``SourceCandidate`` ranked by confidence, plus a
``chosen`` field with the top-1 (which may still be ``unknown_custom``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.migration_cloud import ai_bridge, defaults as mc_defaults
from apps.migration_cloud.models import MigrationArtifact, MigrationBundle

from .signatures import SOURCE_HEADER_SIGNATURES


@dataclass
class SourceCandidate:
    source: str
    confidence: float
    reasoning: str


def classify_source(
    *,
    bundle: MigrationBundle,
    artifacts: list[MigrationArtifact] | None = None,
) -> dict[str, Any]:
    """Classify the source system for an entire bundle.

    Returns::

        {
            "chosen": "powerschool",
            "candidates": [
                {"source": "powerschool", "confidence": 0.86, "reasoning": "..."},
                {"source": "unknown_custom", "confidence": 0.50, ...},
            ],
            "method": "signature" | "operator_hint" | "ai_bridge" | "fallback",
        }
    """
    if bundle.source_hint:
        candidate = bundle.source_hint.strip().lower().replace(" ", "_")
        return {
            "chosen": candidate,
            "candidates": [
                SourceCandidate(candidate, 1.0, "operator hint").__dict__,
            ],
            "method": "operator_hint",
        }

    artifact_iter = artifacts if artifacts is not None else list(bundle.artifacts.all())
    headers, sample_rows = _gather_signal(artifact_iter)
    if not headers:
        return _fallback("no_readable_headers")

    # Deterministic signature scoring.
    ranked = _score_signatures(headers)
    top = ranked[0] if ranked else None
    threshold = float(mc_defaults.get("migration_cloud.classifier.source_min_confidence"))

    if top and top.confidence >= threshold:
        return {
            "chosen": top.source,
            "candidates": [c.__dict__ for c in ranked[:5]],
            "method": "signature",
        }

    # AI tiebreaker.
    known = sorted(SOURCE_HEADER_SIGNATURES.keys())
    proposal = ai_bridge.propose_source_system(
        school=bundle.school,
        headers=headers[:40],
        sample_rows=sample_rows[:3],
        known_sources=known,
    )
    if proposal is not None and proposal.confidence >= threshold:
        ai_candidate = SourceCandidate(
            source=str(proposal.answer),
            confidence=float(proposal.confidence),
            reasoning=proposal.reasoning,
        )
        merged = [ai_candidate] + [c for c in ranked if c.source != ai_candidate.source][:4]
        return {
            "chosen": ai_candidate.source,
            "candidates": [c.__dict__ for c in merged],
            "method": "ai_bridge",
        }

    # Neither path reached threshold — fall through honestly.
    chosen = top.source if top else "unknown_custom"
    return {
        "chosen": chosen,
        "candidates": [c.__dict__ for c in (ranked or [SourceCandidate("unknown_custom", 0.0, "no signal")])][:5],
        "method": "fallback",
    }


def _gather_signal(
    artifacts: list[MigrationArtifact],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Pull headers + a few sample rows from the strongest-signal artifact."""
    if not artifacts:
        return [], []
    # Pick the artifact with the most columns + populated profile.
    candidates = [
        a for a in artifacts
        if a.profile and (a.profile.get("columns") or [])
    ]
    if not candidates:
        return [], []
    best = max(candidates, key=lambda a: len(a.profile.get("columns") or []))
    cols = best.profile.get("columns") or []
    headers = [c.get("name", "") for c in cols]

    # Build 3 sample row dicts from the per-column samples lists.
    row_count = min(3, max((len(c.get("samples") or []) for c in cols), default=0))
    sample_rows: list[dict[str, Any]] = []
    for i in range(row_count):
        row: dict[str, Any] = {}
        for c in cols:
            samples = c.get("samples") or []
            row[c.get("name", "")] = samples[i] if i < len(samples) else None
        sample_rows.append(row)
    return headers, sample_rows


def _score_signatures(headers: list[str]) -> list[SourceCandidate]:
    norm = {_norm(h) for h in headers if h}
    if not norm:
        return []

    scored: list[SourceCandidate] = []
    for source, sig in SOURCE_HEADER_SIGNATURES.items():
        required = {_norm(h) for h in sig.get("required", [])}
        suggested = {_norm(h) for h in sig.get("suggested", [])}

        req_hits = len(required & norm)
        sug_hits = len(suggested & norm)
        if req_hits == 0 and sug_hits == 0:
            continue

        # Confidence: heavy weight on required hits, light weight on suggested.
        denom = max(len(required) + len(suggested), 1)
        confidence = (req_hits * 1.5 + sug_hits) / (denom * 1.5)
        confidence = min(0.99, confidence)
        scored.append(SourceCandidate(
            source=source,
            confidence=round(confidence, 3),
            reasoning=f"{req_hits}/{len(required)} required, {sug_hits}/{len(suggested)} suggested headers matched",
        ))

    scored.sort(key=lambda c: c.confidence, reverse=True)
    return scored


def _norm(header: str) -> str:
    return "".join(ch.lower() for ch in header if ch.isalnum())


def _fallback(reason: str) -> dict[str, Any]:
    return {
        "chosen": "unknown_custom",
        "candidates": [
            SourceCandidate("unknown_custom", 0.0, reason).__dict__,
        ],
        "method": "fallback",
    }
