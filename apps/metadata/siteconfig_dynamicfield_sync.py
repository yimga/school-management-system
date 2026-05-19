"""
Batch 14 Phase 5b: legacy ``siteconfig_dynamicfield*`` tables removed (migration ``siteconfig.0168``).

Historical sync from siteconfig EAV → metadata is only possible on a pre-5b codebase against a DB
that still has those tables. This module remains so management commands and imports stay stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_PHASE5B_RETIREMENT = (
    "Batch 14 Phase 5b: siteconfig_dynamicfield* tables removed (siteconfig.0168). "
    "sync_siteconfig_dynamicfields_to_metadata is a no-op; use a pre-5b release to copy legacy rows "
    "if your database still contained siteconfig EAV data before applying 0168."
)


@dataclass
class SiteconfigDynamicFieldSyncStats:
    definitions_upserted: int = 0
    values_upserted: int = 0
    definition_rows_seen: int = 0
    value_rows_seen: int = 0
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: SiteconfigDynamicFieldSyncStats) -> None:
        self.definitions_upserted += other.definitions_upserted
        self.values_upserted += other.values_upserted
        self.definition_rows_seen += other.definition_rows_seen
        self.value_rows_seen += other.value_rows_seen
        self.warnings.extend(other.warnings)


def sync_definitions_from_siteconfig(*, dry_run: bool = False) -> SiteconfigDynamicFieldSyncStats:
    _ = dry_run
    return SiteconfigDynamicFieldSyncStats()


def sync_values_from_siteconfig(*, dry_run: bool = False) -> SiteconfigDynamicFieldSyncStats:
    _ = dry_run
    return SiteconfigDynamicFieldSyncStats()


def run_full_sync(
    *,
    dry_run: bool = False,
    definitions: bool = True,
    values: bool = True,
) -> SiteconfigDynamicFieldSyncStats:
    _ = (dry_run, definitions, values)  # API compatibility; no-op regardless.
    # Phase 5b retirement is expected on every deploy — not a WARN-worthy condition.
    return SiteconfigDynamicFieldSyncStats()
