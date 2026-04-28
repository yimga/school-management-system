#!/usr/bin/env python3
"""
Gilead / legacy label reference audit (classification; exit 0 by default).

With ``--strict-public``, exit 1 if any tracked ``templates/**/*.html`` (excluding
``templates/admin/``) contains a case-insensitive ``gilead`` match — public UI policy.

Writes docs/generated/gilead_reference_audit.json and .md.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "docs" / "generated" / "gilead_reference_audit.json"
OUT_MD = ROOT / "docs" / "generated" / "gilead_reference_audit.md"
PAT = re.compile(r"gilead", flags=re.IGNORECASE)


def _tracked_files() -> frozenset[str] | None:
    if not (ROOT / ".git").exists():
        return None
    try:
        r = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
            cwd=str(ROOT),
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    out: set[str] = set()
    for raw in r.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            out.add(Path(raw.decode("utf-8")).as_posix())
        except UnicodeDecodeError:
            continue
    return frozenset(out)


def _classify(rel: str) -> str:
    if rel.startswith("docs/"):
        return "docs_legacy"
    if "/migrations/" in rel or "/tests/" in rel:
        return "internal_tooling"
    if rel.startswith("scripts/") or rel.startswith(".cursor/"):
        return "internal_tooling"
    if rel.startswith("templates/"):
        if rel.startswith("templates/admin/"):
            return "internal_tooling"
        return "public_ui_violation"
    if rel.startswith("apps/"):
        return "internal_tooling"
    return "internal_tooling"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--strict-public",
        action="store_true",
        help="Exit 1 if templates (excl. admin) contain gilead matches.",
    )
    args = ap.parse_args(argv)

    tracked = _tracked_files()
    hits: list[dict[str, str]] = []
    public_violations = 0

    def consider(rel: str, line_no: int, line: str) -> None:
        nonlocal public_violations
        cls = _classify(rel)
        if cls == "public_ui_violation":
            public_violations += 1
        hits.append(
            {
                "file": rel,
                "line": str(line_no),
                "classification": cls,
                "preview": line.strip()[:200],
            }
        )

    if tracked is not None:
        for rel in sorted(tracked):
            if not rel.endswith((".py", ".html", ".md", ".json", ".po", ".txt")):
                continue
            path = ROOT / rel
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, start=1):
                if PAT.search(line):
                    consider(rel, i, line)
    else:
        for base in (ROOT / "templates", ROOT / "apps", ROOT / "docs"):
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                suf = path.suffix.lower()
                if suf not in {".html", ".py", ".md", ".json", ".po"}:
                    continue
                rel = path.relative_to(ROOT).as_posix()
                try:
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                for i, line in enumerate(lines, start=1):
                    if PAT.search(line):
                        consider(rel, i, line)

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {"hits": len(hits), "public_ui_violations": public_violations},
        "hits": sorted(hits, key=lambda h: (h["file"], int(h["line"])))[:8000],
        "truncated": len(hits) > 8000,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary: dict[str, int] = {}
    for h in hits:
        summary[h["classification"]] = summary.get(h["classification"], 0) + 1
    lines = [
        "# Gilead reference audit (generated)",
        "",
        f"**UTC** `{payload['generated_at']}`",
        "",
        f"**public_ui_violations:** {public_violations}",
        "",
        "| Classification | Count |",
        "| --- | --- |",
    ]
    for k in sorted(summary.keys()):
        lines.append(f"| {k} | {summary[k]} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.strict_public and public_violations:
        print(
            f"audit_gilead_references: FAIL public_ui_violations={public_violations}",
            file=sys.stderr,
        )
        return 1
    print("audit_gilead_references: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
