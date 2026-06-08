#!/usr/bin/env python3
"""Vendor pinned Tesseract.js browser OCR assets with checksums."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE_MODULES = ROOT / "node_modules"
DESTINATION = ROOT / "static" / "js" / "vendor" / "tesseract"

ASSETS = {
    "tesseract.min.js": NODE_MODULES
    / "tesseract.js"
    / "dist"
    / "tesseract.min.js",
    "worker.min.js": NODE_MODULES / "tesseract.js" / "dist" / "worker.min.js",
    "tesseract-core-lstm.wasm.js": NODE_MODULES
    / "tesseract.js-core"
    / "tesseract-core-lstm.wasm.js",
    "tesseract-core-simd-lstm.wasm.js": NODE_MODULES
    / "tesseract.js-core"
    / "tesseract-core-simd-lstm.wasm.js",
    "tesseract-core-relaxedsimd-lstm.wasm.js": NODE_MODULES
    / "tesseract.js-core"
    / "tesseract-core-relaxedsimd-lstm.wasm.js",
    "eng.traineddata.gz": NODE_MODULES
    / "@tesseract.js-data"
    / "eng"
    / "4.0.0"
    / "eng.traineddata.gz",
    "LICENSE.tesseract-js.txt": NODE_MODULES / "tesseract.js" / "LICENSE.md",
    "LICENSE.tesseract-core.txt": NODE_MODULES
    / "tesseract.js-core"
    / "LICENSE",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    missing = [str(path) for path in ASSETS.values() if not path.is_file()]
    if missing:
        print("TESSERACT_VENDOR_FAIL")
        for path in missing:
            print(f"  - missing {path}")
        return 1

    DESTINATION.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "package": "tesseract.js",
        "version": "7.0.0",
        "language": "eng",
        "language_data_package": "@tesseract.js-data/eng@1.0.0",
        "assets": {},
    }
    for name, source in ASSETS.items():
        target = DESTINATION / name
        shutil.copyfile(source, target)
        manifest["assets"][name] = {
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
        }
    (DESTINATION / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "TESSERACT_VENDOR_PASS "
        f"assets={len(ASSETS)} bytes="
        f"{sum(row['bytes'] for row in manifest['assets'].values())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
