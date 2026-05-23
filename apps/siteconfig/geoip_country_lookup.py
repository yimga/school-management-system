"""
Wave 10 (v3.62.10 — 2026-05-22) — GeoIP-driven country resolution.

The existing country resolver chain
``apps.siteconfig.country_localization_service.resolve_country_for_request``
uses tenant.country → session → cookie → Accept-Language. This module adds an
OPTIONAL IP-based lookup that the chain consults when none of those signals
fired (configurable via env var; OFF by default).

Architecture (sister of the older `apps.siteconfig.geoip_service` cache
helper — both are intentionally separate; this one is read-only country
resolution, the other is the broader lat/lon cache layer):

  - Stdlib-only by default; no MaxMind dependency required at import time.
  - Lazy backend selection via env var ``RMC_GEOIP_BACKEND``:
      * ``"noop"`` (default)   — always returns ""
      * ``"cloudflare"``       — reads ``CF-IPCountry`` header (zero-config
                                  when deployed behind Cloudflare)
      * ``"x-country-code"``   — reads a custom ``X-Country-Code`` header
                                  ops can inject from an upstream WAF / LB
      * ``"maxmind-lite2"``    — reads ``GEOIP_COUNTRY_DATABASE_PATH`` env
                                  (.mmdb file); requires ``geoip2`` PyPI;
                                  auto-falls-back to noop with one-time
                                  WARNING if the package is missing or path
                                  is invalid
  - All backends fail-safe (return "" on any error).
  - PII safety: NEVER logs the raw IP; the IP only crosses a method boundary
    into the MaxMind reader, never into a logger or DB row.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_BACKEND_ENV = "RMC_GEOIP_BACKEND"
_DB_PATH_ENV = "GEOIP_COUNTRY_DATABASE_PATH"


def _selected_backend() -> str:
    return (os.environ.get(_BACKEND_ENV) or "noop").strip().lower()


def _client_ip(request) -> str:
    """Best-effort client IP extraction. NEVER raises."""
    try:
        xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
        if xff:
            for tok in xff.split(","):
                t = tok.strip()
                if t:
                    return t
        real = (request.META.get("HTTP_X_REAL_IP") or "").strip()
        if real:
            return real
        return (request.META.get("REMOTE_ADDR") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _normalize_cc(value: str) -> str:
    out = (value or "").strip().upper()
    if len(out) != 2 or not out.isascii() or not out.isalpha():
        return ""
    return out


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

def _lookup_cloudflare(request) -> str:
    try:
        return _normalize_cc(request.META.get("HTTP_CF_IPCOUNTRY", ""))
    except Exception:  # noqa: BLE001
        return ""


def _lookup_x_country_code(request) -> str:
    try:
        return _normalize_cc(request.META.get("HTTP_X_COUNTRY_CODE", ""))
    except Exception:  # noqa: BLE001
        return ""


_MAXMIND_READER = None
_MAXMIND_INIT_FAILED = False


def _lookup_maxmind_lite2(request) -> str:
    """MaxMind GeoLite2 country lookup via geoip2. Lazy + cached + fail-open."""
    global _MAXMIND_READER, _MAXMIND_INIT_FAILED
    if _MAXMIND_INIT_FAILED:
        return ""
    if _MAXMIND_READER is None:
        try:
            import geoip2.database  # type: ignore
        except ImportError:
            logger.warning(
                "GeoIP backend 'maxmind-lite2' selected but `geoip2` package "
                "is not installed. Falling back to noop. `pip install geoip2`."
            )
            _MAXMIND_INIT_FAILED = True
            return ""
        db_path = (os.environ.get(_DB_PATH_ENV) or "").strip()
        if not db_path or not os.path.isfile(db_path):
            logger.warning(
                "GeoIP backend 'maxmind-lite2' selected but %s is empty or "
                "the file does not exist. Falling back to noop.", _DB_PATH_ENV,
            )
            _MAXMIND_INIT_FAILED = True
            return ""
        try:
            _MAXMIND_READER = geoip2.database.Reader(db_path)
        except Exception:  # noqa: BLE001
            logger.exception(
                "GeoIP backend 'maxmind-lite2' failed to open database; "
                "falling back to noop."
            )
            _MAXMIND_INIT_FAILED = True
            return ""

    ip = _client_ip(request)
    if not ip:
        return ""
    try:
        result = _MAXMIND_READER.country(ip)
        cc = getattr(getattr(result, "country", None), "iso_code", "") or ""
        return _normalize_cc(cc)
    except Exception:  # noqa: BLE001 — AddressNotFoundError / etc.
        return ""


_BACKEND_DISPATCH = {
    "noop":           lambda _req: "",
    "cloudflare":     _lookup_cloudflare,
    "x-country-code": _lookup_x_country_code,
    "maxmind-lite2":  _lookup_maxmind_lite2,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup_country(request) -> str:
    """Return the visitor's ISO 3166-1 alpha-2 country code from GeoIP.

    Returns "" when backend is noop / not configured / cannot resolve.
    Never raises.
    """
    if request is None:
        return ""
    backend = _selected_backend()
    handler = _BACKEND_DISPATCH.get(backend)
    if handler is None:
        logger.warning(
            "GeoIP backend '%s' unknown; valid options: %s. Using noop.",
            backend, ", ".join(sorted(_BACKEND_DISPATCH.keys())),
        )
        return ""
    try:
        return handler(request) or ""
    except Exception:  # noqa: BLE001
        return ""


def reset_cache_for_tests() -> None:
    """Test helper — clear cached MaxMind reader."""
    global _MAXMIND_READER, _MAXMIND_INIT_FAILED
    if _MAXMIND_READER is not None:
        try:
            _MAXMIND_READER.close()
        except Exception:  # noqa: BLE001
            pass
    _MAXMIND_READER = None
    _MAXMIND_INIT_FAILED = False
