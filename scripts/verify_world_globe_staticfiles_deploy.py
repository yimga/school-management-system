#!/usr/bin/env python3
"""Fail deploy when the manager WebGL globe bundle is missing from disk or staticfiles.

The bundle lives under static/js/dist/ (gitignored) and must be built via npm on deploy.
Exit 0 + WORLD_GLOBE_STATICFILES_DEPLOY_PASS when checks pass.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MOUNT = ROOT / "static/js/dist/world-globe.mount.js"
SOURCE_TEXTURE = ROOT / "static/img/globe/earth-night-1k.jpg"
MIN_BYTES = 500_000
MIN_TEXTURE_BYTES = 40_000


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(msg)


def _assert_single_bundle(path: Path) -> None:
    head = path.read_text(encoding="utf-8", errors="replace")[:800]
    if "./world-globe.vendor-" in head or 'from"./world-globe' in head:
        _fail(f"{path}: expected single-file bundle (found relative vendor chunk imports)")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _assert_daylight_bundle(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    required = ("globeImageUrl", "#020612")
    missing = [needle for needle in required if needle not in text]
    if missing:
        _fail(f"{path}: missing daylight globe material markers: {', '.join(missing)}")
    if ".045" not in text and "0.045" not in text:
        _fail(f"{path}: missing low-emissive daylight material intensity")


def _assert_daylight_texture(path: Path) -> None:
    if not path.is_file():
        _fail(f"{path}: globe daylight texture missing")
    size = path.stat().st_size
    if size < MIN_TEXTURE_BYTES:
        _fail(f"{path}: globe texture too small ({size} bytes) — stale purple texture likely collected")
    try:
        from PIL import Image
    except ImportError as exc:
        _fail(f"Pillow required to verify globe texture visual profile: {exc}")

    with Image.open(path) as img:
        rgb = img.convert("RGB").resize((96, 48))
        counts = {"ocean": 0, "green": 0, "desert": 0, "purple": 0}
        pixel_iter = rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata()
        for r, g, b in pixel_iter:
            if b > r + 20 and b > g + 5:
                counts["ocean"] += 1
            if g > r * 0.8 and g > b * 0.8 and 35 <= g <= 150:
                counts["green"] += 1
            if r > g * 1.05 and g > b * 1.05 and r > 120:
                counts["desert"] += 1
            if b > 70 and r > 45 and abs(r - b) < 70 and g < b * 0.85:
                counts["purple"] += 1
    if counts["green"] < 90 or counts["desert"] < 90 or counts["ocean"] < 1_000:
        _fail(f"{path}: daylight earth texture profile too weak: {counts}")
    if counts["purple"] > 220:
        _fail(f"{path}: texture still reads purple instead of earth daylight: {counts}")


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
    _assert_daylight_bundle(SOURCE_MOUNT)
    _assert_daylight_texture(SOURCE_TEXTURE)
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
    source_hash = _sha256(SOURCE_MOUNT)
    collected_plain = sf_dir / "world-globe.mount.js"
    if not collected_plain.is_file():
        _fail("staticfiles/js/dist/world-globe.mount.js missing after collectstatic")
    if _sha256(collected_plain) != source_hash:
        _fail("staticfiles world-globe.mount.js is stale vs static/js/dist/world-globe.mount.js")
    if all(_sha256(p) != source_hash for p in mounts):
        _fail("staticfiles has no collected world-globe bundle matching the current source build")

    sf_texture = ROOT / "staticfiles/img/globe/earth-night-1k.jpg"
    _assert_daylight_texture(sf_texture)
    if _sha256(sf_texture) != _sha256(SOURCE_TEXTURE):
        _fail("staticfiles globe daylight texture is stale vs static/img/globe/earth-night-1k.jpg")


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
