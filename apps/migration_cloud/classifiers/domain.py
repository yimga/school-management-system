"""Domain classifier — picks which of the 23 canonical domains an artifact belongs to.

For each candidate domain, compute an overlap score between the artifact's
normalized headers and the union of every synonym in that domain's
ontology entries. The domain with the highest overlap (and at least one
``required_for`` field matched) wins.

When no domain reaches threshold, the AI bridge takes the shortlist
(top 3 by overlap) and returns a single pick + confidence. The shortlist
short-circuits the LLM from having to consider all 23 domains every time.

This classifier runs **per artifact**, not per bundle — a single bundle
can carry artifacts for students, attendance, grades, and finance, each
classified independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.migration_cloud import ai_bridge, defaults as mc_defaults
from apps.migration_cloud.models import MigrationArtifact
from apps.migration_cloud.ontology import (
    CANONICAL_ONTOLOGY,
    DOMAINS,
    all_synonyms,
    iter_canonical_fields,
)


@dataclass
class DomainCandidate:
    domain: str
    confidence: float
    matched_canonical_fields: list[str]
    reasoning: str


def classify_domain(*, artifact: MigrationArtifact) -> dict[str, Any]:
    """Classify a single artifact into one of the canonical domains.

    Returns::

        {
            "chosen": "students",
            "candidates": [
                {"domain": "students", "confidence": 0.82, "matched_canonical_fields": [...], ...},
                {"domain": "guardians", "confidence": 0.31, ...},
            ],
            "method": "overlap" | "ai_bridge" | "fallback",
        }
    """
    cols = (artifact.profile or {}).get("columns") or []
    if not cols:
        return _fallback("no_profile_columns")

    normalized_headers = {(c.get("normalized") or "") for c in cols if c.get("normalized")}
    if not normalized_headers:
        return _fallback("no_headers")

    ranked = _score_domains(normalized_headers)
    top = ranked[0] if ranked else None
    threshold = float(mc_defaults.get("migration_cloud.classifier.domain_min_confidence"))

    if top and top.confidence >= threshold:
        return {
            "chosen": top.domain,
            "candidates": [c.__dict__ for c in ranked[:5]],
            "method": "overlap",
        }

    # AI tiebreaker over the top-3 shortlist + 'custom_fields' escape.
    shortlist = [c.domain for c in ranked[:3]] or list(DOMAINS[:5])
    if "custom_fields" not in shortlist:
        shortlist.append("custom_fields")

    sample_rows = _build_sample_rows(cols)
    proposal = ai_bridge.propose_domain(
        school=artifact.bundle.school,
        headers=[c.get("name", "") for c in cols][:40],
        sample_rows=sample_rows[:3],
        candidate_domains=shortlist,
    )
    if proposal is not None and proposal.confidence >= threshold:
        ai_choice = DomainCandidate(
            domain=str(proposal.answer),
            confidence=float(proposal.confidence),
            matched_canonical_fields=[],
            reasoning=proposal.reasoning,
        )
        merged = [ai_choice] + [c for c in ranked if c.domain != ai_choice.domain][:4]
        return {
            "chosen": ai_choice.domain,
            "candidates": [c.__dict__ for c in merged],
            "method": "ai_bridge",
        }

    chosen = top.domain if top else "custom_fields"
    return {
        "chosen": chosen,
        "candidates": [c.__dict__ for c in (ranked or [
            DomainCandidate("custom_fields", 0.0, [], "no signal — quarantine for review"),
        ])][:5],
        "method": "fallback",
    }


def _score_domains(normalized_headers: set[str]) -> list[DomainCandidate]:
    scored: list[DomainCandidate] = []
    for domain in DOMAINS:
        if domain == "custom_fields":
            continue
        matched_fields: list[str] = []
        total_synonyms = 0
        hits = 0
        for cf in iter_canonical_fields(domain):
            syns = {s.lower() for s in all_synonyms(cf["canonical_field"], domain=domain)}
            total_synonyms += len(syns)
            overlap = normalized_headers & syns
            if overlap:
                hits += len(overlap)
                matched_fields.append(cf["canonical_field"])

        if hits == 0:
            continue

        # Confidence: matched canonical fields / total canonical fields in domain,
        # capped at 0.99. Bonus when a "required_for" field is matched (proves the domain).
        domain_fields = list(CANONICAL_ONTOLOGY[domain].keys())
        coverage = len(matched_fields) / max(len(domain_fields), 1)
        required_match_bonus = 0.0
        for cf_name in matched_fields:
            if CANONICAL_ONTOLOGY[domain][cf_name].get("required_for"):
                required_match_bonus = 0.15
                break
        confidence = min(0.99, coverage + required_match_bonus)

        scored.append(DomainCandidate(
            domain=domain,
            confidence=round(confidence, 3),
            matched_canonical_fields=matched_fields,
            reasoning=f"{len(matched_fields)}/{len(domain_fields)} canonical fields matched",
        ))

    scored.sort(key=lambda c: c.confidence, reverse=True)
    return scored


def _build_sample_rows(cols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    row_count = min(3, max((len(c.get("samples") or []) for c in cols), default=0))
    rows: list[dict[str, Any]] = []
    for i in range(row_count):
        row: dict[str, Any] = {}
        for c in cols:
            samples = c.get("samples") or []
            row[c.get("name", "")] = samples[i] if i < len(samples) else None
        rows.append(row)
    return rows


def _fallback(reason: str) -> dict[str, Any]:
    return {
        "chosen": "custom_fields",
        "candidates": [
            DomainCandidate("custom_fields", 0.0, [], reason).__dict__,
        ],
        "method": "fallback",
    }
