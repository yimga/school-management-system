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
import logging
import mimetypes
import os
import re
import tarfile
import zipfile
import zlib
from pathlib import Path
from typing import Any, Iterator

from apps.migration_cloud import defaults as mc_defaults
from apps.migration_cloud.models import IntakeMethod
from apps.migration_cloud.xlsx_explode import explode_workbook, first_sheet_name

from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
)

logger = logging.getLogger(__name__)

_READ_CHUNK = 1024 * 1024  # 1 MiB
_XLSX_SUFFIXES = (".xlsx", ".xlsm", ".xls")


def _read_member_capped(stream, cap: int, member_name: str) -> bytes:
    """Read an archive member fully but refuse to inflate past ``cap`` bytes.

    A workbook member has to be read whole (the workbook readers need all the
    bytes), but a member that under-declares its size in the zip central
    directory would otherwise inflate unbounded here and OOM the worker. Cap the
    in-memory read exactly like the raw-member streaming path, raising
    ``IntakeError`` (a cap violation, NOT a skippable member error) on breach.
    """
    buf = bytearray()
    while True:
        chunk = stream.read(_READ_CHUNK)
        if not chunk:
            break
        buf += chunk
        if len(buf) > cap:
            raise IntakeError(
                f"Member {member_name} inflated past the artifact cap "
                f"({cap:,} bytes) mid-read — refusing a potential decompression bomb."
            )
    return bytes(buf)

# Per-member read failures that quarantine the ONE member instead of failing the
# whole bundle: encrypted / password-protected zip members raise stdlib
# RuntimeError (NotImplementedError, its subclass, covers unsupported
# compression), corrupt members raise BadZipFile / TarError / zlib.error, and
# truncated streams raise EOFError / OSError. Cap violations raise IntakeError
# (deliberately NOT in this set) so they still fail the bundle as policy.
_MEMBER_SKIP_ERRORS = (
    RuntimeError,
    zipfile.BadZipFile,
    tarfile.TarError,
    zlib.error,
    EOFError,
    OSError,
)


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

            member_within = os.path.join(parent_path, member_name)

            try:
                # A multi-tab workbook member is several tables in one file.
                # Explode it into one TSV artifact per sheet so an archived
                # workbook doesn't silently drop tabs 2+ (same fix as the
                # FILE_UPLOAD adapter). We must read the member fully for the
                # workbook readers; single-sheet / unreadable workbooks fall
                # through to the raw-member path below.
                if member_name.lower().endswith(_XLSX_SUFFIXES):
                    with opener() as stream:
                        # Bomb guard: the pre-yield check trusts the archive's
                        # DECLARED member size; a workbook member that
                        # under-declares (zip central-directory lie) would inflate
                        # unbounded on a plain stream.read(). Cap the in-memory
                        # read like the raw-member path below does.
                        data = _read_member_capped(
                            stream, max_artifact_bytes, member_name,
                        )
                    sheets = explode_workbook(data)
                    if len(sheets) >= 2:
                        for payload in _sheet_member_payloads(
                            member_within, member_name, sheets, parent_path
                        ):
                            yield payload
                            emitted += 1
                        continue
                    if len(sheets) == 1:
                        # First sheet blank, data in exactly one LATER sheet: the
                        # raw reader only reads sheet 0 (blank) -> zero rows, so
                        # substitute the data sheet's TSV. If the single sheet IS
                        # sheet 0, fall through to the raw-member path below.
                        first = first_sheet_name(data)
                        if first is not None and sheets[0][0] != first:
                            for payload in _sheet_member_payloads(
                                member_within, member_name, sheets, parent_path
                            ):
                                yield payload
                                emitted += 1
                            continue
                    # Single-sheet (first) / unreadable: emit the raw member,
                    # reusing the bytes we already read (no second archive pass).
                    mime = mimetypes.guess_type(member_name)[0] or ""
                    yield ArtifactPayload(
                        path_within_bundle=member_within,
                        filename=os.path.basename(member_name),
                        byte_size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                        mime_type=mime,
                        parent_archive_path=parent_path,
                        content_opener=_bytes_opener(data),
                    )
                    emitted += 1
                    continue

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
                        # Bomb guard: the pre-yield check above trusts the archive's
                        # DECLARED member size. A member that under-declares (zip
                        # central-directory lie) would otherwise stream unbounded here.
                        # IntakeError is deliberately outside _MEMBER_SKIP_ERRORS, so
                        # this fails the bundle as a cap violation rather than silently
                        # skipping the member.
                        if actual_size > max_artifact_bytes:
                            raise IntakeError(
                                f"Member {member_name} inflated past the artifact cap "
                                f"({max_artifact_bytes:,} bytes) mid-read — refusing a "
                                "potential decompression bomb."
                            )

                mime = mimetypes.guess_type(member_name)[0] or ""
                yield ArtifactPayload(
                    path_within_bundle=member_within,
                    filename=os.path.basename(member_name),
                    byte_size=actual_size,
                    sha256=digest.hexdigest(),
                    mime_type=mime,
                    parent_archive_path=parent_path,
                    content_opener=opener,
                )
                emitted += 1
            except _MEMBER_SKIP_ERRORS as exc:
                # One encrypted / password-protected (stdlib RuntimeError),
                # corrupt (BadZipFile / TarError / zlib) or truncated member must
                # not sink the whole bundle — a 500-file drop with one locked
                # member still ingests the other 499. Skip-and-record here;
                # bundle-level failure is reserved for archive-OPEN errors, which
                # surface from _iter_archive_members before this point.
                logger.warning(
                    "archive_intake: skipping unreadable member %r in %s (%s: %s)",
                    member_name,
                    path.name,
                    type(exc).__name__,
                    exc,
                )
                continue


