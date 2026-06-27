#!/usr/bin/env python3
"""Wave A drift gate: RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES <=> live RuntimeDefaults model.

WHY THIS EXISTS (and why it is NOT a duplicate of an existing gate)
------------------------------------------------------------------
Tenant config is resolved by ``get_effective_site_settings`` (apps/platform_runtime/helpers.py),
which layers ``School.settings`` overrides on top of the ``RuntimeDefaults`` singleton ONLY for
field names listed in ``RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES``
(apps/platform_runtime/runtime_defaults_first_class.py). If a typed column is added to the
``RuntimeDefaults`` model but NOT added to that tuple, the column still stores + reads, but it
SILENTLY SKIPS the per-tenant override merge (helpers.py:454-477) — a school can never override
it. The reverse (a tuple entry that is not a real column) is a latent ``AttributeError`` / dead
config key.

Existing gates do NOT cover this:
  * ``verify_domain_ownership_exact_storage.py`` locks the tuple <=> EXACT_FIELD_OWNERS owner-map
    sync (stdlib; it never introspects the Django model).
  * ``verify_marketplace_integration_first_class_parity.py`` checks the live model for only the ~9
    marketplace secret fields.
Neither asserts the FULL tuple against the FULL live model. This gate closes exactly that gap.

It is Django-aware (introspects ``RuntimeDefaults._meta``) so it runs in ``ci.yml::django-tests``
alongside the other model-introspecting gates (verify_get_model_integrity, field/relation refs).
Pure pass/fail (exit 0/1), zero-tolerance — no drift baseline, like its sibling
``verify_domain_ownership_exact_storage.py``.

Run: ``python scripts/verify_runtime_defaults_model_parity.py`` (or ``python manage.py shell``-bootstrapped).
Exit: 0 on parity, 1 on drift.
"""

from __future__ import annotations

import os
import sys

# Concrete columns on RuntimeDefaults that are intentionally NOT first-class
# config fields (so they are excused from the "every column must be first-class"
# direction): the primary key, the JSON catch-all payload bucket, and the row's
# update timestamp (owner == "delete" / row metadata in domain_ownership).
NON_FIRST_CLASS_COLUMNS: frozenset[str] = frozenset({"id", "payload", "updated_at"})


def _collect() -> tuple[set[str], set[str]]:
    import django
    from pathlib import Path

    # Make the repo root importable when run standalone (python scripts/<this>.py
    # puts scripts/ on sys.path[0], not the repo root, so `config`/`apps` wouldn't
    # resolve otherwise).
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    from apps.platform_runtime.models import RuntimeDefaults
    from apps.platform_runtime.runtime_defaults_first_class import (
        RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES,
    )

    columns = {
        f.name
        for f in RuntimeDefaults._meta.get_fields()
        if getattr(f, "concrete", False)
    }
    tuple_names = set(RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES)
    return columns, tuple_names


def main(argv: list[str] | None = None) -> int:
    try:
        columns, tuple_names = _collect()
    except Exception as exc:  # noqa: BLE001 — bootstrap/setup failure is a gate failure, surfaced
        print("verify_runtime_defaults_model_parity: FAILED", file=sys.stderr)
        print(f"  - could not introspect RuntimeDefaults: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    # Direction 1: every first-class tuple entry must be a real concrete column.
    for name in sorted(tuple_names - columns):
        errors.append(
            f"RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES contains {name!r} which is NOT a "
            "concrete RuntimeDefaults column (typo / renamed / removed column) — fix the "
            "tuple in apps/platform_runtime/runtime_defaults_first_class.py."
        )

    # Direction 2: every typed column (minus documented metadata) must be first-class,
    # else its per-tenant override silently skips the resolver merge.
    for name in sorted(columns - tuple_names - NON_FIRST_CLASS_COLUMNS):
        errors.append(
            f"RuntimeDefaults column {name!r} is a typed column but is MISSING from "
            "RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES — it will silently skip the "
            "School.settings override merge in get_effective_site_settings(). Add it to the "
            "tuple (and EXACT_FIELD_OWNERS), or, if it is genuinely not tenant-configurable, "
            "add it to NON_FIRST_CLASS_COLUMNS in this gate with a reason."
        )

    if errors:
        print("verify_runtime_defaults_model_parity: FAILED", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "verify_runtime_defaults_model_parity: PASS "
        f"({len(tuple_names)} first-class fields == "
        f"{len(columns) - len(NON_FIRST_CLASS_COLUMNS & columns)} typed RuntimeDefaults columns; "
        f"{len(NON_FIRST_CLASS_COLUMNS & columns)} metadata columns excused)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
