"""Migrate legacy siteconfig.ProductFeedback rows into apps.feedback.FeatureRequest."""

from __future__ import annotations

from dataclasses import dataclass

LEGACY_MARKER_PREFIX = "[legacy-product-feedback:"

_STATUS_MAP = {
    "SUBMITTED": "submitted",
    "PLANNED": "planned",
    "IN_DEVELOPMENT": "in_development",
    "RELEASED": "released",
    "WONT_DO": "declined",
}


@dataclass
class MigrationSummary:
    scanned: int = 0
    created: int = 0
    skipped_existing: int = 0
    dry_run: bool = True


def migrate_legacy_rows(*, dry_run: bool = True) -> MigrationSummary:
    from apps.feedback.models import FeatureRequest
    from apps.siteconfig.models_marketing import ProductFeedback

    summary = MigrationSummary(dry_run=dry_run)
    for legacy in ProductFeedback.objects.order_by("pk"):
        summary.scanned += 1
        marker = f"{LEGACY_MARKER_PREFIX}{legacy.pk}]"
        # tenant-isolation-allow: platform-legacy-feedback-migration-idempotent-marker-check
        if FeatureRequest.objects.filter(problem_statement__contains=marker).exists():
            summary.skipped_existing += 1
            continue
        if dry_run:
            summary.created += 1
            continue
        FeatureRequest.objects.create(
            school=None,
            submitted_by=legacy.submitted_by,
            title=legacy.title[:180],
            problem_statement=f"{marker}\n\n{legacy.description}".strip(),
            module=legacy.module or "platform",
            region=legacy.region or "",
            status=_STATUS_MAP.get(legacy.status, FeatureRequest.Status.SUBMITTED),
            vote_count=max(0, int(legacy.upvotes or 0)),
            roadmap_status=legacy.get_status_display(),
        )
        summary.created += 1
    return summary
