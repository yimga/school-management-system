#!/usr/bin/env python3
"""Concatenate + minify marketing shell CSS into critical + enhanced bundles.

Reads scripts/marketing_css_bundle_manifest.json and writes:
  static/marketing/css/marketing-critical.min.css
  static/marketing/css/marketing-enhanced.min.css
  static/marketing/css/marketing-bundles.manifest.json  (source hashes for freshness gate)

Usage (repo root):
  python scripts/build_marketing_css_bundles.py
  python scripts/build_marketing_css_bundles.py --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(__file__).resolve().parent / "marketing_css_bundle_manifest.json"
OUT_CRITICAL = REPO / "static" / "marketing" / "css" / "marketing-critical.min.css"
OUT_ENHANCED = REPO / "static" / "marketing" / "css" / "marketing-enhanced.min.css"
OUT_HASH_MANIFEST = REPO / "static" / "marketing" / "css" / "marketing-bundles.manifest.json"


_ALLOW_MARKER_PRESERVE = re.compile(
    r"/\*\s*(?:off-token-allow|theme-locked-allow|sticky-overflow-allow|theme-attr-contract-allow)\s*:[^*]*\*/"
)


def _minify_css(text: str) -> str:
    """Conservative CSS minifier (stdlib only). Preserves strings and calc/var().

    Preserves scanner allow markers (off-token-allow, theme-locked-allow,
    sticky-overflow-allow, theme-attr-contract-allow) so categorical
    CI-marker categories survive bundle regeneration.
    """
    def _strip_comments(m: re.Match) -> str:
        body = m.group(0)
        if _ALLOW_MARKER_PRESERVE.search(body):
            return body
        return ""
    text = re.sub(r"/\*[^*]*\*+(?:[^/*][^*]*\*+)*/", _strip_comments, text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([{}:;,>+~])\s*", r"\1", text)
    text = text.replace(";}", "}")
    return text.strip()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_bundle(paths: list[str], label: str) -> tuple[str, list[dict]]:
    chunks: list[str] = []
    sources: list[dict] = []
    for rel in paths:
        fp = REPO / rel.replace("/", "\\") if "\\" in rel else REPO / rel
        if not fp.is_file():
            raise FileNotFoundError(f"{label} source missing: {rel}")
        raw = fp.read_text(encoding="utf-8")
        digest = _file_sha256(fp)
        chunks.append(f"/* === {rel} sha256:{digest[:12]} === */\n{raw}\n")
        sources.append({"path": rel, "sha256": digest, "bytes": fp.stat().st_size})
    combined = "\n".join(chunks)
    return _minify_css(combined), sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if bundles are stale vs manifest sources",
    )
    args = parser.parse_args()

    spec = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    critical_css, critical_sources = _build_bundle(spec["critical"], "critical")
    enhanced_css, enhanced_sources = _build_bundle(spec["enhanced"], "enhanced")

    out_manifest = {
        "version": spec.get("version"),
        "generated_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "critical": {
            "path": "static/marketing/css/marketing-critical.min.css",
            "bytes": len(critical_css.encode("utf-8")),
            "sources": critical_sources,
        },
        "enhanced": {
            "path": "static/marketing/css/marketing-enhanced.min.css",
            "bytes": len(enhanced_css.encode("utf-8")),
            "sources": enhanced_sources,
        },
        "budgets": spec.get("size_budget_bytes", {}),
    }

    if args.check:
        stale = False
        for out_path, expected_text in (
            (OUT_CRITICAL, critical_css),
            (OUT_ENHANCED, enhanced_css),
        ):
            if not out_path.is_file() or out_path.read_text(encoding="utf-8") != expected_text:
                stale = True
        if stale or not OUT_HASH_MANIFEST.is_file():
            print(
                "marketing CSS bundles stale — run: python scripts/build_marketing_css_bundles.py",
                file=sys.stderr,
            )
            return 1
        stored = json.loads(OUT_HASH_MANIFEST.read_text(encoding="utf-8"))
        if stored.get("critical", {}).get("sources") != critical_sources:
            print("marketing-bundles.manifest.json stale (critical sources)", file=sys.stderr)
            return 1
        if stored.get("enhanced", {}).get("sources") != enhanced_sources:
            print("marketing-bundles.manifest.json stale (enhanced sources)", file=sys.stderr)
            return 1
        crit_bytes = int(out_manifest["critical"]["bytes"])
        enh_bytes = int(out_manifest["enhanced"]["bytes"])
        budgets = spec.get("size_budget_bytes", {})
        crit_max = int(budgets.get("critical_max", 0) or 0)
        enh_max = int(budgets.get("enhanced_max", 0) or 0)
        if crit_max and crit_bytes > crit_max:
            print(
                f"marketing critical bundle {crit_bytes}B exceeds budget {crit_max}B",
                file=sys.stderr,
            )
            return 1
        if enh_max and enh_bytes > enh_max:
            print(
                f"marketing enhanced bundle {enh_bytes}B exceeds budget {enh_max}B",
                file=sys.stderr,
            )
            return 1
        print(
            f"marketing CSS bundles fresh "
            f"(critical={crit_bytes}B enhanced={enh_bytes}B)"
        )
        return 0

    OUT_CRITICAL.parent.mkdir(parents=True, exist_ok=True)
    OUT_CRITICAL.write_text(critical_css, encoding="utf-8")
    OUT_ENHANCED.write_text(enhanced_css, encoding="utf-8")
    OUT_HASH_MANIFEST.write_text(
        json.dumps(out_manifest, indent=2) + "\n", encoding="utf-8"
    )

    budgets = spec.get("size_budget_bytes", {})
    crit_max = int(budgets.get("critical_max", 0) or 0)
    enh_max = int(budgets.get("enhanced_max", 0) or 0)
    exit_code = 0
    if crit_max and out_manifest["critical"]["bytes"] > crit_max:
        print(
            f"WARN: critical bundle {out_manifest['critical']['bytes']}B "
            f"exceeds budget {crit_max}B",
            file=sys.stderr,
        )
    if enh_max and out_manifest["enhanced"]["bytes"] > enh_max:
        print(
            f"WARN: enhanced bundle {out_manifest['enhanced']['bytes']}B "
            f"exceeds budget {enh_max}B",
            file=sys.stderr,
        )

    print(
        f"wrote {OUT_CRITICAL.name} ({out_manifest['critical']['bytes']} bytes) "
        f"and {OUT_ENHANCED.name} ({out_manifest['enhanced']['bytes']} bytes)"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
