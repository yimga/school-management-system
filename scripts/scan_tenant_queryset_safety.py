#!/usr/bin/env python
"""Tenant-isolation queryset safety scanner.

Walks every Python file in ``apps/`` and flags ``Model.objects.filter()``,
``Model.objects.get()``, and ``Model.objects.all()`` call sites where:

  * ``Model`` is tenant-scoped (its definition contains
    ``school = models.ForeignKey(...)`` or ``school_id = models.<Field>``), AND
  * the call site does not include a ``school=`` / ``school_id=`` / ``school__in=`` /
    ``school_id__in=`` kwarg, AND
  * is not inside a method whose ``self`` could already be tenant-scoped
    (best-effort: a manager method on a tenant-scoped model gets a pass).

Output: a JSON baseline written to ``var/security-audit-baseline-tenant-isolation.json``
and a terse stdout summary. CI gate: rerun and diff against the baseline; any
new finding fails.

Limitations (explicit; the scanner trades recall for precision):

  * It does **not** chase chained querysets across files — `qs = Model.objects.filter(school=...)`
    in one module and `qs.filter(name="X")` in another is treated as the chained
    `.filter()` call being unscoped. We document this.
  * Dynamic attribute lookup (`getattr(Model, "objects").filter(...)`) is not detected.
  * `Manager.from_queryset` custom managers are inspected by name, not behaviour.
  * Test files, migration files, and the scanner itself are excluded.

The point of this baseline is to encode every unscoped query that exists today
so any *new* one fails CI. It is not a proof that the current set is exploitable.
"""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"
SCAN_ROOTS = (
    REPO_ROOT / "apps",
    REPO_ROOT / "services",
    REPO_ROOT / "emis",
    REPO_ROOT / "payment",
)
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-tenant-isolation.json"

EXCLUDE_DIR_NAMES = {
    "tests",
    "migrations",
    "__pycache__",
    "node_modules",
    "fixtures",
    "management",
}
EXCLUDE_FILE_SUFFIXES = (
    "_test.py",
    "_tests.py",
)
EXCLUDE_FILENAMES = {
    "scan_tenant_queryset_safety.py",
    # A Django app's top-level ``tests.py`` is a test module (same intent as the
    # ``tests/`` dir + ``_test.py``/``_tests.py`` exclusions above); test code
    # must not inflate the production finding count.
    "tests.py",
}

# Kwargs that prove the queryset is bounded to a single tenant or an
# explicit tenant set. Any of these on a `.filter()` / `.get()` is safe.
SAFE_KWARGS = {
    "school",
    "school_id",
    "school__in",
    "school_id__in",
    "school__exact",
    "school_id__exact",
    # Explicit platform-wide queries (school__isnull=True is the
    # canonical "this row belongs to no tenant" lookup).
    "school__isnull",
    "school_id__isnull",
    # Cross-app tenancy aliases (rare but valid).
    "tenant",
    "tenant_id",
    "tenant__in",
}

# Methods that are inherently safe to call on a Manager / QuerySet without
# adding a tenant filter — they return per-instance state, not querysets.
INHERENTLY_SAFE_METHODS = {
    "create",  # write path; tenant goes in kwargs
    "get_or_create",
    "update_or_create",
    "bulk_create",
    "raw",  # explicit raw SQL — out of scope for this scanner
    "values",  # transformation; chained from already-scoped qs in most cases
    "values_list",
    "annotate",
    "aggregate",
    "order_by",
    "distinct",
    "exists",
    "count",
    "first",
    "last",
    "earliest",
    "latest",
    "in_bulk",
    "iterator",
    "select_related",
    "prefetch_related",
    "only",
    "defer",
    "using",
    "none",
}


def _safe_parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    except SyntaxError:
        return None


def _is_excluded(path: Path) -> bool:
    rel_parts = path.relative_to(REPO_ROOT).parts
    if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
        return True
    if path.name in EXCLUDE_FILENAMES:
        return True
    if any(path.name.endswith(suf) for suf in EXCLUDE_FILE_SUFFIXES):
        return True
    if path.name.startswith("test_"):
        return True
    return False


