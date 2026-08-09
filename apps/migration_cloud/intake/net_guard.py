"""Shared SSRF / egress guard for Migration Cloud server-side fetchers.

Single source of truth for the "refuse a server-side fetch to a non-public
host" policy. Three fetchers pull bytes from a caller-influenced location and
MUST route through this module:

  * ``intake/url_intake.py``    — remote artifact pull (http/sftp/s3).
  * ``intake/api_pull_intake.py`` — authorized vendor REST export.
  * ``asset_pipeline.py``       — binary asset fetch (student photos, PDFs)
    whose ``source_uri`` comes straight off a migrated SIS row.

Before this module the policy lived only in ``url_intake``; the other two were
unmirrored SSRF holes — a tenant-supplied ``photo_url`` of
``http://169.254.169.254/…`` reached the cloud-metadata endpoint, and an
``api_pull`` URL shipped its ``Authorization: Bearer`` token to an
attacker-chosen host. Centralizing here means one guard, one config flag, no
drift between the fetchers.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse
import urllib.request

from apps.migration_cloud import defaults as mc_defaults

from .base import IntakeError

_DEFAULT_UA = "RunMyCampus-MigrationCloud/1.0"
_DEFAULT_TIMEOUT_SECONDS = 30
_CHUNK = 1024 * 1024


def assert_public_host(url: str) -> None:
    """Refuse a URL whose host resolves to a non-public address (SSRF guard).

    A caller-supplied fetch target must not make the server reach its own
    cloud-metadata endpoint (``169.254.169.254``), ``localhost``, or anything
    on the internal RFC-1918 network. EVERY address the host resolves to is
    checked, so a DNS name that points at a private IP is rejected too. Honors
    the ``migration_cloud.intake.block_private_network_fetch`` cascade flag
    (default on) so a sovereign / edge self-host that legitimately pulls from
    an internal host can opt out.
    """
    try:
        blocked = bool(mc_defaults.get("migration_cloud.intake.block_private_network_fetch"))
    except Exception:  # noqa: BLE001 — unknown key → safe default (block)
        blocked = True
    if not blocked:
        return
    host = urllib.parse.urlparse(url).hostname
    if not host:
        raise IntakeError(f"Fetch URL has no host to validate: {url!r}")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise IntakeError(f"Could not resolve fetch host {host!r}: {exc}") from exc
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


class SSRFGuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate the target host on every redirect hop.

    Without this, an allow-listed public URL that 30x-redirects to
    ``http://169.254.169.254/…`` would still reach the metadata endpoint — the
    classic open-redirect SSRF bypass. Raising ``IntakeError`` here is a
    permanent failure; callers re-raise ``IntakeError`` ahead of any
    transient-retry wrapper.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        assert_public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_http_capped(
    url: str,
    *,
    max_bytes: int,
    timeout: float | None = None,
    headers: dict | None = None,
    method: str = "GET",
) -> tuple[bytes, str]:
    """SSRF-guarded HTTP(S) GET returning ``(content_bytes, content_type)``.

    The host is validated as public BEFORE the request is built — so any
    caller-supplied auth header is never sent to a blocked target — and every
    redirect hop is re-validated. The body is streamed with a hard ``max_bytes``
    cap so a hostile server cannot exhaust worker memory. Raises ``IntakeError``
    on a blocked host, an oversize body, or any transport failure.
    """
    assert_public_host(url)
    req = urllib.request.Request(
        url,
        headers=headers or {"User-Agent": _DEFAULT_UA},
        method=method,
    )
    opener = urllib.request.build_opener(SSRFGuardedRedirectHandler())
    to = timeout if timeout is not None else _DEFAULT_TIMEOUT_SECONDS
    try:
        with opener.open(req, timeout=to) as resp:
            content_type = (
                (resp.headers.get("Content-Type", "") or "").split(";")[0].strip()
            )
            buf = bytearray()
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > max_bytes:
                    raise IntakeError(
                        f"Fetch exceeded byte cap ({max_bytes:,} bytes): {url!r}"
                    )
            return bytes(buf), content_type
    except IntakeError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize transport failures
        raise IntakeError(
            f"HTTP fetch failed for {url!r}: {type(exc).__name__}: {exc}"
        ) from exc


__all__ = [
    "assert_public_host",
    "SSRFGuardedRedirectHandler",
    "fetch_http_capped",
]
