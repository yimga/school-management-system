"""Accelerator contract + registry.

An ``Accelerator`` is a thin layer that:
    1. Accepts a vendor-specific handle (API token, OAuth, sandbox URL,
       a known export ZIP layout).
    2. Pulls artifacts using either the vendor's API or the universal
       intake adapter for that shape.
    3. Pre-attaches canonical mappings (source-system enum tables,
       column → canonical field maps, transformer choices) onto each
       artifact so the universal mapper can skip its AI layer.
    4. Hands the bundle back to the orchestrator for the standard apply
       path.

Accelerators NEVER write directly to tenant tables. The orchestrator
owns persistence, RLS scoping, idempotency, quarantine, and rollback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class AcceleratorError(Exception):
    """Raised when an accelerator can't fulfil its contract.

    The orchestrator catches this and falls back to the universal pipeline
    (intake → profile → classify → map). Schools never see an error from a
    broken accelerator — only the slightly-slower universal path.
    """


@dataclass
class AcceleratorContract:
    """What an accelerator promises to deliver.

    ``pre_classified_artifacts`` maps ``path_within_bundle`` →
    ``{"domain": str, "canonical_mappings": {source_column: canonical_field}}``.
    The orchestrator merges these onto the artifacts so classifier and
    mapper skip ahead to apply.
    """

    bundle_id: int
    pre_classified_artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    vendor_enum_tables: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class Accelerator(ABC):
    """One accelerator per supported source."""

    #: Vendor slug — must match a value in
    #: ``apps.migration_cloud.classifiers.signatures.SOURCE_HEADER_SIGNATURES``.
    source: str = ""

    #: Schema or protocol version this accelerator targets (e.g. "1.2").
    version: str = ""

    @abstractmethod
    def is_handle_supported(self, handle: Any) -> bool:
        """Cheap predicate — does this accelerator recognize the handle shape?"""

    @abstractmethod
    def execute(self, *, bundle_id: int, handle: Any) -> AcceleratorContract:
        """Pull artifacts, pre-classify, return contract. May call universal intake."""


# --- Registry ---------------------------------------------------------------

AcceleratorRegistry = dict[str, Accelerator]
_REGISTRY: AcceleratorRegistry = {}


def register_accelerator(source: str, accelerator: Accelerator) -> None:
    """Register an accelerator. Last registration wins for a given source."""
    accelerator.source = source
    _REGISTRY[source] = accelerator


def get_accelerator(source: str) -> Accelerator | None:
    """Look up an accelerator by source slug. Returns ``None`` when unregistered."""
    return _REGISTRY.get(source)
