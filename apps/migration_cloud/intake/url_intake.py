"""URL / signed-link / SFTP / S3 intake.

Pulls bytes from a remote URL (HTTPS signed link), an SFTP path, or an
S3 prefix into a temporary local file then delegates to
:class:`FileIntakeAdapter` (single-file) or :class:`ArchiveIntakeAdapter`
(archive). This keeps the heavy lifting in one place — fetcher here,
shape handling there.

Supported handle shapes:
    * ``str`` URL starting with ``http://`` or ``https://`` — fetched
      via ``urllib.request`` with a 60-second timeout.
    * ``str`` URL starting with ``sftp://`` — requires ``paramiko``;
      raises ``IntakeError`` if not installed.
    * ``str`` URL starting with ``s3://`` — requires ``boto3``; raises
      ``IntakeError`` if not installed.

Safety:
    * Honors ``migration_cloud.intake.max_artifact_bytes`` — refuses
      downloads larger than the cap.
    * Stores the fetched file in a temp directory, registers the local
      path on the bundle's ``intake_source_uri`` so subsequent profiler
      runs can re-read.
    * Verifies SHA-256 over the downloaded bytes and uses that as the
      artifact's hash (idempotent for the same source URL + bytes).
"""

from __future__ import annotations

import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

from apps.migration_cloud import defaults as mc_defaults
from apps.migration_cloud.models import IntakeMethod

from .archive_intake import ArchiveIntakeAdapter
from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
)
from .file_intake import FileIntakeAdapter

_DOWNLOAD_TIMEOUT_SECONDS = 60
_CHUNK = 1024 * 1024


class UrlIntakeAdapter(IntakeAdapter):
    """Fetches a remote artifact then delegates to file/archive intake."""

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        if not isinstance(handle, str) or not handle:
            raise IntakeError("URL intake handle must be a non-empty URL string.")
        scheme = urllib.parse.urlparse(handle).scheme.lower()
        if scheme not in ("http", "https", "sftp", "s3"):
            raise IntakeError(
                f"Unsupported URL scheme {scheme!r}; expected http/https/sftp/s3."
            )

    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        url = str(handle)
        scheme = urllib.parse.urlparse(url).scheme.lower()
        max_bytes = int(mc_defaults.get("migration_cloud.intake.max_artifact_bytes"))

        local_path = _fetch_to_tempfile(url, scheme, max_bytes)
        suffix = local_path.suffix.lower()
        is_archive = suffix in (".zip", ".tar", ".gz", ".tgz", ".7z", ".bz2")

        delegate: IntakeAdapter = (
            ArchiveIntakeAdapter() if is_archive else FileIntakeAdapter()
        )
        # Re-validate against the delegate so the delegate's contract holds.
        delegate.validate_handle(local_path, ctx)
        yield from delegate.iter_artifacts(local_path, ctx)


def _fetch_to_tempfile(url: str, scheme: str, max_bytes: int) -> Path:
    """Download URL → temp file, with size cap and best-effort sniff of filename."""
    parsed = urllib.parse.urlparse(url)
    filename = os.path.basename(parsed.path) or "remote_artifact.bin"
    fd, tmp_name = tempfile.mkstemp(prefix="mc_url_", suffix=f"_{filename}")
    os.close(fd)
    tmp = Path(tmp_name)

    if scheme in ("http", "https"):
        _fetch_http(url, tmp, max_bytes)
    elif scheme == "sftp":
        _fetch_sftp(url, tmp, max_bytes)
    elif scheme == "s3":
        _fetch_s3(url, tmp, max_bytes)
    else:
        raise IntakeError(f"URL scheme {scheme!r} is recognized but no fetcher is wired.")
    return tmp


def _fetch_http(url: str, dest: Path, max_bytes: int) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "RunMyCampus-MigrationCloud/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as resp, dest.open("wb") as out:
            total = 0
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise IntakeError(
                        f"Download exceeded artifact cap ({max_bytes:,} bytes)."
                    )
                out.write(chunk)
    except IntakeError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface a clean message
        raise IntakeError(f"HTTP fetch failed for {url}: {type(exc).__name__}: {exc}") from exc


def _fetch_sftp(url: str, dest: Path, max_bytes: int) -> None:
    try:
        import paramiko  # type: ignore[import-not-found]
    except ImportError as exc:
        raise IntakeError(
            "SFTP intake requires 'paramiko' — install before using sftp:// URLs."
        ) from exc

    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 22
    user = parsed.username or ""
    password = parsed.password or ""
    remote_path = parsed.path or "/"
    if not host or not user:
        raise IntakeError(f"SFTP URL is missing host or username: {url!r}")

    try:
        with paramiko.Transport((host, port)) as tx:
            tx.connect(username=user, password=password)
            sftp = paramiko.SFTPClient.from_transport(tx)
            try:
                attr = sftp.stat(remote_path)
                if attr.st_size and attr.st_size > max_bytes:
                    raise IntakeError(
                        f"Remote SFTP file is {attr.st_size:,} bytes; exceeds cap {max_bytes:,}."
                    )
                sftp.get(remote_path, str(dest))
            finally:
                sftp.close()
    except IntakeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IntakeError(f"SFTP fetch failed for {url}: {type(exc).__name__}: {exc}") from exc


def _fetch_s3(url: str, dest: Path, max_bytes: int) -> None:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise IntakeError(
            "S3 intake requires 'boto3' — install before using s3:// URLs."
        ) from exc

    parsed = urllib.parse.urlparse(url)
    bucket = parsed.netloc
    key = (parsed.path or "").lstrip("/")
    if not bucket or not key:
        raise IntakeError(f"S3 URL must be s3://<bucket>/<key>: got {url!r}")

    try:
        client = boto3.client("s3")
        head = client.head_object(Bucket=bucket, Key=key)
        size = int(head.get("ContentLength", 0) or 0)
        if size and size > max_bytes:
            raise IntakeError(f"S3 object is {size:,} bytes; exceeds cap {max_bytes:,}.")
        client.download_file(bucket, key, str(dest))
    except IntakeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IntakeError(f"S3 fetch failed for {url}: {type(exc).__name__}: {exc}") from exc


# Re-register so the upgraded adapter takes precedence over the Phase U1 stub.
for _method in (IntakeMethod.URL, IntakeMethod.SFTP, IntakeMethod.S3):
    register_adapter(_method, UrlIntakeAdapter())
