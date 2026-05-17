"""PSI drift detection for the grade-prediction model.

Same math as `check_at_risk_drift` but binned over [0, 100] grade
domain and sourced from `GradePrediction.predicted_grade`.
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

from apps.analytics.models import GradePrediction
from apps.schools.models import School

logger = logging.getLogger(
    "apps.analytics.commands.check_grade_prediction_drift"
)

_BIN_EDGES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
_BIN_COUNT = len(_BIN_EDGES) - 1
_BIN_WIDTH = 10
_SCORE_MAX = 100
_EPSILON = 1e-4


def _bin_index(grade: float) -> int:
    if grade >= _SCORE_MAX:
        return _BIN_COUNT - 1
    if grade <= 0:
        return 0
    return min(int(grade // _BIN_WIDTH), _BIN_COUNT - 1)


def _distribution(grades: Iterable[float]) -> list[float]:
    counter = Counter()
    total = 0
    for g in grades:
        counter[_bin_index(float(g))] += 1
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
    help = "Compute PSI for grade-prediction distribution vs reference."

    def add_arguments(self, parser):
        parser.add_argument("--artifact", required=True)
        parser.add_argument("--window-days", type=int, default=30)
        parser.add_argument("--school", default=None)
        parser.add_argument("--write-reference", action="store_true")
        parser.add_argument("--max-psi", type=float, default=None)
        parser.add_argument("--json", default=None)

    def handle(self, *args, **opts):
        artifact_path = Path(opts["artifact"])
        ref_path = artifact_path.with_suffix(
            artifact_path.suffix + ".grade_distribution.json"
        )

        cutoff = timezone.now() - timezone.timedelta(days=opts["window_days"])
        qs = GradePrediction.objects.filter(computed_at__gte=cutoff)
        scope = "platform"
        if opts.get("school"):
            try:
                school = School.objects.get(slug=opts["school"])
            except School.DoesNotExist as exc:
                raise CommandError(f"No school '{opts['school']}'.") from exc
            qs = qs.filter(school_id=school.id)
            scope = f"school={school.slug}"
        else:
            # tenant-isolation-allow: platform-wide drift audit.
            pass

        grades = list(qs.values_list("predicted_grade", flat=True))
        if not grades:
            raise CommandError(
                f"No GradePrediction rows in window={opts['window_days']}d "
                f"scope={scope}."
            )
        current = _distribution(grades)

        if opts.get("write_reference"):
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(json.dumps({
                "bin_edges": _BIN_EDGES,
                "distribution": current,
                "captured_at": timezone.now().isoformat(),
                "sample_size": len(grades),
                "scope": scope,
            }, indent=2))
            self.stdout.write(self.style.SUCCESS(
                f"Wrote reference at {ref_path}"
            ))
            return

        if not ref_path.exists():
            raise CommandError(
                f"No reference at {ref_path}. "
                "Run once with --write-reference after a clean retrain."
            )
        ref = json.loads(ref_path.read_text())
        ref_dist = ref.get("distribution") or []
        if len(ref_dist) != _BIN_COUNT:
            raise CommandError("Reference distribution shape mismatch.")
        psi = _psi(ref_dist, current)
        classification = _classify(psi)

        report = {
            "scope": scope, "window_days": opts["window_days"],
            "reference_sample_size": ref.get("sample_size"),
            "current_sample_size": len(grades),
            "psi": psi, "classification": classification,
            "reference_distribution": ref_dist,
            "current_distribution": current,
        }
        self.stdout.write(
            f"PSI={psi:.4f} ({classification}) n={len(grades)} scope={scope}"
        )
        if opts.get("json"):
            Path(opts["json"]).parent.mkdir(parents=True, exist_ok=True)
            Path(opts["json"]).write_text(json.dumps(report, indent=2))
        if opts.get("max_psi") is not None and psi > opts["max_psi"]:
            raise CommandError(
                f"Drift gate: PSI={psi:.3f} > max={opts['max_psi']}"
            )
