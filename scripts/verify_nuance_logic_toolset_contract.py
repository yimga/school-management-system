#!/usr/bin/env python3
"""
Ensure JSON-Logic nuance hook registry, model choices, and test contexts stay aligned.

Exit 0 prints NUANCE_LOGIC_TOOLSET_CONTRACT_PASS.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()


def _fail(msg: str) -> int:
    print(f"NUANCE_LOGIC_TOOLSET_CONTRACT_FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from apps.siteconfig.models import CustomNuance
    from apps.siteconfig.nuance_engine import (
        HOOK_REGISTRY,
        VIRTUAL_HOOK_POINTS,
        database_hook_points,
        default_test_contexts_for_hook,
        model_hook_point_choices,
    )

    registry_keys = frozenset(HOOK_REGISTRY)
    db_hooks = database_hook_points()
    model_values = {v for v, _ in model_hook_point_choices()}
    model_choice_values = {v for v, _ in CustomNuance.HOOK_CHOICES}

    if db_hooks | VIRTUAL_HOOK_POINTS != registry_keys:
        return _fail(
            "HOOK_REGISTRY must equal database_hook_points() | VIRTUAL_HOOK_POINTS"
        )

    if model_values != db_hooks:
        return _fail("model_hook_point_choices() must match database_hook_points()")

    if model_choice_values != db_hooks:
        return _fail("CustomNuance.HOOK_CHOICES values must match database_hook_points()")

    if VIRTUAL_HOOK_POINTS - registry_keys:
        return _fail("VIRTUAL_HOOK_POINTS must be a subset of HOOK_REGISTRY")

    for hook in db_hooks:
        allowed = set(HOOK_REGISTRY.get(hook, []))
        for i, ctx in enumerate(default_test_contexts_for_hook(hook)):
            extra = set(ctx) - allowed
            if extra:
                return _fail(
                    f"default_test_contexts_for_hook({hook!r}) test {i + 1} "
                    f"uses keys not in registry: {sorted(extra)}"
                )

    for hook in VIRTUAL_HOOK_POINTS:
        allowed = set(HOOK_REGISTRY.get(hook, []))
        for i, ctx in enumerate(default_test_contexts_for_hook(hook)):
            extra = set(ctx) - allowed
            if extra:
                return _fail(
                    f"virtual hook {hook!r} test context {i + 1} has disallowed keys: "
                    f"{sorted(extra)}"
                )

    print("NUANCE_LOGIC_TOOLSET_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
