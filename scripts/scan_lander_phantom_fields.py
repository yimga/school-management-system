#!/usr/bin/env python3
"""Lander phantom-field gate (silent-data-loss seal, 2026-07-09).

The Migration Cloud landers persist canonical rows into tenant models. A whole
class of silent-data-loss bug shipped repeatedly here: a lander hand-builds a
``.create(...)`` / ``.get_or_create(...)`` / ``.update_or_create(...)`` call on a
tenant model with a keyword (or a ``defaults={...}`` literal key) that is **not a
real field of that model** — e.g. ``DynamicFieldValue.objects.create(definition=,
object_id=, value=)`` (the model has ``entity_type/entity_id/field_key/value_json/
school``), or ``StudentProfile(..., enrollment_status="graduated")`` (the field is
``status``). Django raises ``TypeError``/``FieldError``; a surrounding broad
``except`` swallows it; the row vanishes or lands stripped of the phantom data,
and a counter pins to a happy number forever.

This gate AST-scans ``apps/migration_cloud/landers/*.py`` for those calls on the
known tenant models and flags any keyword — or ``defaults={...}`` literal key —
that is not a real field. The sanctioned escape hatch is
``filter_to_model_fields(<dict>, <Model>)``: when ``defaults=`` is a call to that
helper, its keys are dropped-to-real-fields at runtime, so the gate treats the
whole ``defaults`` as safe and does not inspect it. ``**kwargs`` / variable
``defaults`` are opaque (skipped — bias to false-negative, never red a clean
tree).

Model field names are resolved from the live model source (AST) UNIONed with a
hardcoded allowlist backstop, so a newly-added real field never false-positives
and a parse miss never does either.

Usage::

  python scripts/scan_lander_phantom_fields.py             # human report
  python scripts/scan_lander_phantom_fields.py --json      # JSON to stdout
  python scripts/scan_lander_phantom_fields.py --compare   # CI gate (exit 1 if grown)
  python scripts/scan_lander_phantom_fields.py --update-baseline

Mark a deliberate non-field kwarg with ``# lander-phantom-allow: <reason>`` on the
call line or the line above.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "var" / "security-audit-baseline-lander-phantom-fields.json"
LANDERS_DIR = ROOT / "apps" / "migration_cloud" / "landers"

WRITE_METHODS = {"create", "get_or_create", "update_or_create"}
SANITIZER = "filter_to_model_fields"
ALLOW_MARKER = "lander-phantom-allow:"

# Tenant models whose writes we police + where their source lives. Fields are
# read from source (AST) at scan time and UNIONed with the hardcoded backstop
# below so neither a new real field nor a parse miss ever false-positives.
MODEL_SOURCES: dict[str, str] = {
    "DynamicFieldValue": "apps/metadata/models.py",
    "DynamicFieldDefinition": "apps/metadata/models.py",
    "Incident": "apps/academics/models.py",
    "StudentProfile": "apps/people/models.py",
}

# Hardcoded backstop (verified against the models 2026-07-09). Implicit id/pk
# added for every model. FK ``<name>_id`` forms are accepted generically.
_HARDCODED_FIELDS: dict[str, set[str]] = {
    "DynamicFieldValue": {
        "entity_type", "entity_id", "field_key", "value_json", "school",
        "created_at", "updated_at",
    },
    "DynamicFieldDefinition": {
        "entity_type", "field_key", "label", "data_type", "school", "required",
        "is_active", "created_at", "updated_at",
    },
    "Incident": {
        "student", "teacher", "school", "incident_type", "date", "description",
        "severity", "status", "mtss_tier", "parent_notified_at", "notify_parent",
        "created_at", "created_by",
    },
    "StudentProfile": {
        "school", "user", "first_name", "last_name", "student_code",
        "admission_number", "search_index", "profile_photo", "gender",
        "date_of_birth", "place_of_birth", "status", "merged_into", "joined_term",
        "joined_date", "section", "parent_phone", "referral_code", "academic_year",
        "classroom", "specialty", "custom_attributes", "client_offline_id",
        "exam_candidate_number", "exam_center_code", "exam_system", "is_active",
        "uses_transport", "deleted_at", "created_by", "updated_by", "updated_at",
        "tags", "passport",
    },
}


def _fields_from_source(model: str) -> set[str]:
    """Collect class-body field names for ``model`` by AST-parsing its source.

    A field is a class-body ``name = <Call>(...)`` (or annotated assignment
    with a Call value) — i.e. ``models.CharField(...)`` etc. Non-field class
    attributes (``audit_enabled = True``, nested ``class Meta``) are skipped.
    Returns an empty set on any parse failure (the hardcoded backstop covers it).
    """
    src = ROOT / MODEL_SOURCES[model]
    try:
        tree = ast.parse(src.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return set()
    fields: set[str] = set()
    for cls in ast.walk(tree):
        if not (isinstance(cls, ast.ClassDef) and cls.name == model):
            continue
        for stmt in cls.body:
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(stmt, ast.Assign):
                targets = stmt.targets
                value = stmt.value
            elif isinstance(stmt, ast.AnnAssign) and stmt.target is not None:
                targets = [stmt.target]
                value = stmt.value
            if not isinstance(value, ast.Call):
                continue
            for tgt in targets:
                if isinstance(tgt, ast.Name):
                    fields.add(tgt.id)
    return fields


def _resolve_fields() -> dict[str, set[str]]:
    resolved: dict[str, set[str]] = {}
    for model in MODEL_SOURCES:
        fields = set(_HARDCODED_FIELDS.get(model, set()))
        fields |= _fields_from_source(model)
        fields |= {"id", "pk"}
        resolved[model] = fields
    return resolved


def _leftmost_name(node: ast.expr) -> str | None:
    """Return the head ``Name`` id of an attribute/call/subscript chain.

    ``DynamicFieldValue.objects.update_or_create`` -> ``DynamicFieldValue``;
    ``StudentProfile.objects.filter(...).update_or_create`` -> ``StudentProfile``.
    """
    cur: ast.expr = node
    while True:
        if isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        else:
            break
    return cur.id if isinstance(cur, ast.Name) else None


def _is_field(name: str, fields: set[str]) -> bool:
    head = name.split("__", 1)[0]
    if head in ("pk", "id"):
        return True
    if head in fields:
        return True
    # FK ``<field>_id`` writes the same column.
    return head.endswith("_id") and head[:-3] in fields


def _allowed(lines: list[str], lineno: int) -> bool:
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines) and ALLOW_MARKER in lines[idx]:
            return True
    return False


def _candidate_kwargs(call: ast.Call) -> list[str]:
    """Statically-visible kwarg / defaults-literal-key names that must be fields.

    Direct keywords (excluding ``defaults``) are candidates. ``defaults=`` is a
    candidate source ONLY when it is a Dict literal; when it is a
    ``filter_to_model_fields(...)`` call it is sanitized (skip). ``**kwargs`` and
    variable ``defaults`` are opaque (skip).
    """
    names: list[str] = []
    for kw in call.keywords:
        if kw.arg is None:  # **kwargs — opaque
            continue
        if kw.arg == "defaults":
            val = kw.value
            if isinstance(val, ast.Dict):
                for key in val.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        names.append(key.value)
            elif isinstance(val, ast.Call):
                fn = val.func
                fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if fname == SANITIZER:
                    continue  # sanitized — safe
                # any other call value is opaque
            # Name / other -> opaque
            continue
        names.append(kw.arg)
    return names


def scan(model_fields: dict[str, set[str]] | None = None) -> list[dict]:
    fields_by_model = model_fields or _resolve_fields()
    findings: list[dict] = []
    if not LANDERS_DIR.is_dir():
        return findings
    for path in sorted(LANDERS_DIR.glob("*.py")):
        rel = path.relative_to(ROOT)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in WRITE_METHODS):
                continue
            model = _leftmost_name(func)
            if model not in fields_by_model:
                continue
            if _allowed(lines, node.lineno):
                continue
            fields = fields_by_model[model]
            for name in _candidate_kwargs(node):
                if not _is_field(name, fields):
                    findings.append({
                        "path": rel.as_posix(),
                        "model": model,
                        "kwarg": name,
                        "line": node.lineno,
                    })
    return findings


def _multiset(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        key = f"{f['path']}::{f['model']}::{f['kwarg']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _payload(findings: list[dict]) -> dict:
    return {"finding_count": len(findings), "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = scan()

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(_payload(findings), indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {len(findings)} finding(s)")
        return 0

    if args.json:
        print(json.dumps(_payload(findings), indent=2, sort_keys=True))
        return 1 if findings else 0

    if args.compare:
        if not BASELINE.is_file():
            print("no baseline; run --update-baseline first", file=sys.stderr)
            return 1
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        base_counts = _multiset(base.get("findings", []))
        cur_counts = _multiset(findings)
        grew = {
            k: (v, base_counts.get(k, 0))
            for k, v in cur_counts.items()
            if v > base_counts.get(k, 0)
        }
        if grew:
            print("lander phantom-field writes GREW (silent-data-loss risk):", file=sys.stderr)
            for key, (cur, prev) in sorted(grew.items()):
                print(f"  {key}: {prev} -> {cur}", file=sys.stderr)
            print(
                "Persist through real model fields (route non-fields via "
                "filter_to_model_fields or the DynamicFieldValue engine), or add "
                "'# lander-phantom-allow: <reason>'.",
                file=sys.stderr,
            )
            return 1
        print(
            f"lander phantom-field writes: {len(findings)} site(s) "
            f"(baseline {base.get('finding_count')}) — no growth"
        )
        return 0

    print(f"{len(findings)} phantom-field write-site(s) in migration_cloud landers")
    for f in findings:
        print(f"  {f['path']}:{f['line']}  {f['model']}(..., {f['kwarg']}=...)  # not a field")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
