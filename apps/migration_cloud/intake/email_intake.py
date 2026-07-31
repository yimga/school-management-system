"""Email-with-attachments intake.

Schools forward an email (with the SIS export attached) to
``migrate@<tenant>.runmycampus.com``; the inbound mail handler hands the raw
message to this adapter, which parses every attachment and registers each as an
artifact — delegating to the file / archive adapters so a ``.csv`` attachment
lands exactly like an uploaded CSV and a ``.zip`` attachment expands into its
members.

Accepted ``handle`` shapes:
    * a path (``str`` / ``pathlib.Path``) to a ``.eml`` file,
    * raw RFC-822 ``bytes`` (or a ``str`` containing the raw message),
    * an ``email.message.Message`` / ``EmailMessage`` object.

Only real attachments are ingested — the body parts (``text/plain`` /
``text/html`` with no filename and no ``attachment`` disposition) are skipped.
Attachment filenames are sanitised to their basename (no path traversal). An
email with no attachments fails fast with a clear ``IntakeError`` (visible on the
bundle), never a silent zero-artifact success.
"""

from __future__ import annotations

import email
import os
import tempfile
from email import policy as _email_policy
from email.message import Message as _EmailMsg
from pathlib import Path
from typing import Any, Iterator

from apps.migration_cloud.models import IntakeMethod

from .base import ArtifactPayload, IntakeAdapter, IntakeContext, IntakeError, register_adapter

_ARCHIVE_SUFFIXES = (".zip", ".tar", ".gz", ".tgz", ".7z", ".bz2")
# A raw message pasted as a str won't be a filesystem path; only treat short,
# single-line strings as candidate paths before falling back to raw-bytes parse.
_MAX_PATH_LEN = 4096  # magic-number-allow: max plausible filesystem path length


class EmailIntakeAdapter(IntakeAdapter):
    """Adapter for the ``EMAIL`` intake method."""

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        msg = _parse_message(handle)
        if next(_iter_attachments(msg), None) is None:
            raise IntakeError(
                "This email has no attachments to migrate. Attach the exported "
                "SIS files (CSV / Excel / ZIP) and forward it again."
            )

    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        # Local import to avoid any import-order coupling in intake/__init__.
        from .archive_intake import ArchiveIntakeAdapter
        from .file_intake import FileIntakeAdapter

        msg = _parse_message(handle)
        workdir = Path(tempfile.mkdtemp(prefix="mc_email_"))
        seen: set[str] = set()
        any_yielded = False

        for filename, data in _iter_attachments(msg):
            safe = _safe_name(filename)
            # De-dup identical attachment names within one email so distinct
            # files never clobber each other on disk.
            candidate = safe
            i = 1
            while candidate in seen:
                stem, dot, ext = safe.partition(".")
                candidate = f"{stem}_{i}{dot}{ext}" if dot else f"{safe}_{i}"
                i += 1
            seen.add(candidate)

            local = workdir / candidate
            local.write_bytes(data)

            is_archive = Path(candidate).suffix.lower() in _ARCHIVE_SUFFIXES
            delegate: IntakeAdapter = (
                ArchiveIntakeAdapter() if is_archive else FileIntakeAdapter()
            )
            # Re-validate against the delegate so its contract holds, then yield
            # its payloads (a CSV → one artifact; a ZIP → its members).
            delegate.validate_handle(local, ctx)
            for payload in delegate.iter_artifacts(local, ctx):
                any_yielded = True
                yield payload

        if not any_yielded:
            raise IntakeError(
                "Email attachments could not be read as migratable files. Ensure "
                "the export is attached as a real file (CSV / Excel / ZIP)."
            )


def _parse_message(handle: Any) -> _EmailMsg:
    """Coerce any accepted handle shape to a parsed email message."""
    if isinstance(handle, _EmailMsg):
        return handle
    raw: bytes | None = None
    if isinstance(handle, (bytes, bytearray)):
        raw = bytes(handle)
    elif isinstance(handle, (str, Path)):
        raw_str = str(handle)
        looks_like_path = "\n" not in raw_str and len(raw_str) < _MAX_PATH_LEN
        if looks_like_path:
            try:
                p = Path(handle)
                if p.exists() and p.is_file():
                    raw = p.read_bytes()
            except (OSError, ValueError):
                raw = None
        if raw is None:
            raw = raw_str.encode("utf-8", errors="replace")
    if raw is None:
        raise IntakeError(
            "Email intake handle must be a .eml path, raw RFC-822 bytes/str, or "
            "an email.message.Message."
        )
    try:
        return email.message_from_bytes(raw, policy=_email_policy.default)
    except Exception as exc:  # noqa: BLE001 — surface a clean message
        raise IntakeError(
            f"Could not parse the forwarded email: {type(exc).__name__}: {exc}"
        ) from exc


def _iter_attachments(msg: _EmailMsg) -> Iterator[tuple[str, bytes]]:
    """Yield ``(filename, bytes)`` for each real attachment part."""
    for part in msg.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = str(part.get("Content-Disposition") or "").lower()
        # A real attachment has a filename OR an explicit attachment disposition;
        # inline body parts (no filename, no attachment disposition) are skipped.
        if not filename and "attachment" not in disposition:
            continue
        try:
            data = part.get_payload(decode=True)
        except Exception:  # noqa: BLE001 — a malformed part must not abort the rest
            data = None
        if not data:
            continue
        yield (filename or "attachment.bin"), bytes(data)


def _safe_name(filename: str) -> str:
    """Basename-only, control-char-free filename (no path traversal)."""
    base = os.path.basename(str(filename or "").replace("\\", "/")).strip()
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '<>:"|?*')
    return base or "attachment.bin"


register_adapter(IntakeMethod.EMAIL, EmailIntakeAdapter())
