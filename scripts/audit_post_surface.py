#!/usr/bin/env python3
"""
POST / mutation surface audit — governance visibility + optional strict gate.

Combines:
- POST-handler decorator classification (regenerates ``post_handler_audit.json``)
- Product ``csrf_exempt`` usages (line-level, heuristic)
- DRF ``AllowAny`` / open permission hints in ``apps/``
- Product ``apps/`` signals aligned with security_surface audit: raw SQL (``.cursor.execute``),
  ``subprocess.``, and CSV/PDF export delivery hints (attachment / ``FileResponse``)
- Optional embedded summary from ``security_surface_audit.json`` when present

Writes ``docs/generated/post_surface_audit.json`` and ``docs/generated/post_surface_audit.md``.

Exit:
- 0: default (always emit ledger; **does not** fail the repo on historical gaps)
- 1: with ``--strict`` when any **product** POST handler row is ``needs_review``,
     or when ``--fail-on-csrf-product`` and ``csrf_exempt`` hits exist under ``apps/``.

This avoids declaring the entire tree "DOMINANT" while still supporting a hard gate when ready.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_JSON = REPO / "docs" / "generated" / "post_surface_audit.json"
OUT_MD = REPO / "docs" / "generated" / "post_surface_audit.md"
POST_HANDLER_JSON = REPO / "docs" / "generated" / "post_handler_audit.json"
SECURITY_SURFACE_JSON = REPO / "docs" / "generated" / "security_surface_audit.json"

_RE_CURSOR = re.compile(r"\.cursor\.execute\s*\(")
_RE_SUBPROCESS = re.compile(r"\bsubprocess\.")


def _line_looks_like_export_delivery(line: str) -> bool:
    """Heuristic for CSV/PDF/JSON download responses (static scan)."""
    s = line.strip()
    if not s or s.startswith("#"):
        return False
    if "Content-Disposition" in line and "attachment" in line.lower():
        return True
    if "FileResponse" in line:
        return True
    if "attachment" in line.lower() and ("filename=" in line or "filename =" in line):
        return any(ext in line for ext in (".csv", ".pdf", ".json", ".xlsx"))
    return False


SKIP = (
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".django_test_dbs",
)


def _iter_apps_py():
    apps = REPO / "apps"
    if not apps.is_dir():
        return
    for path in apps.rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if any(sk in rel for sk in SKIP) or "/tests/" in rel or "test_" in path.name:
            continue
        yield path


def _scan_csrf_exempt() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pat = re.compile(r"(csrf_exempt|csrf_exempt\s*\()")
    for path in sorted(_iter_apps_py(), key=lambda p: str(p)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if "csrf_exempt" not in line or line.strip().startswith("#"):
                continue
            if pat.search(line):
                rows.append(
                    {
                        "file": path.relative_to(REPO).as_posix(),
                        "line": str(i),
                        "signal": "csrf_exempt",
                    }
                )
    return rows


def _scan_allow_any() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(_iter_apps_py(), key=lambda p: str(p)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if "AllowAny" in line and ("permission" in line.lower() or "Permission" in line):
                rows.append(
                    {
                        "file": path.relative_to(REPO).as_posix(),
                        "line": str(i),
                        "signal": "allow_any_hint",
                    }
                )
    return rows


def _scan_apps_pattern(pat: re.Pattern[str], signal: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(_iter_apps_py(), key=lambda p: str(p)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(REPO).as_posix()
        for i, line in enumerate(text.splitlines(), start=1):
            if line.strip().startswith("#"):
                continue
            if pat.search(line):
                rows.append({"file": rel, "line": str(i), "signal": signal})
    return rows


def _scan_export_delivery_hints() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(_iter_apps_py(), key=lambda p: str(p)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(REPO).as_posix()
        for i, line in enumerate(text.splitlines(), start=1):
            if _line_looks_like_export_delivery(line):
                rows.append(
                    {"file": rel, "line": str(i), "signal": "export_delivery_hint"}
                )
    return rows


def _load_post_handler_payload() -> dict:
    if not POST_HANDLER_JSON.is_file():
        return {}
    try:
        return json.loads(POST_HANDLER_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_post_handler_rows() -> list[dict]:
    data = _load_post_handler_payload()
    return list(data.get("rows") or [])


def _load_security_surface_summary() -> dict:
    if not SECURITY_SURFACE_JSON.is_file():
        return {}
    try:
        data = json.loads(SECURITY_SURFACE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "generated_at": data.get("generated_at"),
        "summary": data.get("summary") if isinstance(data.get("summary"), dict) else {},
        "totals": data.get("totals") if isinstance(data.get("totals"), dict) else {},
        "summary_by_classification": data.get("summary_by_classification")
        if isinstance(data.get("summary_by_classification"), dict)
        else {},
    }


def _regenerate_post_handler() -> None:
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "audit_post_handler_surface.py")],
        cwd=str(REPO),
        check=False,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any product POST handler is needs_review.",
    )
    ap.add_argument(
        "--fail-on-csrf-product",
        action="store_true",
        help="Exit 1 if any csrf_exempt hit exists under apps/ (product).",
    )
    ap.add_argument(
        "--refresh-security-audit",
        action="store_true",
        help="Run scripts/audit_security_surface.py first so security_surface_audit_embed is current.",
    )
    args = ap.parse_args(argv)

    if args.refresh_security_audit:
        subprocess.run(
            [sys.executable, str(REPO / "scripts" / "audit_security_surface.py")],
            cwd=str(REPO),
            check=False,
        )

    _regenerate_post_handler()
    ph_rows = _load_post_handler_rows()
    product_post = [r for r in ph_rows if r.get("bucket") == "product"]
    needs_review = [r for r in product_post if r.get("classification") == "needs_review"]
    protected = [r for r in product_post if r.get("classification") == "protected_candidate"]

    csrf_hits = _scan_csrf_exempt()
    allow_any = _scan_allow_any()
    cursor_hits = _scan_apps_pattern(_RE_CURSOR, "cursor_execute")
    subprocess_hits = _scan_apps_pattern(_RE_SUBPROCESS, "subprocess")
    export_hints = _scan_export_delivery_hints()
    ph_payload = _load_post_handler_payload()
    security_embed = _load_security_surface_summary()

    payload = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "product_post_handlers": len(product_post),
            "product_needs_review": len(needs_review),
            "product_protected_candidate": len(protected),
            "csrf_exempt_hits_apps": len(csrf_hits),
            "allow_any_hint_hits": len(allow_any),
            "cursor_execute_hits_apps": len(cursor_hits),
            "subprocess_hits_apps": len(subprocess_hits),
            "export_delivery_hint_hits_apps": len(export_hints),
        },
        "post_risk": {
            "product_needs_review_post_handlers": len(needs_review),
            "product_protected_candidate_post_handlers": len(protected),
        },
        "post_handler_audit_embed": {
            "generated_at": ph_payload.get("generated_at"),
            "totals": ph_payload.get("totals") or {},
            "summary_by_classification": ph_payload.get("summary_by_classification")
            or {},
            "summary_by_bucket": ph_payload.get("summary_by_bucket") or {},
        },
        "security_surface_audit_embed": security_embed,
        "post_handler_product_needs_review": needs_review,
        "csrf_exempt_hits": csrf_hits,
        "allow_any_hints": allow_any[:500],
        "cursor_execute_hits": cursor_hits[:400],
        "subprocess_hits": subprocess_hits[:400],
        "export_delivery_hints": export_hints[:400],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# POST / mutation surface audit",
        "",
        f"**Generated:** {payload['generated_at']}",
        "",
        "## Summary",
        "",
        f"- product POST handlers: {payload['summary']['product_post_handlers']}",
        f"- product needs_review: {payload['summary']['product_needs_review']}",
        f"- csrf_exempt (apps): {payload['summary']['csrf_exempt_hits_apps']}",
        f"- allow_any hints: {payload['summary']['allow_any_hint_hits']}",
        f"- cursor_execute (apps): {payload['summary']['cursor_execute_hits_apps']}",
        f"- subprocess (apps): {payload['summary']['subprocess_hits_apps']}",
        f"- export_delivery_hint (apps): {payload['summary']['export_delivery_hint_hits_apps']}",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print("audit_post_surface: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    print(f"  written: {OUT_MD.as_posix()}")
    print(
        f"  product POST needs_review: {len(needs_review)}; "
        f"csrf_exempt (apps): {len(csrf_hits)}; allow_any hints: {len(allow_any)}; "
        f"cursor_execute (apps): {len(cursor_hits)}; subprocess (apps): {len(subprocess_hits)}; "
        f"export hints (apps): {len(export_hints)}"
    )

    if args.strict and needs_review:
        print("FAIL: --strict and product POST handlers need review.", file=sys.stderr)
        return 1
    if args.fail_on_csrf_product and csrf_hits:
        print("FAIL: --fail-on-csrf-product and csrf_exempt present in apps/.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
