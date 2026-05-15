"""Value-normalization transformer library — apply on every row at apply time.

Each transformer takes a source value (string, usually) and produces a
canonical value or raises ``TransformerError``. The mapper attaches one
transformer per (source_column, canonical_field) mapping; the orchestrator
runs them as it streams rows into the tenant.

Add a new transformer by subclassing :class:`Transformer` in a new module
under this package and registering with ``register("name", instance)``.
The AI bridge's ``propose_transformer`` returns the registry key as a
string, so adding a transformer makes it available to the LLM by name.

Design notes:
    * Transformers are stateless. State (vendor enum tables, grading-scale
      lookups, locale hints) is passed in via the ``context`` argument so
      the same transformer instance can be reused across tenants safely.
    * Transformers are deterministic. Same input + same context = same
      output. This is what makes dry-run preview meaningful.
    * Transformers raise ``TransformerError`` (not ValueError) when a
      value can't be normalized. The orchestrator catches and quarantines
      the row; the bundle continues.
"""

from __future__ import annotations

from .base import Transformer, TransformerContext, TransformerError, get_transformer, register

# Side-effect imports register transformers into the registry.
from . import attendance_code  # noqa: F401
from . import currency_to_decimal  # noqa: F401
from . import date_iso_normalize  # noqa: F401
from . import encoding_fix  # noqa: F401
from . import enum_rewrite  # noqa: F401
from . import grading_scale_to_canonical  # noqa: F401
from . import name_split  # noqa: F401
from . import phone_e164  # noqa: F401

__all__ = [
    "Transformer",
    "TransformerContext",
    "TransformerError",
    "get_transformer",
    "register",
]
