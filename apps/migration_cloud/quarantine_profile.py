"""Quarantine distribution profiling — issue_class × artifact × domain."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .quarantine_resolution import (
    QUARANTINE_ISSUE_LABELS,
    _source_row_from_payload,
    quarantine_queryset_for_bundle,
)


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
