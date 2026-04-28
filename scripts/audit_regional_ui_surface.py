#!/usr/bin/env python3
"""
Regional / RTL shell readiness — scans key templates for lang/dir/marker/CSS signals.

Writes docs/generated/regional_ui_surface_audit.{json,md}.
Exit 1 only when a **required root shell** is missing lang+dir on <html> or regional marker.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "docs" / "generated" / "regional_ui_surface_audit.json"
OUT_MD = ROOT / "docs" / "generated" / "regional_ui_surface_audit.md"

SHELL_REQUIRE = (
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
    "templates/base.html",
)

HIGH_IMPACT = (
    "templates/accounts/backend_dashboard.html",
    "templates/siteconfig/compliance_exports.html",
    "templates/marketplace/tenant_app_catalog.html",
    "templates/teacher/marks_list.html",
)

LR_PATTERN = re.compile(r"\b(text-left|text-right|float-start|float-end|ms-|me-|ps-|pe-)[\w-]*")


def _read(rel: str) -> str | None:
    p = ROOT / rel
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def _classify_shell(text: str) -> str:
    if not text:
        return "violation"
    low = text.lower()
    if "<html" not in low:
        return "needs_review"
    if "lang=" in low and "dir=" in low and "data-rmc-regional-ui" in low:
        return "rtl_ready"
    return "violation"


def _scan_high_impact(rel: str) -> tuple[str, list[str]]:
    text = _read(rel)
    msgs: list[str] = []
    if text is None:
        return "needs_review", [f"missing file: {rel}"]
    if "trans " in text or "{% trans" in text or "ttag" in text or "terminology" in text:
        term = "terminology_ready"
    else:
        term = "needs_review"
    hits = LR_PATTERN.findall(text)
    if hits:
        msgs.append(f"physical LTR/RTR class hints: {len(hits)} (sample: {hits[:5]})")
    if "data-rmc-regional-ui" in text or '{% extends "portal_base.html"' in text:
        return "rtl_ready" if not hits else "needs_review", msgs
    if '{% extends "backend_base.html"' in text or '{% extends "control_plane' in text:
        return "needs_review", msgs
    return term, msgs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args(argv)
    rows: list[dict[str, object]] = []
    shell_fail = False
    for rel in SHELL_REQUIRE:
        t = _read(rel)
        cls = _classify_shell(t or "")
        if cls == "violation":
            shell_fail = True
        rows.append(
            {
                "path": rel,
                "bucket": "shell",
                "classification": cls,
                "notes": [] if cls != "violation" else ["missing lang/dir/data-rmc-regional-ui on html"],
            }
        )
    for rel in HIGH_IMPACT:
        cls, notes = _scan_high_impact(rel)
        rows.append({"path": rel, "bucket": "high_impact", "classification": cls, "notes": notes})

    summary = {
        "violation": sum(1 for r in rows if r.get("classification") == "violation"),
        "needs_review": sum(1 for r in rows if r.get("classification") == "needs_review"),
        "rtl_ready": sum(1 for r in rows if r.get("classification") == "rtl_ready"),
        "terminology_ready": sum(1 for r in rows if r.get("classification") == "terminology_ready"),
    }
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "rows": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = [
        "# Regional UI surface audit",
        "",
        f"**Generated:** {payload['generated_at']}",
        "",
        "## Summary",
        "",
        json.dumps(summary, indent=2),
        "",
    ]
    for r in rows:
        md.append(f"- `{r['path']}` — **{r['classification']}**")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"audit_regional_ui_surface: OK -> {OUT_JSON}")
    if shell_fail:
        print("FAIL: shell violation (html lang/dir/marker).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