def _bytes_opener(data: bytes):
    def _open():
        return io.BytesIO(data)

    return _open


def _sheet_member_payloads(
    member_within: str,
    member_name: str,
    sheets: list[tuple[str, bytes]],
    parent_path: str,
) -> Iterator[ArtifactPayload]:
    """Yield one TSV ``ArtifactPayload`` per exploded worksheet of an archive
    member, preserving the member's folder + parent-archive lineage.

    ``parent_archive_path`` is the archive's own name (identical to raw
    members) so the orchestrator links each sheet back to the parent artifact.
    """
    parent_dir = os.path.dirname(member_within)
    stem = os.path.splitext(os.path.basename(member_name))[0]
    seen: set[str] = set()
    for index, (sheet_name, tsv_bytes) in enumerate(sheets, start=1):
        safe_sheet = re.sub(r"[^\w\- ]", "_", sheet_name).strip() or f"Sheet{index}"
        art = f"{stem} - {safe_sheet}.tsv"
        if art in seen:
            art = f"{stem} - {index}. {safe_sheet}.tsv"
        seen.add(art)
        yield ArtifactPayload(
            path_within_bundle=os.path.join(parent_dir, art) if parent_dir else art,
            filename=art,
            byte_size=len(tsv_bytes),
            sha256=hashlib.sha256(tsv_bytes).hexdigest(),
            mime_type="text/tab-separated-values",
            parent_archive_path=parent_path,
            content_opener=_bytes_opener(tsv_bytes),
        )


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


def _iter_archive_members(path: Path, max_bytes: int | None = None):
    """Yield ``(member_name, content_opener, declared_size)`` for each member."""
    name = path.name.lower()
    if max_bytes is None:
        max_bytes = int(mc_defaults.get("migration_cloud.intake.max_artifact_bytes"))

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
        # DECOMPRESSION BOMB GUARD. gzip's uncompressed size is unknown until read,
        # so a tiny .gz can inflate to many GB and OOM the worker — and the caller's
        # per-artifact byte cap only runs on the yielded (already-inflated) size, too
        # late. Read at most cap+1 bytes: if the stream still isn't exhausted, it is
        # over the cap, so refuse the bundle instead of inflating unbounded.
        with gzip.open(path, "rb") as gz:
            data = gz.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise IntakeError(
                f"Gzip member {inner_name} decompresses beyond the artifact cap "
                f"({max_bytes:,} bytes) — refusing a potential decompression bomb."
            )
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
