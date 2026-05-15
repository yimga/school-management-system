"""Transformer ABC + registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class TransformerError(Exception):
    """Raised when a transformer cannot normalize a value.

    The orchestrator catches this, quarantines the row with the message
    attached, and continues with the next row. Never abort the bundle.
    """


@dataclass
class TransformerContext:
    """Per-call context — vendor enum tables, locale hints, grading scales.

    ``hints`` is the merged ``locale_hints`` from the artifact's profile
    plus any operator overrides. ``options`` carries transformer-specific
    config (e.g. ``{"scale": "US-A-F"}`` for the grading-scale transformer).
    """

    canonical_field: str = ""
    hints: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)


class Transformer(ABC):
    """One transformer per registered name."""

    name: str = ""

    @abstractmethod
    def transform(self, value: Any, ctx: TransformerContext) -> Any:
        """Return the canonical value or raise ``TransformerError``."""


_REGISTRY: dict[str, Transformer] = {}


def register(name: str, transformer: Transformer) -> None:
    transformer.name = name
    _REGISTRY[name] = transformer


def get_transformer(name: str) -> Transformer | None:
    return _REGISTRY.get(name)
