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

import ipaddress
import os
import socket
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


class _TransientFetchError(IntakeError):
    """A remote fetch failure that is worth retrying (network hiccup, timeout).

    A subclass of ``IntakeError`` so, once the retry budget is exhausted, it
    propagates like any other intake failure. Permanent failures (size cap
    exceeded, missing optional dependency, malformed URL) raise plain
    ``IntakeError`` and are NOT retried.
    """


def _resilience_max_retries() -> int:
    """Retry budget for remote pulls (wires the ``migration_cloud.network`` config)."""
    try:
        return max(1, int(mc_defaults.get("migration_cloud.network.max_retries")))
    except Exception:  # noqa: BLE001 — fall back to a safe default
        return 5


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _assert_public_host(url: str) -> None:
    """SSRF guard: refuse a URL whose host resolves to a non-public address.

    A pasted intake handle must not make the server reach its own cloud-metadata
    endpoint (``169.254.169.254``), ``localhost``, or anything on the internal
    RFC-1918 network. EVERY address the host resolves to is checked, so a DNS
    name that points at a private IP is rejected too. Honors the
    ``migration_cloud.intake.block_private_network_fetch`` cascade flag (default
    on) so a sovereign / edge self-host that legitimately pulls from an internal
    host can opt out.
    """
    try:
        blocked = bool(mc_defaults.get("migration_cloud.intake.block_private_network_fetch"))
    except Exception:  # noqa: BLE001 — unknown key → safe default (block)
        blocked = True
    if not blocked:
        return
    host = urllib.parse.urlparse(url).hostname
    if not host:
        raise IntakeError(f"Intake URL has no host to validate: {url!r}")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise IntakeError(f"Could not resolve intake host {host!r}: {exc}") from exc
    for info in infos:
        raw_ip = info[4][0]
        # Strip an IPv6 zone id (e.g. 'fe80::1%eth0') before parsing.
        ip = ipaddress.ip_address(raw_ip.split("%", 1)[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise IntakeError(
                f"Refusing to fetch {host!r}: it resolves to non-public address "
                f"{ip} (SSRF guard). Allow internal fetches on a self-host "
                "deployment by setting the config flag "
                "migration_cloud.intake.block_private_network_fetch=false."
            )


class _SSRFGuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate the target host on every redirect hop.

    Without this, an allow-listed public URL that 30x-redirects to
    ``http://169.254.169.254/…`` would still reach the metadata endpoint — the
    classic open-redirect SSRF bypass. Raising ``IntakeError`` here is a
    permanent failure (never retried) because ``_fetch_http`` re-raises
    ``IntakeError`` ahead of its transient-retry wrapper.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        _assert_public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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

    fetcher = {
        "http": _fetch_http,
        "https": _fetch_http,
        "sftp": _fetch_sftp,
        "s3": _fetch_s3,
    }.get(scheme)
    if fetcher is None:
        _safe_unlink(tmp)
        raise IntakeError(f"URL scheme {scheme!r} is recognized but no fetcher is wired.")

    # Wire network_resilience.retry: a transient network hiccup on a large
    # remote pull now retries with exponential backoff + jitter instead of
    # failing the whole bundle on the first blip. Only ``_TransientFetchError``
    # is retried — a size-cap breach or a missing paramiko/boto3 raises plain
    # ``IntakeError`` and fails fast. Each attempt re-opens ``dest`` in "wb"
    # (full re-download), so no partial-append corruption.
    from apps.migration_cloud import network_resilience

    try:
        network_resilience.retry(
            fetcher,
            max_retries=_resilience_max_retries(),
            retry_on=(_TransientFetchError,),
        )(url, tmp, max_bytes)
    except Exception:
        _safe_unlink(tmp)
        raise
    return tmp


def _fetch_http(url: str, dest: Path, max_bytes: int) -> None:
    _assert_public_host(url)  # SSRF guard: block loopback/private/link-local before we connect.
    req = urllib.request.Request(url, headers={"User-Agent": "RunMyCampus-MigrationCloud/1.0"})
    opener = urllib.request.build_opener(_SSRFGuardedRedirectHandler())
    try:
        with opener.open(req, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as resp, dest.open("wb") as out:
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
    except Exception as exc:  # noqa: BLE001 — transient network failure → retryable
        raise _TransientFetchError(
            f"HTTP fetch failed for {url}: {type(exc).__name__}: {exc}"
        ) from exc


def _fetch_sftp(url: str, dest: Path, max_bytes: int) -> None:
    _assert_public_host(url)  # SSRF guard: block private/loopback/link-local SFTP targets.
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
    except Exception as exc:  # noqa: BLE001 — transient transport failure → retryable
        raise _TransientFetchError(
            f"SFTP fetch failed for {url}: {type(exc).__name__}: {exc}"
        ) from exc


def _fetch_s3(url: str, dest: Path, max_bytes: int) -> None:
    # No _assert_public_host here: an s3:// handle's netloc is a BUCKET name, not a
    # network host — boto3 resolves it to the AWS S3 endpoint, so there is no
    # attacker-controlled host to SSRF into. (The http/https + sftp fetchers ARE
    # guarded, since those take a real network host.)
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
    except Exception as exc:  # noqa: BLE001 — transient transport failure → retryable
        raise _TransientFetchError(
            f"S3 fetch failed for {url}: {type(exc).__name__}: {exc}"
        ) from exc


# Re-register so the upgraded adapter takes precedence over the Phase U1 stub.
for _method in (IntakeMethod.URL, IntakeMethod.SFTP, IntakeMethod.S3):
    register_adapter(_method, UrlIntakeAdapter())
