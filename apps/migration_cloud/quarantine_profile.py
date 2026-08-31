"""Quarantine distribution profiling — issue_class × artifact × domain."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .quarantine_resolution import (
    QUARANTINE_ISSUE_LABELS,
    _source_row_from_payload,
    quarantine_queryset_for_bundle,
)


def _artifact_key(value) -> str:
    """Basename, lowercased. Quarantine payloads and artifact rows disagree on
    whether the path carries directories, so compare the only part they share."""
    return str(value or "").strip().replace(chr(92), "/").rsplit("/", 1)[-1].lower()


def artifact_yield_overview(bundle) -> list[dict[str, Any]]:
    """Per artifact: rows discovered vs rows that never became records.

    Closes a blind spot found reading production bundle 85. All 88 of its held
    rows sat on one PDF. Autopilot dismisses all 88 as page furniture, quarantine
    drops to zero and the bundle reads APPLIED -- with nothing, anywhere, saying
    that file contributed NOTHING. Correct if it was only ever a stats report;
    indistinguishable from a successful import if it was not.

    Nothing stores "records created per artifact" -- ``ApplyResult.per_artifact``
    is built during apply and then discarded -- but it does not need to. Every
    discovered row either lands or is quarantined, so an artifact whose
    quarantine count reaches its ``row_count`` produced no records at all. That
    stays true after autopilot dismisses them, because dismissal marks records
    REPAIRED rather than deleting them.

    Counting is done in the database, grouped, precisely because a bundle can
    carry 75,600 held rows.
    """
    from django.db.models import Count

    from apps.automation.models import MigrationQuarantineRecord
    from .quarantine_resolution import quarantine_queryset_for_bundle

    tallies: dict[str, dict[str, int]] = {}
    grouped = (
        quarantine_queryset_for_bundle(bundle, pending_only=False)
        .values("payload__artifact", "status")
        .annotate(n=Count("id"))
    )
    for entry in grouped:
        slot = tallies.setdefault(
            _artifact_key(entry.get("payload__artifact")),
            {"held_total": 0, "held_pending": 0, "held_resolved": 0},
        )
        count = int(entry.get("n") or 0)
        slot["held_total"] += count
        if entry.get("status") == MigrationQuarantineRecord.Status.PENDING:
            slot["held_pending"] += count
        else:
            slot["held_resolved"] += count

    rows: list[dict[str, Any]] = []
    for artifact in bundle.artifacts.all():
        key = _artifact_key(artifact.path_within_bundle) or _artifact_key(artifact.filename)
        slot = tallies.get(key) or {"held_total": 0, "held_pending": 0, "held_resolved": 0}
        discovered = artifact.row_count
        # row_count is null for archives and binaries -- formats that were never
        # going to yield rows. Unknown is not zero, so they are not accused.
        produced_nothing = bool(
            discovered and discovered > 0 and slot["held_total"] >= discovered
        )
        rows.append(
            {
                "artifact": artifact.path_within_bundle or artifact.filename,
                "format": str(artifact.detected_format or ""),
                "rows_discovered": discovered,
                "held_total": slot["held_total"],
                "held_pending": slot["held_pending"],
                "held_resolved": slot["held_resolved"],
                "produced_nothing": produced_nothing,
            }
        )
    rows.sort(key=lambda r: (not r["produced_nothing"], str(r["artifact"])))
    return rows


def profile_quarantine_distribution(
    bundle,
    *,
    pending_only: bool = True,
) -> dict[str, Any]:
    """Return a structured profile of held rows for a bundle run."""
    qs = quarantine_queryset_for_bundle(bundle, pending_only=pending_only)
    by_class: dict[str, int] = defaultdict(int)
    by_domain: dict[str, int] = defaultdict(int)
    by_artifact: dict[str, int] = defaultdict(int)
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    pdf_noise_candidates = 0
    total = 0

    try:
        from .landers._helpers import row_is_pdf_noise_hold
    except ImportError:  # pragma: no cover
        row_is_pdf_noise_hold = None  # type: ignore[assignment]

    for rec in qs.iterator():
        total += 1
        issue_class = str(rec.issue_class or "lander_error")
        domain = str(rec.domain or "—")
        payload = rec.payload if isinstance(rec.payload, dict) else {}
        artifact = str(payload.get("artifact") or "—")
        artifact_label = artifact.rsplit("/", 1)[-1] if artifact != "—" else "—"

        by_class[issue_class] += 1
        by_domain[domain] += 1
        by_artifact[artifact_label] += 1
        matrix[issue_class][f"{domain}|{artifact_label}"] += 1

        if row_is_pdf_noise_hold is not None and issue_class == "missing_required":
            source_row = _source_row_from_payload(payload)
            if row_is_pdf_noise_hold(domain, source_row, artifact):
                pdf_noise_candidates += 1

    return {
        "bundle_id": getattr(bundle, "pk", None),
        "pending_only": pending_only,
        "total": total,
        "by_issue_class": dict(sorted(by_class.items(), key=lambda x: -x[1])),
        "by_domain": dict(sorted(by_domain.items(), key=lambda x: -x[1])),
        "by_artifact": dict(sorted(by_artifact.items(), key=lambda x: -x[1])),
        "issue_class_labels": {
            k: QUARANTINE_ISSUE_LABELS.get(k, k) for k in by_class
        },
        "matrix_issue_class_domain_artifact": {
            ic: dict(sorted(cells.items(), key=lambda x: -x[1]))
            for ic, cells in sorted(matrix.items())
        },
        "pdf_noise_candidates": pdf_noise_candidates,
    }
