"""Detect distribution drift in production at-risk scores.

Compares the current `RiskFactor.score` distribution (over the last
`--window-days` days) to a reference distribution captured at training time.
Reports Population Stability Index (PSI) — the standard credit-risk drift
metric — and classifies severity.

PSI bands (industry convention):
    < 0.10         no significant drift
    0.10 - 0.25    moderate drift (investigate)
    >= 0.25        significant drift (retrain candidate)

Reference distribution lives alongside the artifact as a sidecar JSON file
(`<artifact>.distribution.json`) — first run captures it; subsequent runs
compare. Use `--write-reference` to overwrite after a clean retrain.

Tenant scoping: pass `--school <slug>` to compare a single tenant's
distribution; otherwise the comparison runs platform-wide. Per-tenant
drift is the usable signal when one cohort behaviour shifts (e.g. a new
intake's attendance pattern moved); platform-wide tends to wash out.
"""

from __future__ import annotations

import json
import logging
import math
from collections import Counter
from pathlib import Path
from typing import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.analytics.models import RiskFactor
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.check_at_risk_drift")

# 10 equal-width bins across the score domain [0, 100].
_BIN_EDGES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
_BIN_COUNT = len(_BIN_EDGES) - 1
# Floor for empty bins so log() / division never blow up (industry convention).
_EPSILON = 1e-4


_SCORE_DOMAIN_MAX = 100  # RiskFactor.score is bounded [0, 100]
_BIN_WIDTH = 10


def _bin_index(score: float) -> int:
    if score >= _SCORE_DOMAIN_MAX:
        return _BIN_COUNT - 1
    if score <= 0:
        return 0
    return min(int(score // _BIN_WIDTH), _BIN_COUNT - 1)


def _distribution(scores: Iterable[float]) -> list[float]:
    counter = Counter()
    total = 0
    for s in scores:
        counter[_bin_index(float(s))] += 1
        total += 1
    if not total:
        return [0.0] * _BIN_COUNT
    return [counter.get(i, 0) / total for i in range(_BIN_COUNT)]


def _psi(reference: list[float], current: list[float]) -> float:
    psi = 0.0
    for ref, cur in zip(reference, current):
        ref_p = max(ref, _EPSILON)
        cur_p = max(cur, _EPSILON)
        psi += (cur_p - ref_p) * math.log(cur_p / ref_p)
    return psi


def _classify(psi: float) -> str:
    if psi < 0.10:
        return "stable"
    if psi < 0.25:
        return "moderate"
    return "significant"


class Command(BaseCommand):
    help = "Compute Population Stability Index for prod RiskFactor scores."

    def add_arguments(self, parser):
        parser.add_argument(
            "--artifact",
            required=True,
            help="Path to the joblib artifact; sidecar reference distribution "
            "lives at <artifact>.distribution.json.",
        )
        parser.add_argument(
            "--window-days",
            type=int,
            default=30,
            help="Look back this many days of RiskFactor rows for the current dist.",
        )
        parser.add_argument(
            "--school",
            default=None,
            help="School slug to scope the analysis to (omit for platform-wide).",
        )
        parser.add_argument(
            "--write-reference",
            action="store_true",
            help="Capture the current distribution as the new reference (use after retrain).",
        )
        parser.add_argument(
            "--max-psi",
            type=float,
            default=None,
            help="Optional gate: exit non-zero when PSI exceeds this floor.",
        )
        parser.add_argument(
            "--json",
            default=None,
            help="Optional JSON report output path.",
        )

    def handle(self, *args, **opts):
        artifact_path = Path(opts["artifact"])
        ref_path = artifact_path.with_suffix(artifact_path.suffix + ".distribution.json")

        cutoff = timezone.now() - timezone.timedelta(days=opts["window_days"])
        qs = RiskFactor.objects.filter(computed_at__gte=cutoff)
        scope = "platform"
        if opts.get("school"):
            try:
                school = School.objects.get(slug=opts["school"])
            except School.DoesNotExist as exc:
                raise CommandError(f"No school with slug '{opts['school']}'") from exc
            qs = qs.filter(school_id=school.id)
            scope = f"school={school.slug}"
        else:
            # tenant-isolation-allow: drift command computes platform-wide histogram by design (operator-invoked tooling).
            pass

        scores = list(qs.values_list("score", flat=True))
        if not scores:
            raise CommandError(
                f"No RiskFactor rows in the last {opts['window_days']} days "
                f"for scope={scope}; nothing to compare."
            )

        current_dist = _distribution(scores)
        n_current = len(scores)

        if opts.get("write_reference"):
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(
                json.dumps(
                    {
                        "bin_edges": _BIN_EDGES,
                        "distribution": current_dist,
                        "captured_at": timezone.now().isoformat(),
                        "sample_size": n_current,
                        "scope": scope,
                    },
                    indent=2,
                )
            )
            self.stdout.write(self.style.SUCCESS(
                f"Wrote reference distribution to {ref_path} ({n_current} samples)"
            ))
            return

        if not ref_path.exists():
            raise CommandError(
                f"No reference distribution at {ref_path}. "
                "Run once with --write-reference after the last clean retrain."
            )
        ref_payload = json.loads(ref_path.read_text())
        ref_dist = ref_payload.get("distribution") or []
        if len(ref_dist) != _BIN_COUNT:
            raise CommandError(
                f"Reference distribution at {ref_path} has {len(ref_dist)} bins; "
                f"expected {_BIN_COUNT}. Re-capture with --write-reference."
            )

        psi = _psi(ref_dist, current_dist)
        classification = _classify(psi)

        report = {
            "artifact": str(artifact_path),
            "reference": str(ref_path),
            "scope": scope,
            "window_days": opts["window_days"],
            "reference_sample_size": ref_payload.get("sample_size"),
            "reference_captured_at": ref_payload.get("captured_at"),
            "current_sample_size": n_current,
            "psi": psi,
            "classification": classification,
            "bin_edges": _BIN_EDGES,
            "reference_distribution": ref_dist,
            "current_distribution": current_dist,
        }
        self.stdout.write(f"PSI={psi:.4f} ({classification}) — "
                          f"n_current={n_current}, scope={scope}")
        if opts.get("json"):
            Path(opts["json"]).parent.mkdir(parents=True, exist_ok=True)
            Path(opts["json"]).write_text(json.dumps(report, indent=2))
            self.stdout.write(self.style.SUCCESS(f"Wrote {opts['json']}"))

        if opts.get("max_psi") is not None and psi > opts["max_psi"]:
            raise CommandError(
                f"Drift gate failed: PSI={psi:.3f} > max={opts['max_psi']:.3f}"
            )
