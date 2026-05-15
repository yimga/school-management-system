"""Intake adapter contract — one ABC, one registry, used by every source-shape.

Each adapter takes a source-shape-specific *handle* (a file path, a URL, an
OAuth token, a SQL connection string) and yields ``ArtifactPayload`` records
that the orchestrator persists as ``MigrationArtifact`` rows under a bundle.

Adapters NEVER touch the database directly. They emit payloads; the
``BundleIngestionService`` writes rows. This keeps adapters trivially
unit-testable and lets the orchestrator enforce idempotency, deduplication,
and tenant scoping in one place.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import IO, Any, Iterator, Mapping, MutableMapping


class IntakeError(Exception):
    """Raised when intake cannot proceed (auth failed, blob unreadable, etc.).

    Adapters should raise this with a human-readable message; the orchestrator
    marks the bundle FAILED and stores the message on ``size_summary['error']``.
    """


@dataclass
class ArtifactPayload:
    """A single artifact emitted by an adapter, ready for the orchestrator to persist.

    ``content_stream`` is opened lazily by the orchestrator (not the adapter)
    when the profiler reads bytes; this keeps memory bounded for large bundles.
    Adapters provide a ``content_opener`` callable that the orchestrator calls
    inside its own context to obtain the stream.
    """

    path_within_bundle: str
    filename: str
    byte_size: int
    sha256: str
    mime_type: str = ""
    encoding: str = ""
    parent_archive_path: str | None = None
    content_opener: Any = None  # callable () -> IO[bytes]; resolved by orchestrator
    extra: MutableMapping[str, Any] = field(default_factory=dict)


@dataclass
class IntakeContext:
    """Per-bundle context passed to adapters at start.

    Adapters read tenant scope, idempotency key, and seeded defaults from here
    rather than calling Django settings directly — easier to test, easier to
    swap defaults at runtime.
    """

    bundle_id: int
    idempotency_key: str
    schema_name: str = ""
    source_hint: str = ""
    options: Mapping[str, Any] = field(default_factory=dict)


class IntakeAdapter(ABC):
    """One adapter per ``IntakeMethod`` value.

    Subclasses override :meth:`iter_artifacts` to yield ``ArtifactPayload``
    records and optionally :meth:`validate_handle` to fail fast on bad inputs
    (missing file, invalid credentials, unreachable URL).
    """

    #: The ``IntakeMethod`` value this adapter handles.
    intake_method: str = ""

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        """Optional fast-fail. Override to raise ``IntakeError`` before iteration."""

    @abstractmethod
    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        """Yield one ``ArtifactPayload`` per file/table/sheet/blob in the source."""


# --- Registry ---------------------------------------------------------------

IntakeRegistry = dict[str, IntakeAdapter]
_REGISTRY: IntakeRegistry = {}


def register_adapter(intake_method: str, adapter: IntakeAdapter) -> None:
    """Register an adapter for an ``IntakeMethod``. Last registration wins."""
    adapter.intake_method = intake_method
    _REGISTRY[intake_method] = adapter


def get_adapter(intake_method: str) -> IntakeAdapter:
    """Look up the adapter for a method. Raises ``KeyError`` if unregistered."""
    try:
        return _REGISTRY[intake_method]
    except KeyError as exc:  # pragma: no cover — defensive
        raise KeyError(
            f"No intake adapter registered for method {intake_method!r}. "
            "Did you forget to import apps.migration_cloud.intake?"
        ) from exc


# --- Helpers shared by adapters --------------------------------------------

_HASH_CHUNK = 1024 * 1024  # 1 MiB


def sha256_of_stream(stream: IO[bytes]) -> tuple[str, int]:
    """Return ``(hex_digest, byte_count)`` for a binary stream.

    Streams are consumed; callers that need to re-read should rewind or reopen.
    """
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = stream.read(_HASH_CHUNK)
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
    return digest.hexdigest(), total
