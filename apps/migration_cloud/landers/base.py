"""Lander contract + registry — the apply step's per-domain persistence layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator


class LanderError(Exception):
    """Raised when a canonical row cannot be persisted.

    The orchestrator quarantines the row (creates a ``MigrationQuarantineRecord``)
    with the error attached and continues with the next row. Lander errors
    never abort the bundle.
    """


@dataclass
class LanderResult:
    """Per-row outcome the orchestrator records on the child ``MigrationRun``."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    quarantined: int = 0
    errors: list[str] = field(default_factory=list)
    created_ids: list[Any] = field(default_factory=list)
    updated_ids_with_old_values: list[dict[str, Any]] = field(default_factory=list)
    # Structured per-row failures, appended in LOCKSTEP with ``errors`` by
    # ``_helpers.record_row_error``. Each entry is::
    #
    #     {"error": str,          # identical to the matching errors[i]
    #      "row": {...},          # bounded source-row snapshot — replay needs this
    #      "reason_code": str,    # a landers.reason_codes value
    #      "reason_source": str,  # "declared" | "fallback"
    #      "field": str | None}   # the offending column, when the lander knows it
    #
    # Lockstep matters: the orchestrator used to pair rows to errors through a
    # ``{error_string: row}`` dict, so two rows failing with the SAME message
    # collapsed onto one entry and every row but the last lost its snapshot. Any
    # error message that does not interpolate the row hits that — which is most
    # of them. Index alignment cannot collide.
    error_rows: list[dict[str, Any]] = field(default_factory=list)

    # Advisory diagnostics that are NOT held rows: the row landed, but something
    # attached to it did not (a custom-attributes sweep, an extras write). Ten
    # such sites used to append to ``errors`` WITHOUT incrementing ``quarantined``,
    # so each one minted a "held for review" record the board never counted — the
    # table and the banner disagreed, and a school was shown a partial-write
    # warning as though a row had been rejected. They are still durable and still
    # surfaced; they are just not counted as rows anyone must review.
    notes: list[dict[str, Any]] = field(default_factory=list)


def merge_lander_results(target: LanderResult, source: LanderResult) -> None:
    """Fold one lander's outcome into another (e.g. specialty → academics reroute)."""
    target.created += source.created
    target.updated += source.updated
    target.skipped += source.skipped
    target.quarantined += source.quarantined
    target.errors.extend(source.errors)
    target.error_rows.extend(source.error_rows)
    target.notes.extend(source.notes)
    target.created_ids.extend(source.created_ids)
    target.updated_ids_with_old_values.extend(source.updated_ids_with_old_values)


@dataclass
class LanderContext:
    """Tenant + bundle context handed to every lander invocation."""

    school: Any
    schema_name: str
    bundle_id: int
    artifact_id: int
    artifact_path: str = ""
    dry_run: bool = False
    transformer_options: dict[str, Any] = field(default_factory=dict)


class Lander(ABC):
    """One per canonical domain that owns its tenant-side persistence."""

    domain: str = ""

    # Whether THIS lander already persists every ``custom_fields.*`` /
    # ``_unmapped.*`` pass-through column itself (e.g. by sweeping them into a
    # JSON attrs bag or writing the whole row to ``DynamicFieldValue``). The
    # orchestrator's residual-capture net (``_run_lander_under_schema``) runs a
    # no-data-loss sweep behind EVERY lander that leaves this False, so a lander
    # that neither sweeps nor sets this flag still cannot drop a column. Set True
    # ONLY when the lander genuinely captures all residual keys — otherwise the
    # net is skipped and columns the lander ignores are lost. See the cross-lander
    # guardrail in ``tests/test_lander_no_column_left_behind_2026_08_16.py``.
    sweeps_custom_columns: bool = False

    @abstractmethod
    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        """Persist canonical rows under the tenant schema.

        Implementations MUST:
          * Run inside ``django_tenants.utils.schema_context(ctx.schema_name)``
            so writes land in the tenant schema (orchestrator does this
            wrapping — landers do not call schema_context themselves).
          * Respect ``ctx.dry_run`` (no writes, just return the would-be result).
          * Append ``created_ids`` and ``updated_ids_with_old_values`` so the
            rollback handler can revert the run.
          * Raise ``LanderError`` for genuine failures; per-row issues should
            increment ``quarantined`` and continue.
        """


# --- Registry ---------------------------------------------------------------

_REGISTRY: dict[str, Lander] = {}


def register(domain: str, lander: Lander) -> None:
    lander.domain = domain
    _REGISTRY[domain] = lander


def get_lander(domain: str) -> Lander | None:
    return _REGISTRY.get(domain)