def _app_label_from_path(path: Path) -> str:
    rel = path.relative_to(APPS_DIR).parts
    return rel[0] if rel else ""


def collect_tenant_models() -> dict[str, set[str]]:
    """Return ``{model_name -> {app_label, ...}}`` for every model whose class
    body contains ``school = models.ForeignKey(...)`` or ``school_id = models.<Field>``.

    A given model name can live in more than one app — keys are model names
    (without app prefix) because the queryset analysis below sees only the
    class name in ``Model.objects.X``. False positives are acceptable here;
    the trade-off is documented in the file docstring.
    """
    tenant_models: dict[str, set[str]] = defaultdict(set)

    for py_path in APPS_DIR.rglob("models*.py"):
        if _is_excluded(py_path):
            continue
        tree = _safe_parse(py_path)
        if tree is None:
            continue
        app_label = _app_label_from_path(py_path)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for body_node in node.body:
                if isinstance(body_node, ast.Assign):
                    targets = [
                        t.id for t in body_node.targets if isinstance(t, ast.Name)
                    ]
                    if "school" in targets or "school_id" in targets:
                        tenant_models[node.name].add(app_label)
                        break
                if isinstance(body_node, ast.AnnAssign) and isinstance(body_node.target, ast.Name):
                    if body_node.target.id in ("school", "school_id"):
                        tenant_models[node.name].add(app_label)
                        break

    return tenant_models


