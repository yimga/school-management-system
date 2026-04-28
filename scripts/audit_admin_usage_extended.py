#!/usr/bin/env python3
"""
Extended /admin and ``admin:`` URL usage scan (templates + product Python).

Exit 0. Complements ``audit_admin_gravity.py`` with template-level visibility.
Writes docs/generated/admin_usage_extended_audit.json and .md.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "docs" / "generated" / "admin_usage_extended_audit.json"
OUT_MD = ROOT / "docs" / "generated" / "admin_usage_extended_audit.md"

RE_ADMIN_URL = re.compile(r"{%\s*url\s+['\"]admin:")
RE_ADMIN_HREF = re.compile(r"href=[\"']/admin/")
RE_ADMIN_REV = re.compile(r"reverse\s*\(\s*['\"]admin:")
SKIP = frozenset({".git", "node_modules", "__pycache__", ".pytest_cache"})


def _classify_html(rel: str) -> str:
    if rel.startswith("templates/admin/"):
        return "django_admin_template"
    if "control_plane" in rel or "siteconfig/" in rel or "schools/super_" in rel:
        return "cp_surface_advanced_fallback"
    return "product_template_needs_review"


def _classify_py(rel: str) -> str:
    if "/admin.py" in rel or rel.endswith("/admin.py"):
        return "admin_module"
    if "/tests/" in rel or rel.startswith("apps/conftest"):
        return "tests"
    if "/migrations/" in rel:
        return "migrations"
    return "product_python_needs_review"


def _scan_file(path: Path, *, is_html: bool) -> list[dict[str, str]]:
    rel = path.relative_to(ROOT).as_posix()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    cls_fn = _classify_html if is_html else _classify_py
    out: list[dict[str, str]] = []
    for i, line in enumerate(lines, start=1):
        for name, pat in (
            ("django_admin_url_tag", RE_ADMIN_URL),
            ("admin_href", RE_ADMIN_HREF),
            ("reverse_admin", RE_ADMIN_REV),
        ):
            if pat.search(line):
                out.append(
                    {
                        "file": rel,
                        "line": str(i),
                        "pattern": name,
                        "classification": cls_fn(rel),
                    }
                )
    return out


def main() -> int:
    hits: list[dict[str, str]] = []
    tpl_root = ROOT / "templates"
    if tpl_root.is_dir():
        for path in sorted(tpl_root.rglob("*.html")):
            if any(s in path.parts for s in SKIP):
                continue
            hits.extend(_scan_file(path, is_html=True))
    for base in (ROOT / "apps", ROOT / "emis"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(s in path.parts for s in SKIP):
                continue
            if "/migrations/" in path.as_posix():
                continue
            hits.extend(_scan_file(path, is_html=False))

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {"hits": len(hits)},
        "hits": sorted(hits, key=lambda h: (h["file"], int(h["line"]), h["pattern"])),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary: dict[str, int] = {}
    for h in hits:
        summary[h["classification"]] = summary.get(h["classification"], 0) + 1
    lines = [
        "# Admin usage extended audit (generated)",
        "",
        f"**UTC** `{payload['generated_at']}`",
        "",
        f"**Total hits:** {len(hits)}",
        "",
        "| Classification | Count |",
        "| --- | --- |",
    ]
    for k in sorted(summary.keys()):
        lines.append(f"| {k} | {summary[k]} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("audit_admin_usage_extended: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
