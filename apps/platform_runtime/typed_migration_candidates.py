"""
First candidates for typed-store migration (1043) — documentation / planning only.

Safe re-exports: use :func:`iter_typed_migration_candidate_keys` in tests and verifiers.
Do not perform ORM writes here.
"""
from __future__ import annotations

from pathlib import Path
import json


def iter_typed_migration_candidate_keys() -> tuple[str, ...]:
    """Keys whose Phase B category is ``typed_migration_target`` in the generated map."""
    repo = Path(__file__).resolve().parent.parent.parent
    p = repo / "docs" / "generated" / "sitesettings_typed_ownership_map.json"
    if not p.is_file():
        return ()
    data = json.loads(p.read_text(encoding="utf-8"))
    fields = data.get("fields") or {}
    out = [
        k
        for k, meta in fields.items()
        if isinstance(meta, dict)
        and meta.get("phase_b_category") == "typed_migration_target"
    ]
    return tuple(sorted(out))
