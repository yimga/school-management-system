"""Sync tenant per-file domain tags into the pipeline operator map."""

from __future__ import annotations

from apps.migration_cloud.accelerators.runmycampus_canonical import is_valid_canonical_domain
from apps.migration_cloud.models import BundleStatus, MigrationBundle


def invalidate_catalog_preflight_cache(bundle: MigrationBundle) -> None:
    """Drop stale catalog preflight so the next read recomputes after tag changes."""
    summary = dict(bundle.mapping_summary or {})
    if "catalog_preflight" not in summary:
        return
    del summary["catalog_preflight"]
    bundle.mapping_summary = summary
    bundle.save(update_fields=["mapping_summary", "updated_at"])


def sync_operator_assigned_domains(
    bundle: MigrationBundle,
    *,
    rewind_status: bool = True,
) -> None:
    """Mirror ``artifact.assigned_domain`` into ``discovery_summary``.

    When *rewind_status* is True (tenant review POST), rewind to PROFILED so
    ``_advance`` re-runs classify+map. When False (pipeline auto-fix after map),
    keep the current status — the caller runs ``refresh_bundle_inference`` next.
    """
    summary = dict(bundle.discovery_summary or {})
    operator = dict(summary.get("operator_assigned_domains") or {})
    for artifact in bundle.artifacts.all():
        tag = (artifact.assigned_domain or "").strip()
        path_key = artifact.path_within_bundle or ""
        name_key = artifact.filename or ""
        if tag and is_valid_canonical_domain(tag):
            if path_key:
                operator[path_key] = tag
            if name_key:
                operator[name_key] = tag
        else:
            if path_key:
                operator.pop(path_key, None)
            if name_key:
                operator.pop(name_key, None)
    summary["operator_assigned_domains"] = operator
    bundle.discovery_summary = summary
    update_fields = ["discovery_summary", "updated_at"]
    if rewind_status and bundle.status in (
        BundleStatus.CLASSIFIED,
        BundleStatus.MAPPED,
        BundleStatus.READY,
    ):
        bundle.status = BundleStatus.PROFILED
        update_fields.append("status")
    invalidate_catalog_preflight_cache(bundle)
    bundle.save(update_fields=update_fields)
