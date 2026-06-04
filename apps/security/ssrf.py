"""SSRF guard: validate that an outbound URL points at a public host.

Used by every code path that fetches or POSTs to a user/tenant-supplied URL
(webhook subscriptions, brand import, etc.). Blocks private / loopback /
link-local (incl. the 169.254.169.254 cloud-metadata endpoint) / reserved /
multicast targets by resolving the hostname and checking EVERY resolved IP.

This is a resolve-then-check guard. It is not a complete DNS-rebinding defense on
its own (a name could resolve differently between this check and the actual
connect); callers that need that should additionally pin/connect to a validated
IP. For our threat model (a tenant registering a malicious target) checking at
both registration time and delivery time closes the practical hole.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def _ip_blocked(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable → treat as unsafe
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local      # 169.254.0.0/16 (cloud metadata) + fe80::/10
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_safe_public_url(url: str, *, allow_http: bool = False) -> tuple[bool, str]:
    """Return ``(ok, reason)``. ``ok`` is True only for a public http(s) target."""
    if not url or not isinstance(url, str):
        return False, "empty_url"
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, "bad_scheme"
    if scheme == "http" and not allow_http:
        return False, "http_not_allowed"
    host = parsed.hostname
    if not host:
        return False, "no_host"
    port = parsed.port or (443 if scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError, ValueError):
        return False, "dns_failed"
    if not infos:
        return False, "dns_empty"
    for info in infos:
        ip_str = info[4][0]
        if _ip_blocked(ip_str):
            return False, "private_or_blocked_ip"
    return True, ""


__all__ = ["is_safe_public_url"]