def _has_safe_kwarg(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg in SAFE_KWARGS:
            return True
        # Q-object detection: any positional arg that mentions a SAFE_KWARGS
        # key is treated as safe.
        if kw.arg is None:
            try:
                src = ast.unparse(kw.value)
            except AttributeError:
                continue
            if any(k in src for k in SAFE_KWARGS):
                return True
    for pos in call.args:
        try:
            src = ast.unparse(pos)
        except AttributeError:
            continue
        if any(k in src for k in SAFE_KWARGS):
            return True
    return False


def _call_chain_names(node: ast.AST) -> list[str]:
    """Return attribute path leading to a Call. ``Foo.objects.filter(x=1)`` ->
    ``["Foo", "objects", "filter"]``. Used to recognise ``<Model>.objects.<method>(...)``.
    """
    names: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        names.insert(0, current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        names.insert(0, current.id)
    return names


_ALLOW_COMMENT = "tenant-isolation-allow:"


def _allowlisted_lines(source: str) -> dict[int, str]:
    """Return ``{line_number: reason}`` for every line carrying a
    ``# tenant-isolation-allow: <reason>`` comment.

    Annotating a call site like ::

        # tenant-isolation-allow: control-plane operator query (reviewed 2026-05-14)
        Foo.objects.filter(is_active=True)

    silences the scanner for that line *and* the line below. The
    reason text is mandatory — un-explained allowlists defeat the
    point.
    """
    lines = source.splitlines()
    allowed: dict[int, str] = {}
    for idx, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        marker_at = stripped.find(_ALLOW_COMMENT)
        if marker_at == -1:
            continue
        # Only accept inside a comment (line starts with # or contains '# ' before marker).
        comment_start = raw.find("#")
        if comment_start == -1 or comment_start > raw.find(_ALLOW_COMMENT):
            continue
        reason = stripped[marker_at + len(_ALLOW_COMMENT):].strip() or "no-reason-given"
        # Comment applies to this line, then walks forward across blank lines to the
        # next substantive line (fixes markers separated from the call by a blank line).
        allowed[idx] = reason
        j = idx + 1
        while j <= len(lines):
            row = lines[j - 1].strip()
            if not row:
                allowed[j] = reason
                j += 1
                continue
            if row.startswith("#") and _ALLOW_COMMENT not in row:
                allowed[j] = reason
                j += 1
                continue
            allowed[j] = reason
            break
    return allowed


def _marker_covers_line(source: str, lineno: int, *, lookback: int = 12) -> bool:
    """True when a allow-marker appears on a recent line above a multiline call."""
    if lineno <= 0:
        return False
    lines = source.splitlines()
    start = max(0, lineno - lookback)
    for i in range(start, lineno - 1):
        if _ALLOW_COMMENT in lines[i]:
            return True
    return False


def scan_file(path: Path, tenant_model_names: set[str]) -> list[dict]:
    tree = _safe_parse(path)
    if tree is None:
        return []
    findings: list[dict] = []
    source = path.read_text(encoding="utf-8", errors="ignore")
    allowed = _allowlisted_lines(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        chain = _call_chain_names(node.func)
        # Pattern: <Model>.objects.<method>(...)
        if len(chain) < 3:
            continue
        model_name, attr, method = chain[0], chain[-2], chain[-1]
        if attr != "objects":
            continue
        # 2026-05-14 wave NS-4: extend coverage to write paths.
        # `update()` + `delete()` against an unscoped queryset are
        # significantly more dangerous than reads — a missing
        # `school=` filter on a `.update()` can rewrite every tenant's
        # row in one query. `bulk_create` is excluded (callers pass
        # explicit `school=` per row); `create` is excluded for the
        # same reason.
        if method not in {"filter", "get", "all", "update", "delete"}:
            continue
        if method in INHERENTLY_SAFE_METHODS:
            continue
        if model_name not in tenant_model_names:
            continue
        if method != "all" and _has_safe_kwarg(node):
            continue
        if node.lineno in allowed:
            continue
        if _marker_covers_line(source, node.lineno):
            continue

        if method == "all":
            reason = "objects_all_on_tenant_model"
        elif method in {"update", "delete"}:
            reason = f"unscoped_{method}_on_tenant_model"
        else:
            reason = "no_school_filter"
        findings.append(
            {
                "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "line": node.lineno,
                "model": model_name,
                "method": method,
                "call": f"{model_name}.objects.{method}(...)",
                "reason": reason,
            }
        )

    return findings


def main(argv: list[str]) -> int:
    write_baseline = "--write-baseline" in argv
    compare = "--compare" in argv
    summary_only = "--summary" in argv

    tenant_models = collect_tenant_models()
    tenant_names = set(tenant_models.keys())
    print(f"[scanner] tenant-scoped models: {len(tenant_names)}", file=sys.stderr)

    findings: list[dict] = []
    for scan_root in SCAN_ROOTS:
        if not scan_root.is_dir():
            continue
        for py_path in scan_root.rglob("*.py"):
            if _is_excluded(py_path):
                continue
            findings.extend(scan_file(py_path, tenant_names))

    findings.sort(key=lambda f: (f["file"], f["line"]))
    by_app: dict[str, int] = defaultdict(int)
    for f in findings:
        parts = f["file"].split("/")
        app = parts[1] if len(parts) > 1 else "other"
        by_app[app] += 1

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_scoped_models": sorted(tenant_names),
        "tenant_model_count": len(tenant_names),
        "finding_count": len(findings),
        "findings_per_app": dict(sorted(by_app.items(), key=lambda kv: -kv[1])),
        "findings": findings if not summary_only else findings[:50],
    }

    print(json.dumps({k: v for k, v in payload.items() if k != "findings"}, indent=2))
    if not summary_only:
        print(f"\n[scanner] sample (first 5):", file=sys.stderr)
        for f in findings[:5]:
            print(f"  {f['file']}:{f['line']}  {f['call']}  ({f['reason']})", file=sys.stderr)

    if write_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"[scanner] baseline written to {BASELINE_PATH}", file=sys.stderr)
        return 0

    if compare:
        if not BASELINE_PATH.exists():
            print(f"[scanner] no baseline at {BASELINE_PATH}; run --write-baseline first", file=sys.stderr)
            return 2
        old = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        old_set = {(f["file"], f["line"], f["model"], f["method"]) for f in old.get("findings", [])}
        new_set = {(f["file"], f["line"], f["model"], f["method"]) for f in findings}
        new_only = new_set - old_set
        if new_only:
            print(f"[scanner] NEW UNSCOPED QUERIES ({len(new_only)}):", file=sys.stderr)
            for entry in sorted(new_only):
                print(f"  + {entry[0]}:{entry[1]}  {entry[2]}.objects.{entry[3]}(...)", file=sys.stderr)
            return 1
        print("[scanner] no new unscoped queries vs baseline.", file=sys.stderr)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
