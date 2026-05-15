"""Intake adapters — one per source-shape.

The universal intake pipeline accepts any artifact and routes it through a
single registry of adapters keyed by ``IntakeMethod``. Adapters convert their
source-shape into a normalized stream of ``MigrationArtifact`` rows under a
``MigrationBundle``; everything downstream (profiler, classifier, mapper,
orchestrator) is shape-agnostic.

Add a new source-shape by:
    1. Implementing :class:`IntakeAdapter` in a new module under this package.
    2. Registering it via ``register_adapter(IntakeMethod.X, MyAdapter)``.
    3. Adding the new ``IntakeMethod`` value in ``apps.migration_cloud.models``.

The registry is intentionally module-level rather than DB-backed because the
set of source-shapes is small and changes ship with code, not config.
"""

from __future__ import annotations

from .base import IntakeAdapter, IntakeError, IntakeRegistry, get_adapter, register_adapter

# Side-effect imports register the adapters into the registry.
from . import access_intake  # noqa: F401
from . import archive_intake  # noqa: F401
from . import database_intake  # noqa: F401
from . import email_intake  # noqa: F401
from . import file_intake  # noqa: F401
from . import oauth_intake  # noqa: F401
from . import pdf_intake  # noqa: F401
from . import sql_dump_intake  # noqa: F401
from . import url_intake  # noqa: F401

__all__ = [
    "IntakeAdapter",
    "IntakeError",
    "IntakeRegistry",
    "get_adapter",
    "register_adapter",
]
