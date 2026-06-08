#!/usr/bin/env python3
"""Fail deploy when the manager WebGL globe bundle is missing from disk or staticfiles.

The bundle lives under static/js/dist/ (gitignored) and must be built via npm on deploy.
Exit 0 + WORLD_GLOBE_STATICFILES_DEPLOY_PASS when checks pass.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MOUNT = ROOT / "static/js/dist/world-globe.mount.js"
MIN_BYTES = 500_000


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(msg)


def _assert_single_bundle(path: Path) -> None:
    head = path.read_text(encoding="utf-8", errors="replace")[:800]
    if "./world-globe.vendor-" in head or 'from"./world-globe' in head:
        _fail(f"{path}: expected single-file bundle (found relative vendor chunk imports)")


def _assert_no_retired_vendor_chunks() -> None:
    dist = ROOT / "static/js/dist"
    if not dist.is_dir():
        return
    stale = sorted(p.name for p in dist.iterdir() if p.is_file() and p.name.startswith("world-globe.vendor-"))
    if stale:
        _fail(f"retired globe vendor chunks still on disk: {', '.join(stale)} — run scripts/purge_retired_globe_vendor_chunks.py")


def verify_source() -> None:
    if not SOURCE_MOUNT.is_file():
        _fail(
            "static/js/dist/world-globe.mount.js missing — run npm run build:world-globe in build.sh"
        )
    size = SOURCE_MOUNT.stat().st_size
    if size < MIN_BYTES:
        _fail(f"world-globe.mount.js too small ({size} bytes) — rebuild with npm run build:world-globe")
    _assert_single_bundle(SOURCE_MOUNT)
    _assert_no_retired_vendor_chunks()


def verify_staticfiles() -> None:
    sf_dir = ROOT / "staticfiles/js/dist"
    if not sf_dir.is_dir():
        _fail("staticfiles/js/dist/ missing — collectstatic did not run or globe bundle was not built")
    mounts = sorted(sf_dir.glob("world-globe.mount*.js"))
    if not mounts:
        _fail("staticfiles has no world-globe.mount*.js after collectstatic")
    if max(p.stat().st_size for p in mounts) < MIN_BYTES:
        _fail("collected world-globe.mount.js too small — globe build step likely skipped on deploy")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        action="store_true",
        help="Verify built source under static/js/dist/ (build.sh after npm build)",
    )
    parser.add_argument(
        "--staticfiles",
        action="store_true",
        help="Verify collected staticfiles/ after collectstatic (Render predeploy)",
    )
    args = parser.parse_args()
    if not args.source and not args.staticfiles:
        verify_source()
        return 0
    if args.source:
        verify_source()
    if args.staticfiles:
        verify_staticfiles()
    _ok("WORLD_GLOBE_STATICFILES_DEPLOY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
