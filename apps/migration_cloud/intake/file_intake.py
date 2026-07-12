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
import os
import re
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Iterator

from apps.migration_cloud.models import IntakeMethod
from apps.migration_cloud.xlsx_explode import explode_workbook

from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
    sha256_of_stream,
)

_XLSX_SUFFIXES = (".xlsx", ".xlsm")


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
            # A multi-tab workbook is really several tables in one file. Explode
            # it into one artifact per non-empty sheet so every tab is
            # classified + landed independently — otherwise the pipeline reads
            # only the first sheet and silently drops the rest (data loss). A
            # single-sheet workbook (or one openpyxl can't read) falls through
            # to the raw-file path below unchanged.
            if path.suffix.lower() in _XLSX_SUFFIXES:
                sheets = explode_workbook(path)
                if len(sheets) >= 2:
                    yield from _sheet_payloads(path, sheets)
                    continue

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


def _sheet_payloads(
    workbook_path: Path, sheets: list[tuple[str, bytes]]
) -> Iterator[ArtifactPayload]:
    """Yield one TSV ``ArtifactPayload`` per exploded worksheet.

    Each sheet's TSV is spilled to a short-lived temp file so the payload's
    ``content_opener`` stays valid for the blob-capture at ingest (mirrors the
    PDF adapter). Artifact names are ``<workbook> - <sheet>.tsv`` and are
    de-duplicated so the (bundle, sha256, path) uniqueness constraint holds.
    """
    seen: set[str] = set()
    for index, (sheet_name, tsv_bytes) in enumerate(sheets, start=1):
        fd, tmp_name = tempfile.mkstemp(prefix="mc_xlsx_", suffix=".tsv")
        os.close(fd)
        tmp = Path(tmp_name)
        tmp.write_bytes(tsv_bytes)

        safe_sheet = re.sub(r"[^\w\- ]", "_", sheet_name).strip() or f"Sheet{index}"
        art_name = f"{workbook_path.stem} - {safe_sheet}.tsv"
        if art_name in seen:
            art_name = f"{workbook_path.stem} - {index}. {safe_sheet}.tsv"
        seen.add(art_name)

        yield ArtifactPayload(
            path_within_bundle=art_name,
            filename=art_name,
            byte_size=len(tsv_bytes),
            sha256=sha256(tsv_bytes).hexdigest(),
            mime_type="text/tab-separated-values",
            content_opener=_path_opener(tmp),
        )


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
