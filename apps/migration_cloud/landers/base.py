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
    # Audit C-4: optional structured per-row failures. Each entry is
    # ``{"error": str, "row": <bounded source-row snapshot>}`` so the orchestrator
    # can thread the offending SOURCE ROW into the quarantine record (not just an
    # error string). Populated by ``_helpers.record_row_error``; landers that only
    # append to ``errors`` keep the string-only quarantine payload (no regression).
    error_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LanderContext:
    """Tenant + bundle context handed to every lander invocation."""

    school: Any
    schema_name: str
    bundle_id: int
    artifact_id: int
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
