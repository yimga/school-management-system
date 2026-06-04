"""Heuristic dead-code CANDIDATE finder (report-only; never deletes).

Walks ``apps/`` for top-level ``def``/``class`` definitions, counts textual
references to each name across the whole repo (``.py`` + ``.html``), and reports
symbols whose only occurrence is their own definition site.

This is a REVIEW aid, not ground truth. It has known false positives:

  * dynamic dispatch / ``getattr(obj, "name")`` / string-routed URLs
  * names exported only via ``__all__`` or re-exported elsewhere
  * DRF serializer/form fields, admin classes registered by decorator,
    signal handlers connected by ``@receiver``, templatetags, management
    commands (entry is the filename, not a reference)
  * anything referenced only from a template by a name the regex can't see

Every candidate is therefore CATEGORISED by confidence so a human can triage:

  PLAIN     - plain module-level function/class, no framework signal -> highest
              confidence it is genuinely dead (still verify before deleting)
  MODEL     - subclass of models.Model -> needs a MIGRATION decision, never a
              blind delete
  ADMIN     - ModelAdmin / in admin.py -> usually registered dynamically
  SIGNAL    - @receiver-decorated -> connected by decorator, not by name
  TEMPLATETAG - in a templatetags/ package -> referenced from templates
  VIEW      - in views*.py / api -> often routed by string in urls.py
  FORM_SER  - *Form / *Serializer / Meta-bearing -> referenced via field magic

Usage:
    python scripts/scan_dead_code_candidates.py            # human summary
    python scripts/scan_dead_code_candidates.py --json     # machine-readable
    python scripts/scan_dead_code_candidates.py --md       # markdown report
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = REPO_ROOT / "apps"

# Directories whose definitions we DO NOT report (entry points / generated).
_SKIP_DEF_PARTS = {"migrations", "tests", "__pycache__"}
_SKIP_DEF_FILENAMES = {"__init__.py", "urls.py", "admin.py", "apps.py"}

# Reference search covers the whole product surface.
_REF_DIRS = ["apps", "config", "services", "templates", "scripts"]
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Names that are framework hooks / entry points — never "dead" by signature.
_DUNDER_OR_HOOK = re.compile(
    r"^(__\w+__|ready|run|handle|Meta|Config|Migration|"
    r"setUp\w*|tearDown\w*|test_\w+)$"
)


def _is_test_file(path: Path) -> bool:
    return path.name.startswith("test_") or path.name.endswith("_test.py") or (
        path.name in {"tests.py", "conftest.py"}
    )


def _iter_def_files():
    for path in APPS_DIR.rglob("*.py"):
        parts = set(path.parts)
        if parts & _SKIP_DEF_PARTS:
            continue
        if path.name in _SKIP_DEF_FILENAMES:
            continue
        if _is_test_file(path):
            continue
        yield path


def _iter_ref_files():
    for rel in _REF_DIRS:
        base = REPO_ROOT / rel
        if not base.exists():
            continue
        for ext in ("*.py", "*.html"):
            for path in base.rglob(ext):
                if "__pycache__" in path.parts:
                    continue
                yield path


def _base_names(node: ast.ClassDef) -> list[str]:
    names = []
    for b in node.bases:
        if isinstance(b, ast.Name):
            names.append(b.id)
        elif isinstance(b, ast.Attribute):
            names.append(b.attr)
    return names


def _has_receiver_decorator(node) -> bool:
    for d in node.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        name = getattr(target, "attr", None) or getattr(target, "id", None)
        if name == "receiver":
            return True
    return False


def _categorise(path: Path, node) -> str:
    rel = path.relative_to(REPO_ROOT).as_posix()
    name = node.name
    if "templatetags" in path.parts:
        return "TEMPLATETAG"
    if _has_receiver_decorator(node):
        return "SIGNAL"
    if isinstance(node, ast.ClassDef):
        bases = _base_names(node)
        if "Model" in bases or "TenantModel" in bases:
            return "MODEL"
        if "ModelAdmin" in bases or name.endswith("Admin") or path.name == "admin.py":
            return "ADMIN"
        if name.endswith(("Form", "Serializer", "ViewSet", "View")):
            return "FORM_SER" if name.endswith(("Form", "Serializer")) else "VIEW"
    if re.search(r"(^|/)(views|api)[^/]*\.py$", rel) or "/api/" in rel:
        return "VIEW"
    return "PLAIN"


def collect_definitions():
    """name -> list of (path, lineno, kind, category)."""
    defs: dict[str, list[tuple]] = defaultdict(list)
    for path in _iter_def_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError):
            continue
        for node in tree.body:  # top-level only
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
                if name.startswith("_") and not name.startswith("__"):
                    # single-underscore "private" helpers are in-scope, but we
                    # only flag them if truly unreferenced — keep them.
                    pass
                if _DUNDER_OR_HOOK.match(name):
                    continue
                kind = "class" if isinstance(node, ast.ClassDef) else "func"
                defs[name].append(
                    (path, node.lineno, kind, _categorise(path, node))
                )
    return defs


def count_references():
    counts: Counter = Counter()
    for path in _iter_ref_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        counts.update(set(_WORD_RE.findall(text)))  # presence per file
        # also count multiplicity for "defined once, used once = only def"
    return counts


def total_occurrences():
    counts: Counter = Counter()
    for path in _iter_ref_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        counts.update(_WORD_RE.findall(text))
    return counts


def find_candidates():
    defs = collect_definitions()
    occ = total_occurrences()
    file_presence = count_references()

    candidates = []
    for name, sites in defs.items():
        n_defs = len(sites)
        total = occ.get(name, 0)
        files_with = file_presence.get(name, 0)
        # Heuristic: a symbol whose total textual occurrences across the repo is
        # <= the number of definition sites appears ONLY where it is defined.
        if total <= n_defs:
            for path, lineno, kind, category in sites:
                candidates.append(
                    {
                        "name": name,
                        "kind": kind,
                        "category": category,
                        "file": path.relative_to(REPO_ROOT).as_posix(),
                        "line": lineno,
                        "occurrences": total,
                        "def_sites": n_defs,
                        "files_present": files_with,
                    }
                )
    candidates.sort(key=lambda c: (c["category"], c["file"], c["line"]))
    return candidates


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--md", action="store_true", help="emit markdown report")
    args = ap.parse_args(argv)

    candidates = find_candidates()
    by_cat: dict[str, list] = defaultdict(list)
    for c in candidates:
        by_cat[c["category"]].append(c)

    if args.json:
        print(json.dumps({"candidates": candidates, "total": len(candidates)}, indent=2))
        return 0

    order = ["PLAIN", "FORM_SER", "VIEW", "ADMIN", "SIGNAL", "TEMPLATETAG", "MODEL"]
    safety = {
        "PLAIN": "highest-confidence dead (verify dynamic use, then safe to delete)",
        "FORM_SER": "field-magic risk — verify before deleting",
        "VIEW": "may be string-routed in urls.py — verify route table",
        "ADMIN": "registered dynamically — usually NOT dead",
        "SIGNAL": "connected by @receiver — usually NOT dead",
        "TEMPLATETAG": "referenced from templates by tag name — usually NOT dead",
        "MODEL": "DB table exists — needs a MIGRATION decision, never blind-delete",
    }

    if args.md:
        counts = {cat: len(by_cat.get(cat, [])) for cat in order}
        out = ["# Dead-code candidate report (heuristic, report-only)\n"]
        out.append(
            "_Generated by `scripts/scan_dead_code_candidates.py`. Re-run to "
            "refresh. This file is data for human triage — nothing here is "
            "deleted automatically._\n"
        )
        out.append(f"**Total candidates: {len(candidates)}**\n")
        out.append("| category | count | delete-safety |")
        out.append("|---|---|---|")
        for cat in order:
            if counts.get(cat):
                out.append(f"| {cat} | {counts[cat]} | {safety[cat]} |")
        out.append("")
        out.append("## Methodology\n")
        out.append(
            "A symbol (top-level `def`/`class` in `apps/`, excluding tests, "
            "migrations, `__init__`/`urls`/`admin`/`apps.py`, dunders and "
            "framework hooks) is a candidate when its name's **total textual "
            "occurrences across the repo** (`.py` + `.html` under `apps/`, "
            "`config/`, `services/`, `templates/`, `scripts/`) is `<=` the "
            "number of places it is defined — i.e. the name appears nowhere "
            "except its own definition.\n"
        )
        out.append("## Accuracy / known false positives\n")
        out.append(
            "Calibration spot-check (2026-06-03): 6/6 sampled PLAIN symbols "
            "(`roles_filter_q`, `mask_address`, `compute_proration`, "
            "`is_instructional_day`, `get_risk_factors_for_school`, "
            "`propose_workflow`) confirmed to have exactly one reference line — "
            "their definition. The heuristic does NOT see: dynamic dispatch / "
            "`getattr`, `__all__`-only re-exports, URL names routed by string, "
            "template tag invocations, DRF serializer/form field magic, or "
            "Celery tasks scheduled by dotted-string name. Hence the category "
            "split below: trust PLAIN most, treat ADMIN/SIGNAL/TEMPLATETAG as "
            "likely-live, and NEVER blind-delete MODEL (DB table exists).\n"
        )
        out.append("## Triage workflow\n")
        out.append(
            "1. Start with **PLAIN**. For each, confirm zero references "
            "(`grep -rwn <name> apps config services templates scripts`) and "
            "check it is not an intended public API, then delete cleanly and "
            "log it in `docs/CSS_RETIREMENT_DOCKET.md`.\n"
            "2. **MODEL**: decide per model — keep, or write a removal "
            "migration. Never delete the class without dropping the table.\n"
            "3. **VIEW/FORM_SER/ADMIN/SIGNAL/TEMPLATETAG**: verify the dynamic "
            "entry point (urls.py route, `@receiver` connect, template tag, "
            "admin register) before acting; most are live.\n"
        )
        for cat in order:
            rows = by_cat.get(cat, [])
            if not rows:
                continue
            out.append(f"\n## {cat} ({len(rows)}) — {safety[cat]}\n")
            out.append("| symbol | kind | file:line |")
            out.append("|---|---|---|")
            for c in rows:
                out.append(
                    f"| `{c['name']}` | {c['kind']} | {c['file']}:{c['line']} |"
                )
        print("\n".join(out))
        return 0

    print(f"Dead-code CANDIDATES (heuristic, report-only): {len(candidates)}\n")
    for cat in order:
        rows = by_cat.get(cat, [])
        if not rows:
            continue
        print(f"== {cat} ({len(rows)}) — {safety[cat]} ==")
        for c in rows[:200]:
            print(f"   {c['file']}:{c['line']}  {c['kind']} {c['name']}")
        if len(rows) > 200:
            print(f"   ... and {len(rows) - 200} more")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
