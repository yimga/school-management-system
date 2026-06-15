#!/usr/bin/env python
"""verify_intelligence_model_producers.py — seal against the read-only-orphan-model leak.

Background
----------
A class of latent bug on this platform: a model that drives a user-facing surface
is READ in views/services but never WRITTEN anywhere, so the surface is
perpetually empty and the feature looks "dormant". This bit the customer-success
support co-pilot — `TenantRiskAlert` + `TenantInterventionSuggestion` were read by
four surfaces but had zero producers, so the co-pilot only ever showed its empty
state (fixed by `customersuccess.services.sync_tenant_risk_signals`).

This verifier seals that fix so it can NEVER silently regress: for every
surface-critical model on the WATCHLIST it asserts at least one *writer* exists in
non-test application code. A writer is `<Model>.objects.create / get_or_create /
update_or_create / bulk_create / acreate`, or a direct `<Model>(...)`
instantiation. If a watchlisted model loses its producer, CI fails here.

This is intentionally a curated allowlist (zero false positives), not a repo-wide
orphan scan. When a new surface-critical model gains a producer, add it to
WATCHLIST so the producer is guarded going forward.

Exit code 0 = every watchlisted model has a producer; 1 = at least one orphaned.
Stdlib only.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = REPO_ROOT / "apps"

# (app_label, ModelName): models that drive a user-facing surface and therefore
# MUST have a producer. Keyed by app so the search stays scoped + fast.
WATCHLIST: tuple[tuple[str, str], ...] = (
    ("customersuccess", "TenantRiskAlert"),
    ("customersuccess", "TenantInterventionSuggestion"),
)

_WRITER_METHODS = frozenset(
    {"create", "get_or_create", "update_or_create", "bulk_create", "acreate"}
)


def _iter_app_py_files(app_label: str):
    app_dir = APPS_DIR / app_label
    if not app_dir.is_dir():
        return
    for path in app_dir.rglob("*.py"):
        parts = set(path.parts)
        if "migrations" in parts or "tests" in parts:
            continue
        if path.name.startswith("test_"):
            continue
        yield path


def _model_has_writer(app_label: str, model_name: str) -> bool:
    """True if any non-test app file writes `model_name` (manager create or instantiation)."""
    for path in _iter_app_py_files(app_label):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # <Model>(...) direct instantiation
            if isinstance(func, ast.Name) and func.id == model_name:
                return True
            # <Model>.objects.<writer>(...)
            if (
                isinstance(func, ast.Attribute)
                and func.attr in _WRITER_METHODS
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "objects"
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == model_name
            ):
                return True
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON report"
    )
    args = parser.parse_args(argv)

    orphans = []
    checked = []
    for app_label, model_name in WATCHLIST:
        has_writer = _model_has_writer(app_label, model_name)
        checked.append((app_label, model_name, has_writer))
        if not has_writer:
            orphans.append(f"{app_label}.{model_name}")

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "checked": [
                        {"app": a, "model": m, "has_producer": ok}
                        for (a, m, ok) in checked
                    ],
                    "orphans": orphans,
                    "ok": not orphans,
                },
                indent=2,
            )
        )
    else:
        for app_label, model_name, ok in checked:
            mark = "ok " if ok else "ORPHAN"
            print(f"  [{mark}] {app_label}.{model_name}")
        if orphans:
            print(
                "\nERROR: watchlisted surface model(s) have no producer "
                "(read-only orphan regression):"
            )
            for o in orphans:
                print(f"  - {o}")
            print(
                "\nA surface that reads this model will be perpetually empty. "
                "Restore the producer, or if the model was intentionally retired, "
                "remove it from WATCHLIST in this script."
            )
        else:
            print(
                f"\nOK: all {len(checked)} watchlisted surface models have a producer."
            )

    return 1 if orphans else 0


if __name__ == "__main__":
    sys.exit(main())
