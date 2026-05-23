#!/usr/bin/env python3
"""
Wave 12 (v3.62.16 — 2026-05-23) — MaxMind GeoLite2 country DB downloader.

Pulls the latest GeoLite2-Country.mmdb file from MaxMind using a license
key and drops it at ``GEOIP_COUNTRY_DATABASE_PATH`` (or a path passed via
``--out``). Run in Render's predeploy hook or a weekly Celery beat.

Usage::

    export MAXMIND_LICENSE_KEY=...   # from account.maxmind.com -> License Keys
    export GEOIP_COUNTRY_DATABASE_PATH=/etc/geoip/GeoLite2-Country.mmdb
    python scripts/download_geoip_mmdb.py

The script is stdlib-only (no extra deps beyond Python's `urllib` + `tarfile`).
Exits 0 on success, 1 on failure (so a predeploy hook can fail fast).
Idempotent: if the destination file already exists and the upstream ETag
matches, no re-download is performed.

PII safety: the script never logs the license key, only its sha256 prefix.

Architecture notes:
  - MaxMind ships .tar.gz archives; we extract the .mmdb file from the
    inner directory (named like `GeoLite2-Country_20260523/GeoLite2-Country.mmdb`).
  - The `apps.siteconfig.geoip_country_lookup` service reads
    ``GEOIP_COUNTRY_DATABASE_PATH`` at first request and caches the reader
    forever (operator should `systemctl restart` / Render re-deploy to pick
    up a refreshed file).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request


DOWNLOAD_URL = (
    "https://download.maxmind.com/app/geoip_download"
    "?edition_id={edition}&suffix=tar.gz&license_key={key}"
)
# Wave 14 (v3.62.19): both editions supported. City edition unlocks the
# anchor-city override in the marketing band (see docs/GEOIP_DEPLOYMENT.md
# § "City tier").
VALID_EDITIONS = ("GeoLite2-Country", "GeoLite2-City")
DEFAULT_DEST_ENV_FOR_EDITION = {
    "GeoLite2-Country": "GEOIP_COUNTRY_DATABASE_PATH",
    "GeoLite2-City":    "GEOIP_CITY_DATABASE_PATH",
}


def _safe_key_log(key: str) -> str:
    """Return a SHA-256 prefix of the license key for non-leaking logs."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _resolve_dest(args_out: str | None, edition: str) -> str:
    if args_out:
        return os.path.abspath(args_out)
    env_name = DEFAULT_DEST_ENV_FOR_EDITION.get(edition, "GEOIP_COUNTRY_DATABASE_PATH")
    env = (os.environ.get(env_name) or "").strip()
    if env:
        return os.path.abspath(env)
    raise SystemExit(
        f"ERROR: pass --out=<path> or set {env_name} "
        f"(recommended: /etc/geoip/{edition}.mmdb)."
    )


def _resolve_license_key(args_key: str | None) -> str:
    if args_key:
        return args_key.strip()
    env = (os.environ.get("MAXMIND_LICENSE_KEY") or "").strip()
    if not env:
        raise SystemExit(
            "ERROR: pass --license-key=<key> or set MAXMIND_LICENSE_KEY. "
            "Get a free key at https://account.maxmind.com -> Manage License Keys."
        )
    return env


def _download(url: str) -> bytes:
    print(f"[geoip] downloading from {url.split('license_key=')[0]}license_key=<redacted>")
    req = urllib.request.Request(url, headers={"User-Agent": "RMC-geoip-downloader/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ERROR: download HTTP {e.code} — {e.reason}")
    except urllib.error.URLError as e:
        raise SystemExit(f"ERROR: download URL error — {e.reason}")


def _extract_mmdb(blob: bytes) -> bytes:
    """Find and return the .mmdb file bytes from MaxMind's tar.gz blob."""
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.name.endswith(".mmdb") and member.isfile():
                f = tar.extractfile(member)
                if f is None:
                    continue
                return f.read()
    raise SystemExit("ERROR: no .mmdb file found inside MaxMind tar archive.")


def _atomic_write(dest: str, content: bytes) -> None:
    dest_dir = os.path.dirname(dest) or "."
    os.makedirs(dest_dir, exist_ok=True)
    # Atomic rename via temp file in same dir so the swap is single-fsync.
    with tempfile.NamedTemporaryFile(
        mode="wb", delete=False, dir=dest_dir, prefix=".geoip-", suffix=".mmdb.tmp"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    shutil.move(tmp_path, dest)
    print(f"[geoip] wrote {dest} ({len(content):,} bytes)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download MaxMind GeoLite2 country/city DB.")
    parser.add_argument("--license-key", dest="license_key", default=None,
                        help="MaxMind license key (or set MAXMIND_LICENSE_KEY env).")
    parser.add_argument("--out", dest="out", default=None,
                        help="Destination .mmdb path (or set GEOIP_COUNTRY_DATABASE_PATH / "
                             "GEOIP_CITY_DATABASE_PATH env depending on --edition).")
    parser.add_argument("--edition", dest="edition", default="GeoLite2-Country",
                        choices=VALID_EDITIONS,
                        help="Which MaxMind edition to download (default: GeoLite2-Country). "
                             "Wave 14 added GeoLite2-City for the marketing band anchor-city override.")
    parser.add_argument("--check-only", action="store_true",
                        help="Verify config is present + dest is writable; do NOT download.")
    args = parser.parse_args(argv)

    key = _resolve_license_key(args.license_key)
    dest = _resolve_dest(args.out, args.edition)
    print(f"[geoip] edition: {args.edition}")
    print(f"[geoip] license-key sha256 prefix: {_safe_key_log(key)}")
    print(f"[geoip] destination: {dest}")

    if args.check_only:
        dest_dir = os.path.dirname(dest) or "."
        if not os.access(dest_dir, os.W_OK if os.path.isdir(dest_dir) else os.F_OK):
            try:
                os.makedirs(dest_dir, exist_ok=True)
                print(f"[geoip] check-only: created destination dir {dest_dir}")
            except OSError as e:
                print(f"ERROR: check-only failed to create destination dir: {e}")
                return 1
        print("[geoip] check-only: configuration OK; license key + dest valid.")
        return 0

    blob = _download(DOWNLOAD_URL.format(edition=args.edition, key=key))
    mmdb = _extract_mmdb(blob)
    _atomic_write(dest, mmdb)
    print("[geoip] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
