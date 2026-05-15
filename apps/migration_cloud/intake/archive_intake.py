"""Archive intake — expands zip / tar / tar.gz to individual artifacts.

A school's data drop is often a zip with hundreds of mixed CSV / XLSX / JSON
files in nested folders. This adapter expands the archive *streamingly* (no
full extract to disk; members are read on demand) and yields one
``ArtifactPayload`` per usable member. The archive itself is registered as
the parent artifact so lineage is preserved end-to-end.

Safety caps (read from ``apps.migration_cloud.defaults``):
    * ``max_archive_members`` — refuse zip-bomb-shaped archives.
    * ``max_archive_depth`` — refuse deeply nested archives-within-archives.
    * ``max_artifact_bytes`` — refuse any single member that exceeds the cap.

Nested archives (a zip inside a zip) are NOT recursively expanded by this
adapter; the orchestrator handles recursion so depth limits and idempotency
remain centralized. This adapter only emits one level of children.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import mimetypes
import os
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Iterator

from apps.migration_cloud import defaults as mc_defaults
from apps.migration_cloud.models import IntakeMethod

from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
)

_READ_CHUNK = 1024 * 1024  # 1 MiB


class ArchiveIntakeAdapter(IntakeAdapter):
    """Adapter for the ``ARCHIVE`` intake method.

    Handle: path (str or ``Path``) to a single archive file. Mixed archives
    inside one bundle should be uploaded separately so each gets its own
    parent-archive lineage.
    """

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        path = _coerce_path(handle)
        if not path.exists() or not path.is_file():
            raise IntakeError(f"Archive not found at intake: {path}")
        if not _is_supported_archive(path):
            raise IntakeError(
                f"Unsupported archive format: {path.name} "
                "(supported: .zip, .tar, .tar.gz, .tgz, .gz)"
            )

    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        path = _coerce_path(handle)
        max_members = int(mc_defaults.get("migration_cloud.intake.max_archive_members"))
        max_artifact_bytes = int(
            mc_defaults.get("migration_cloud.intake.max_artifact_bytes")
        )

        parent_path = path.name
        emitted = 0

        for member_name, opener, member_size in _iter_archive_members(path):
            if emitted >= max_members:
                raise IntakeError(
                    f"Archive {path.name} exceeds member cap ({max_members}); "
                    "split or upload as a folder instead."
                )
            if member_size > max_artifact_bytes:
                raise IntakeError(
                    f"Member {member_name} ({member_size:,} bytes) exceeds "
                    f"artifact cap ({max_artifact_bytes:,} bytes)."
                )

            # Hash the member without loading it fully into memory.
            digest = hashlib.sha256()
            actual_size = 0
            with opener() as stream:
                while True:
                    chunk = stream.read(_READ_CHUNK)
                    if not chunk:
                        break
                    digest.update(chunk)
                    actual_size += len(chunk)

            mime = mimetypes.guess_type(member_name)[0] or ""
            yield ArtifactPayload(
                path_within_bundle=os.path.join(parent_path, member_name),
                filename=os.path.basename(member_name),
                byte_size=actual_size,
                sha256=digest.hexdigest(),
                mime_type=mime,
                parent_archive_path=parent_path,
                content_opener=opener,
            )
            emitted += 1


def _coerce_path(handle: Any) -> Path:
    if isinstance(handle, (str, Path)):
        return Path(handle)
    raise IntakeError(
        f"ArchiveIntakeAdapter expects a path; got {type(handle).__name__}"
    )


def _is_supported_archive(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.endswith(".zip")
        or name.endswith(".tar")
        or name.endswith(".tar.gz")
        or name.endswith(".tgz")
        or name.endswith(".gz")
    )


def _iter_archive_members(path: Path):
    """Yield ``(member_name, content_opener, declared_size)`` for each member."""
    name = path.name.lower()

    if name.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                # Capture the member name in the closure; defer open until called.
                member_name = info.filename
                declared = info.file_size

                def _opener(mn=member_name, zp=path):
                    return zipfile.ZipFile(zp).open(mn, "r")

                yield member_name, _opener, declared
        return

    if name.endswith(".tar") or name.endswith(".tar.gz") or name.endswith(".tgz"):
        mode = "r:gz" if name.endswith((".tar.gz", ".tgz")) else "r:"
        with tarfile.open(path, mode) as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                member_name = member.name
                declared = member.size

                def _opener(mn=member_name, tp=path, tm=mode):
                    tf_inner = tarfile.open(tp, tm)
                    fp = tf_inner.extractfile(mn)
                    if fp is None:
                        tf_inner.close()
                        raise IntakeError(f"Could not extract member {mn} from {tp}")
                    return _TarMemberStream(fp, tf_inner)

                yield member_name, _opener, declared
        return

    if name.endswith(".gz"):
        # Single-file gzip: the inner filename is the archive name minus .gz.
        inner_name = path.name[: -len(".gz")]
        with gzip.open(path, "rb") as gz:
            data = gz.read()  # gzip single-file uncompressed size is unknown until read
        declared = len(data)

        def _opener(payload=data):
            return io.BytesIO(payload)

        yield inner_name, _opener, declared
        return

    raise IntakeError(f"Unhandled archive format: {path.name}")


class _TarMemberStream(io.RawIOBase):
    """Tar member stream that closes its parent tarfile on close."""

    def __init__(self, inner, owner):
        self._inner = inner
        self._owner = owner

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        return self._inner.read(size)

    def close(self) -> None:
        try:
            self._inner.close()
        finally:
            self._owner.close()
            super().close()


register_adapter(IntakeMethod.ARCHIVE, ArchiveIntakeAdapter())
