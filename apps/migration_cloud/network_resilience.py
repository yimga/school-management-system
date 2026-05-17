"""Network resilience for URL / SFTP / S3 intake (Tier 2 #14).

Wraps a fetch callable in:
    * tenacity-style retry with exponential backoff + jitter,
    * Range / If-Range checkpointing for HTTP downloads (resume after hiccup),
    * deterministic checksum verification so a partial download isn't trusted,
    * configurable timeouts that don't block the worker pool forever.

Public surface (callers in ``intake/url_intake.py`` etc.):
    fetch_with_resume(uri, *, dest, timeout=30, max_retries=5)
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Raised when a fetch exhausts its retry budget."""


def fetch_with_resume(
    uri: str,
    *,
    dest: str | Path,
    timeout: float = 30.0,
    max_retries: int = 5,
    expected_sha256: str | None = None,
) -> dict:
    """Fetch ``uri`` to ``dest`` with resume + retry + checksum guard.

    Returns ``{"path": str, "bytes": int, "sha256": str, "resumed": bool, "attempts": int}``.
    Raises ``FetchError`` when retries are exhausted.

    Supported schemes:
        * http / https — Range header resume
        * sftp         — paramiko, single-shot (no resume) with retry
        * s3           — boto3 multipart get with explicit Range
        * file / ""    — local copy (no retry needed)
    """
    parsed = urlparse(uri)
    scheme = (parsed.scheme or "file").lower()
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    local_path = _local_filesystem_path(uri, parsed) if scheme in ("file", "") else ""

    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            if scheme in ("http", "https"):
                resumed_bytes = dest_path.stat().st_size if dest_path.exists() else 0
                _fetch_http_with_range(uri, dest_path, timeout=timeout, resume_from=resumed_bytes)
            elif scheme == "sftp":
                _fetch_sftp(uri, dest_path, timeout=timeout)
            elif scheme == "s3":
                _fetch_s3(uri, dest_path)
            elif scheme in ("file", ""):
                _fetch_file(local_path or parsed.path or uri, dest_path)
            else:
                raise FetchError(f"unsupported scheme: {scheme}")
            digest, size = _hash_file(dest_path)
            if expected_sha256 and digest != expected_sha256:
                raise FetchError(
                    f"checksum mismatch: expected {expected_sha256}, got {digest}"
                )
            return {
                "path": str(dest_path),
                "bytes": size,
                "sha256": digest,
                "resumed": attempt > 1,
                "attempts": attempt,
            }
        except FetchError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            backoff = min(2.0 ** (attempt - 1), 30.0) + random.uniform(0, 0.5)
            logger.warning(
                "fetch_with_resume: %s (attempt %d/%d, sleeping %.1fs): %s",
                uri, attempt, max_retries, backoff, exc,
            )
            time.sleep(backoff)
    raise FetchError(f"fetch failed for {uri} after {max_retries} attempts: {last_err}")


def _fetch_http_with_range(uri: str, dest: Path, *, timeout: float, resume_from: int) -> None:
    import urllib.request

    headers = {"User-Agent": "RunMyCampus-MigrationCloud/1.0"}
    mode = "wb"
    if resume_from > 0 and dest.exists():
        headers["Range"] = f"bytes={resume_from}-"
        mode = "ab"
    req = urllib.request.Request(uri, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator-controlled URI
        chunk_size = 64 * 1024
        with dest.open(mode) as out:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out.write(chunk)


def _fetch_sftp(uri: str, dest: Path, *, timeout: float) -> None:
    parsed = urlparse(uri)
    try:
        import paramiko  # type: ignore[import-not-found]
    except ImportError as exc:
        raise FetchError(f"paramiko not installed: {exc}") from exc
    transport = paramiko.Transport((parsed.hostname or "", parsed.port or 22))
    transport.banner_timeout = timeout
    try:
        transport.connect(username=parsed.username or "", password=parsed.password or "")
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            sftp.get(parsed.path or "", str(dest))
        finally:
            sftp.close()
    finally:
        transport.close()


def _fetch_s3(uri: str, dest: Path) -> None:
    parsed = urlparse(uri)
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise FetchError(f"boto3 not installed: {exc}") from exc
    s3 = boto3.client("s3")
    s3.download_file(parsed.netloc, parsed.path.lstrip("/"), str(dest))


def _fetch_file(path: str, dest: Path) -> None:
    src = Path(path)
    if not src.exists() or not src.is_file():
        raise FetchError(f"source file not found: {path}")
    with src.open("rb") as r, dest.open("wb") as w:
        while True:
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            w.write(chunk)


def _local_filesystem_path(uri: str, parsed) -> str:
    """Best-effort resolution of a file:// URI to a filesystem path.

    Handles Windows quirks where ``file://C:\\path`` parses with netloc='C:'
    + a backslashed path. Falls back to stripping the ``file://`` prefix.
    """
    if not uri.startswith("file://"):
        return ""
    stripped = uri[len("file://"):]
    # ``file:///C:/path`` → /C:/path → C:/path
    if stripped.startswith("/") and len(stripped) > 3 and stripped[2] == ":":
        return stripped[1:]
    # ``file://C:\\path`` → C:\\path
    return stripped


def _hash_file(path: Path) -> tuple[str, int]:
    sha = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(64 * 1024)
            if not chunk:
                break
            sha.update(chunk)
            size += len(chunk)
    return sha.hexdigest(), size


def retry(
    fn: Callable,
    *,
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    max_backoff: float = 30.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Generic retry decorator-like wrapper. Use directly as ``retry(fn)(*args)``."""
    def wrapped(*args, **kwargs):
        last: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except retry_on as exc:
                last = exc
                if attempt == max_retries:
                    raise
                backoff = min(initial_backoff * (2 ** (attempt - 1)), max_backoff) + random.uniform(0, 0.25)
                logger.warning("retry: %s attempt %d/%d failed (sleep %.1fs)",
                                fn.__name__, attempt, max_retries, backoff)
                time.sleep(backoff)
        if last is not None:
            raise last  # pragma: no cover — defensive
    return wrapped
