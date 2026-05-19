#!/usr/bin/env python
"""Upstream compatibility watch for ``django-cryptography`` (v3.34.0 Agent 5).

Why this exists
---------------
RunMyCampus's legacy-hash encryption layer (``apps/accounts/legacy_hashes/
encryption.py``) currently reports backend ``internal_fernet_shim``
because upstream ``django-cryptography`` 1.x imports
``django.utils.baseconv``, which was removed in Django 5. The shim is a
HONEST FALLBACK — same crypto strength (AES-128-CBC + HMAC-SHA256), but
maintenance + audit reviewers prefer the upstream implementation.

This watch script polls PyPI weekly (via the Celery beat schedule
``upstream-watch-django-cryptography``) for new releases of
``django-cryptography`` and inspects each release's sdist for any
remaining reference to ``django.utils.baseconv``. The script is a
**watch**, not a CI gate — it always exits 0 and writes its findings
to ``var/upstream-watch/django-cryptography-<timestamp>.json`` for the
audit trail. The Celery wrapper (apps/accounts/tasks.py::
watch_django_cryptography_upstream) optionally emails ops when a
compatible version lands.

Operator workflow when compatibility is detected
-------------------------------------------------
1. Receive the watch email.
2. Inspect the JSON audit trail at ``var/upstream-watch/...``.
3. Manually verify the candidate release in a test environment
   (install ``django-cryptography==<version>`` and run the test suite).
4. Bump ``requirements.txt`` and follow the data-migration plan in
   ``docs/SECURITY_KEYS.md`` § "Internal Fernet Shim Migration Plan".

Safety
------
* No third-party HTTP libraries — stdlib ``urllib.request`` only.
* No authentication credentials are ever included in fetches.
* Redirect chain is bounded to 3 hops.
* All HTTP fetches carry a 30-second timeout.
* The PyPI public JSON API is the only host contacted; nothing about
  this script writes to PyPI (read-only watch).

Exit codes
----------
* 0 always (watch, not a gate). Errors are recorded in the audit JSON
  with ``error_class`` + ``error_message`` fields, and emitted to
  stderr for the operator.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import logging
import pathlib
import re
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from typing import Any

logger = logging.getLogger(__name__)

# magic-number-allow: well-known PyPI metadata host plus version pin
PYPI_JSON_URL = "https://pypi.org/pypi/django-cryptography/json"

# Versions known to depend on django.utils.baseconv (Django <5 only).
KNOWN_INCOMPATIBLE_MAX = "1.1.0"

# The version we predict will land Django-5 compatibility. Operators
# bump this as upstream announces.
KNOWN_COMPATIBLE_BASE = "1.2.0"

HTTP_TIMEOUT_SECONDS = 30  # magic-number-allow: bounded fetch timeout
MAX_REDIRECTS = 3  # magic-number-allow: hop ceiling
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024  # magic-number-allow: 5 MiB safety cap

BASECONV_PATTERNS = (
    re.compile(rb"django\.utils\.baseconv"),
    re.compile(rb"from\s+django\.utils\s+import\s+baseconv"),
)


def _parse_version(version: str) -> tuple[int, ...]:
    """Best-effort PEP 440-ish parse. Returns a tuple of ints.

    Pre-release / dev-release suffixes are stripped so the tuple is
    suitable for ``<`` / ``>`` comparison among the small set of
    release versions we expect. Returns ``(0,)`` on parse failure so
    such entries sort first (effectively ignored).
    """
    digits: list[int] = []
    for chunk in version.split("."):
        m = re.match(r"^\d+", chunk)
        if not m:
            break
        digits.append(int(m.group(0)))
    return tuple(digits) if digits else (0,)


def _fetch_with_limit(url: str, *, max_bytes: int = MAX_DOWNLOAD_BYTES) -> bytes:
    """Fetch ``url`` returning at most ``max_bytes`` of body.

    Uses stdlib only. Caps redirects via a custom handler. Raises
    ``urllib.error.HTTPError`` / ``URLError`` on transport failures —
    callers convert these into recorded errors in the audit JSON.
    """

    class _CappedRedirect(urllib.request.HTTPRedirectHandler):
        max_redirections = MAX_REDIRECTS

    opener = urllib.request.build_opener(_CappedRedirect())
    req = urllib.request.Request(url, headers={"User-Agent": "rmc-upstream-watch/1.0"})
    with opener.open(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"response from {url!r} exceeds {max_bytes}-byte cap")
    return data


def _list_release_versions(metadata: dict[str, Any]) -> list[str]:
    """Return release version strings from the PyPI JSON metadata.

    PyPI's ``releases`` key maps version -> list of file dicts; we
    drop any entry whose file list is empty (yanked or skeleton).
    """
    releases = metadata.get("releases") or {}
    out = []
    for v, files in releases.items():
        if isinstance(files, list) and len(files) > 0:
            out.append(v)
    out.sort(key=_parse_version)
    return out


def _select_sdist_url(metadata: dict[str, Any], version: str) -> str | None:
    """Find a source-distribution URL for the given release version.

    Falls back to a wheel if no sdist exists; wheel ``METADATA`` /
    source-extracted .py files still let us grep for the baseconv
    import.
    """
    files = (metadata.get("releases") or {}).get(version) or []
    sdist_url: str | None = None
    wheel_url: str | None = None
    for f in files:
        if not isinstance(f, dict):
            continue
        url = f.get("url")
        packagetype = f.get("packagetype")
        if not url:
            continue
        if packagetype == "sdist" and sdist_url is None:
            sdist_url = url
        elif packagetype == "bdist_wheel" and wheel_url is None:
            wheel_url = url
    return sdist_url or wheel_url


def _archive_contains_baseconv(archive_bytes: bytes, url: str) -> bool:
    """Return True if any file inside the archive references baseconv.

    Supports .tar.gz / .tgz (sdist) and .whl (zip). Other formats fall
    through as 'unknown' — recorded as a separate audit-trail entry.
    """
    if url.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                if not member.name.endswith((".py", ".cfg", ".toml")):
                    continue
                try:
                    extracted = tf.extractfile(member)
                except KeyError:
                    continue
                if extracted is None:
                    continue
                content = extracted.read()
                if any(p.search(content) for p in BASECONV_PATTERNS):
                    return True
        return False
    if url.endswith(".whl"):
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            for name in zf.namelist():
                if not name.endswith((".py", ".cfg", ".toml", "METADATA")):
                    continue
                content = zf.read(name)
                if any(p.search(content) for p in BASECONV_PATTERNS):
                    return True
        return False
    # Unknown archive type — operator inspects manually.
    raise ValueError(f"unrecognised archive extension for {url!r}")


def _evaluate_version(metadata: dict[str, Any], version: str) -> dict[str, Any]:
    """Inspect ``version``'s archive for baseconv references.

    Returns a structured record suitable for JSON serialization. On any
    transport / parse error the record carries ``error_class`` +
    ``error_message`` and the operator does the manual lookup.
    """
    record: dict[str, Any] = {
        "version": version,
        "archive_url": None,
        "compatible_with_django_5": None,
        "verdict": None,
        "error_class": None,
        "error_message": None,
    }
    url = _select_sdist_url(metadata, version)
    record["archive_url"] = url
    if url is None:
        record["verdict"] = "no_archive_url"
        record["error_message"] = "no sdist or wheel URL in PyPI metadata"
        return record
    try:
        archive_bytes = _fetch_with_limit(url)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
        record["error_class"] = type(exc).__name__
        record["error_message"] = str(exc)
        record["verdict"] = "fetch_failed"
        return record
    try:
        has_baseconv = _archive_contains_baseconv(archive_bytes, url)
    except (tarfile.TarError, zipfile.BadZipFile, ValueError) as exc:
        record["error_class"] = type(exc).__name__
        record["error_message"] = str(exc)
        record["verdict"] = "archive_unreadable"
        return record
    record["compatible_with_django_5"] = not has_baseconv
    record["verdict"] = "compatible" if not has_baseconv else "blocked"
    return record


def _write_audit_trail(
    repo_root: pathlib.Path, payload: dict[str, Any]
) -> pathlib.Path:
    target_dir = repo_root / "var" / "upstream-watch"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"django-cryptography-{timestamp}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[1],
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--min-version",
        default=KNOWN_COMPATIBLE_BASE,
        help=(
            "Only evaluate versions >= this value (default: "
            f"{KNOWN_COMPATIBLE_BASE} — the predicted compat baseline)"
        ),
    )
    args = parser.parse_args(argv)

    payload: dict[str, Any] = {
        "watched_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "pypi_url": PYPI_JSON_URL,
        "min_version": args.min_version,
        "known_incompatible_max": KNOWN_INCOMPATIBLE_MAX,
        "known_compatible_base": KNOWN_COMPATIBLE_BASE,
        "evaluations": [],
        "summary_lines": [],
    }

    try:
        raw = _fetch_with_limit(PYPI_JSON_URL)
        metadata = json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
        payload["fetch_error_class"] = type(exc).__name__
        payload["fetch_error_message"] = str(exc)
        payload["summary_lines"].append(
            f"ERROR: failed to fetch PyPI metadata: {type(exc).__name__}: {exc}"
        )
        sys.stderr.write(payload["summary_lines"][-1] + "\n")
        _write_audit_trail(args.repo_root, payload)
        return 0  # watch never gates CI

    versions = _list_release_versions(metadata)
    min_tuple = _parse_version(args.min_version)
    interesting = [v for v in versions if _parse_version(v) >= min_tuple]
    payload["total_releases"] = len(versions)
    payload["candidate_count"] = len(interesting)

    if not interesting:
        payload["summary_lines"].append(
            f"No releases >= {args.min_version} on PyPI yet "
            f"(latest: {versions[-1] if versions else 'unknown'})."
        )
    for v in interesting:
        record = _evaluate_version(metadata, v)
        payload["evaluations"].append(record)
        if record["verdict"] == "compatible":
            line = (
                f"COMPAT: django-cryptography {v} appears Django-5-compatible "
                "— manual verification recommended"
            )
        elif record["verdict"] == "blocked":
            line = (
                f"BLOCKED: django-cryptography {v} still depends on "
                "django.utils.baseconv"
            )
        else:
            line = (
                f"UNKNOWN: django-cryptography {v}: "
                f"{record['verdict']} ({record.get('error_message')})"
            )
        payload["summary_lines"].append(line)
        sys.stdout.write(line + "\n")

    audit_path = _write_audit_trail(args.repo_root, payload)
    sys.stdout.write(f"audit trail written: {audit_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
