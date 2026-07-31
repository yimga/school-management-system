"""Runtime phantom-field coverage for ALL lander-written models (2026-07-31).

The stdlib CI gate ``scripts/scan_lander_phantom_fields.py`` only knows 4 models
(DynamicFieldValue / DynamicFieldDefinition / Incident / StudentProfile) because
it resolves fields by AST-parsing a single ``models.py`` file — which misses
inherited fields and models defined in a ``models/`` package (TranscriptVaultItem,
the athletics models, …). That left ~26 lander-written models unpoliced for the
silent-data-loss "phantom field" bug: a ``.create()/.update_or_create()`` kwarg
(or a ``defaults={...}`` literal key) that is not a real field of the model →
``TypeError``/``FieldError`` swallowed by a broad ``except`` → the row vanishes or
lands stripped.

This test closes the blind-spot the robust way: it AST-walks every lander's
write-calls and checks each statically-visible kwarg against the model's LIVE
``_meta`` (so inheritance + model-packages + every app are covered, no hardcoded
field lists). It mirrors the scanner's escape hatches — ``**kwargs`` and a
``defaults=filter_to_model_fields(...)`` call are sanitised/opaque and skipped,
and ``# lander-phantom-allow: <reason>`` on the call line or the line above opts a
site out. False-negative biased: a model name that doesn't resolve to exactly one
registered model is skipped rather than guessed.
"""

from __future__ import annotations

import ast
from pathlib import Path

from django.apps import apps as django_apps
from django.test import SimpleTestCase

_LANDERS_DIR = Path(__file__).resolve().parents[1] / "landers"
_WRITE_METHODS = {"create", "get_or_create", "update_or_create"}
_SANITIZER = "filter_to_model_fields"
_ALLOW_MARKER = "lander-phantom-allow:"


def _models_by_name() -> dict[str, object]:
    """Map class name -> model, keeping only unambiguously-unique names."""
    by_name: dict[str, list] = {}
    for model in django_apps.get_models():
        by_name.setdefault(model.__name__, []).append(model)
    return {name: models[0] for name, models in by_name.items() if len(models) == 1}


def _real_field_names(model) -> set[str]:
    names: set[str] = {"id", "pk"}
    for f in model._meta.get_fields():
        name = getattr(f, "name", None)
        if name:
            names.add(name)
        attname = getattr(f, "attname", None)  # FK gives both name and name_id
        if attname:
            names.add(attname)
    return names


def _leftmost_name(node: ast.expr) -> str | None:
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


def _candidate_kwargs(call: ast.Call) -> list[str]:
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
                if fname == _SANITIZER:
                    continue  # sanitised → safe
                # any other call value is opaque
            # Name / other -> opaque
            continue
        names.append(kw.arg)
    return names


def _is_field(name: str, fields: set[str]) -> bool:
    head = name.split("__", 1)[0]
    if head in ("pk", "id") or head in fields:
        return True
    return head.endswith("_id") and head[:-3] in fields


def _allowed(lines: list[str], lineno: int) -> bool:
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines) and _ALLOW_MARKER in lines[idx]:
            return True
    return False


class LanderPhantomFieldRuntimeTests(SimpleTestCase):
    def test_no_lander_writes_a_phantom_field_on_any_model(self):
        models_by_name = _models_by_name()
        field_cache: dict[str, set[str]] = {}
        phantoms: list[str] = []
        checked_models: set[str] = set()

        self.assertTrue(_LANDERS_DIR.is_dir(), "landers dir missing")
        for path in sorted(_LANDERS_DIR.glob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute) and func.attr in _WRITE_METHODS):
                    continue
                model_name = _leftmost_name(func)
                model = models_by_name.get(model_name or "")
                if model is None:
                    continue  # unresolved / ambiguous → skip (false-negative bias)
                if _allowed(lines, node.lineno):
                    continue
                if model_name not in field_cache:
                    field_cache[model_name] = _real_field_names(model)
                fields = field_cache[model_name]
                checked_models.add(model_name)
                for name in _candidate_kwargs(node):
                    if not _is_field(name, fields):
                        phantoms.append(
                            f"{path.name}:{node.lineno}  {model_name}(..., {name}=...) "
                            f"— not a field of {model._meta.label}"
                        )

        self.assertEqual(
            phantoms, [],
            "Lander write(s) target a phantom (non-existent) model field — silent "
            "data loss risk. Route non-fields through filter_to_model_fields / the "
            "DynamicFieldValue engine, or mark a reviewed site "
            "'# lander-phantom-allow: <reason>':\n" + "\n".join(phantoms),
        )
        # Sanity: we actually policed a broad set of models (not a no-op), well
        # beyond the 4 the stdlib scanner covers.
        self.assertGreaterEqual(
            len(checked_models), 10,
            f"expected to police many lander models; only checked {sorted(checked_models)}",
        )
