#!/usr/bin/env python3
"""Build deferred portal shell CSS bundle (mirrors marketing bundle builder).

Usage:
  python scripts/build_portal_css_bundles.py
  python scripts/build_portal_css_bundles.py --check
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(__file__).resolve().parent / "portal_css_bundle_manifest.json"
OUT_ENHANCED = REPO / "static" / "css" / "portal-shell-enhanced.min.css"
OUT_HASH_MANIFEST = REPO / "static" / "css" / "portal-bundles.manifest.json"


def _load_minify():
    marketing_builder = REPO / "scripts" / "build_marketing_css_bundles.py"
    spec = importlib.util.spec_from_file_location("build_marketing_css_bundles", marketing_builder)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module._minify_css, module._file_sha256, module._build_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    minify_css, file_sha256, build_bundle = _load_minify()
    spec = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    enhanced_css, enhanced_sources = build_bundle(spec["enhanced"], "portal-enhanced")

    out_manifest = {
        "version": spec.get("version"),
        "generated_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enhanced": {
            "path": "static/css/portal-shell-enhanced.min.css",
            "bytes": len(enhanced_css.encode("utf-8")),
            "sources": enhanced_sources,
        },
        "budgets": spec.get("size_budget_bytes", {}),
    }

    if args.check:
        stale = (
            not OUT_ENHANCED.is_file()
            or OUT_ENHANCED.read_text(encoding="utf-8") != enhanced_css
            or not OUT_HASH_MANIFEST.is_file()
        )
        if stale:
            print(
                "portal CSS bundle stale — run: python scripts/build_portal_css_bundles.py",
                file=sys.stderr,
            )
            return 1
        stored = json.loads(OUT_HASH_MANIFEST.read_text(encoding="utf-8"))
        if stored.get("enhanced", {}).get("sources") != enhanced_sources:
            print("portal-bundles.manifest.json stale (enhanced sources)", file=sys.stderr)
            return 1
        enh_bytes = int(out_manifest["enhanced"]["bytes"])
        enh_max = int(spec.get("size_budget_bytes", {}).get("enhanced_max", 0) or 0)
        if enh_max and enh_bytes > enh_max:
            print(
                f"portal enhanced bundle {enh_bytes}B exceeds budget {enh_max}B",
                file=sys.stderr,
            )
            return 1
        print(f"portal CSS bundle fresh (enhanced={enh_bytes}B)")
        return 0

    OUT_ENHANCED.parent.mkdir(parents=True, exist_ok=True)
    OUT_ENHANCED.write_text(enhanced_css, encoding="utf-8")
    OUT_HASH_MANIFEST.write_text(
        json.dumps(out_manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {OUT_ENHANCED.name} ({out_manifest['enhanced']['bytes']} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
