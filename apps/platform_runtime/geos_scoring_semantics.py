"""
GEOS scoring semantics — 6-dimension honest matrix.

The legacy matrix reports a 2-axis score (repo_pct + live_pct) which is too
easy to misread as production readiness. This module exposes a 6-dimension
projection on top of the existing pillar scores so the reader cannot collapse
public-live readiness, external-vendor readiness, and pwa readiness into a
single "composite 100".

Rules:
- `repo_pct` can be 100 only when repo verifiers support it.
- `internal_pilot_pct` reflects Lane 2 harness evidence (not public).
- `public_live_pct` cannot exceed `internal_pilot_pct`.
- `external_vendor_pct` cannot be 100 without on-disk vendor proof.
- `pwa_pct` cannot be 100 without manifest + service worker + browser/install proof.
- `market_ready_pct` = min(public_live_pct, external_vendor_pct).
- `composite_pct` = min(repo_pct, internal_pilot_pct, public_live_pct, pwa_pct, external_vendor_pct).
- `native_app_status` is always DEFERRED in current batch; not failed.
- `native_app_strategy` is fixed: PWA-first, native wrappers after 100-school proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


NATIVE_APP_STATUS_DEFERRED = "DEFERRED"
NATIVE_APP_STRATEGY = (
    "PWA-first launch strategy. Capacitor/Tauri/WebView wrappers deferred "
    "until at least 100 schools are stable on the web core and PWA "
    "installability is browser-proven on iOS Safari + Android Chrome."
)


@dataclass
class GEOSHonestScore:
    pillar_id: str
    repo_pct: float
    internal_pilot_pct: float
    public_live_pct: float
    pwa_pct: float
    external_vendor_pct: float
    market_ready_pct: float
    composite_pct: float
    native_app_status: str
    native_app_strategy: str
    verdict: str
    explanation: str

    def to_dict(self) -> dict:
        return {
            "pillar_id": self.pillar_id,
            "repo_pct": self.repo_pct,
            "internal_pilot_pct": self.internal_pilot_pct,
            "public_live_pct": self.public_live_pct,
            "pwa_pct": self.pwa_pct,
            "external_vendor_pct": self.external_vendor_pct,
            "market_ready_pct": self.market_ready_pct,
            "composite_pct": self.composite_pct,
            "native_app_status": self.native_app_status,
            "native_app_strategy": self.native_app_strategy,
            "verdict": self.verdict,
            "explanation": self.explanation,
        }


def score_pillar(
    *,
    pillar_id: str,
    repo_pct: float,
    legacy_live_pct: float,
    has_public_live_evidence: bool,
    has_external_vendor_evidence: bool,
    has_pwa_browser_evidence: bool,
) -> GEOSHonestScore:
    """Project a 2-axis pillar score into the 6-dimension honest matrix.

    `legacy_live_pct` is the value the existing verifier already emitted for
    the live axis (which mixed internal Lane 2 evidence with curated register
    statuses). We treat it as the internal-pilot ceiling and downgrade the
    public/external/pwa dimensions when the corresponding evidence is missing.
    """
    repo = max(0.0, min(100.0, repo_pct))
    internal_pilot = max(0.0, min(100.0, legacy_live_pct))
    if internal_pilot > repo:
        # Internal pilot cannot exceed what the repo actually supports.
        internal_pilot = repo
    public_live = internal_pilot if has_public_live_evidence else 0.0
    external_vendor = internal_pilot if has_external_vendor_evidence else 0.0
    pwa = repo if has_pwa_browser_evidence else min(repo, 60.0)
    market_ready = min(public_live, external_vendor)
    composite = min(repo, internal_pilot, public_live or 0.0, pwa, external_vendor or 0.0)

    if composite >= 99.0:
        verdict = "READY"
    elif public_live == 0.0:
        verdict = "PUBLIC LIVE PENDING"
    elif external_vendor == 0.0:
        verdict = "EXTERNAL VENDOR BLOCKED"
    elif pwa < 80.0:
        verdict = "PWA PROOF PARTIAL"
    else:
        verdict = "REPO SCOPE READY"

    explanation_parts: list[str] = []
    explanation_parts.append(f"repo={repo:.1f}%")
    explanation_parts.append(f"internal_pilot={internal_pilot:.1f}%")
    explanation_parts.append(f"public_live={public_live:.1f}%")
    explanation_parts.append(f"pwa={pwa:.1f}%")
    explanation_parts.append(f"external_vendor={external_vendor:.1f}%")
    if not has_public_live_evidence:
        explanation_parts.append("(public live downgraded — no proof)")
    if not has_external_vendor_evidence:
        explanation_parts.append("(external vendor downgraded — no proof)")
    if not has_pwa_browser_evidence:
        explanation_parts.append("(pwa capped at 60 — no browser proof)")

    return GEOSHonestScore(
        pillar_id=pillar_id,
        repo_pct=round(repo, 1),
        internal_pilot_pct=round(internal_pilot, 1),
        public_live_pct=round(public_live, 1),
        pwa_pct=round(pwa, 1),
        external_vendor_pct=round(external_vendor, 1),
        market_ready_pct=round(market_ready, 1),
        composite_pct=round(composite, 1),
        native_app_status=NATIVE_APP_STATUS_DEFERRED,
        native_app_strategy=NATIVE_APP_STRATEGY,
        verdict=verdict,
        explanation=" ".join(explanation_parts),
    )


def aggregate(scores: Iterable[GEOSHonestScore]) -> dict:
    rows = list(scores)
    if not rows:
        return {"empty": True}

    def avg(field: str) -> float:
        return round(sum(getattr(r, field) for r in rows) / len(rows), 1)

    return {
        "pillar_count": len(rows),
        "repo_pct": avg("repo_pct"),
        "internal_pilot_pct": avg("internal_pilot_pct"),
        "public_live_pct": avg("public_live_pct"),
        "pwa_pct": avg("pwa_pct"),
        "external_vendor_pct": avg("external_vendor_pct"),
        "market_ready_pct": avg("market_ready_pct"),
        "composite_pct": avg("composite_pct"),
        "native_app_status": NATIVE_APP_STATUS_DEFERRED,
        "native_app_strategy": NATIVE_APP_STRATEGY,
    }


__all__ = [
    "GEOSHonestScore",
    "NATIVE_APP_STATUS_DEFERRED",
    "NATIVE_APP_STRATEGY",
    "aggregate",
    "score_pillar",
]
