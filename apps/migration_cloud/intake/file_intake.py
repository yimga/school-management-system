"""Direct-file intake — handles a single file or a list/iterable of paths.

The most common path: a school admin uploads one or more files through the
wizard. Each file becomes one ``ArtifactPayload``. No archive expansion; that
is :mod:`archive_intake`'s job.

Inputs accepted as the ``handle``:
    * ``pathlib.Path`` or ``str`` to a single file.
    * Iterable of paths.
    * Iterable of ``(path, mime_type)`` tuples (operator-supplied MIME).

Validation deliberately leaves unknown extensions in place rather than
quarantining at intake — the profiler in Phase U2 sniffs bytes and the
classifier in Phase U3 decides whether the file is usable. Quarantine at
intake would lose long-tail sources the platform is designed to ingest.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Iterable, Iterator

from apps.migration_cloud.models import IntakeMethod

from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
    sha256_of_stream,
)


class FileIntakeAdapter(IntakeAdapter):
    """Adapter for the ``FILE_UPLOAD`` intake method."""

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        for path, _ in _normalize_handle(handle):
            if not path.exists():
                raise IntakeError(f"File not found at intake: {path}")
            if not path.is_file():
                raise IntakeError(f"Path is not a file: {path}")

    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        for path, hint_mime in _normalize_handle(handle):
            mime = hint_mime or (mimetypes.guess_type(path.name)[0] or "")
            with path.open("rb") as stream:
                digest, byte_size = sha256_of_stream(stream)

            yield ArtifactPayload(
                path_within_bundle=path.name,
                filename=path.name,
                byte_size=byte_size,
                sha256=digest,
                mime_type=mime,
                content_opener=_path_opener(path),
            )


def _path_opener(path: Path):
    def _open():
        return path.open("rb")

    return _open


def _normalize_handle(handle: Any) -> Iterable[tuple[Path, str]]:
    """Coerce supported handle shapes to ``[(Path, mime_hint), ...]``."""
    if isinstance(handle, (str, Path)):
        yield Path(handle), ""
        return

    try:
        iterator = iter(handle)
    except TypeError as exc:
        raise IntakeError(
            f"FileIntakeAdapter does not accept handle of type {type(handle).__name__}"
        ) from exc

    for item in iterator:
        if isinstance(item, (str, Path)):
            yield Path(item), ""
        elif isinstance(item, tuple) and len(item) == 2:
            path, mime = item
            yield Path(path), str(mime or "")
        else:
            raise IntakeError(
                f"FileIntakeAdapter cannot normalize handle item: {item!r}"
            )


register_adapter(IntakeMethod.FILE_UPLOAD, FileIntakeAdapter())
