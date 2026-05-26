"""Wave Q6 (v3.95.2 — 2026-05-26) — Skyward read-only migration adapter.

Counsel-blocked write paths stay literal `# honest-stub:` markers in
``companion-docker/app/extractors/skyward.py``. This adapter wires the
read-only path through to the migration_cloud workflow:

- Takes a Skyward CSV export bundle (rows as list[dict]).
- Preprocesses each row via the existing Companion extractor.
- Maps to the canonical RMC ingestion shape.
- Returns ``{"records": [...], "skipped_write_paths": [...]}`` so the
  caller (concierge specialist + audit) can see exactly what counsel-blocked
  fields were dropped on the floor.

NEVER call this with intent to write back to Skyward. The companion's
honest-stub markers refuse Skyward writes; this module is for *importing
Skyward data into RMC*, not the reverse.
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


# Fields that the Skyward extractor routes to ``read_only_*`` prefixed keys
# per the v3.34.0 counsel docket. The adapter surfaces them under separate
# keys so the audit trail records what RMC chose not to write back.
_READ_ONLY_KEYS: tuple[str, ...] = (
    "read_only_status",
    "read_only_balance",
)


def adapt_skyward_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Read-only Skyward → RMC canonical shape transform.

    Returns::

        {
          "records": [
            {"external_id": "...", "first_name": "...", ...},
            ...
          ],
          "skipped_write_paths": [
            {"row_index": 4, "field": "read_only_status", "value": "active"},
            ...
          ],
          "stats": {
            "total_rows": int,
            "records_emitted": int,
            "write_paths_skipped": int,
          },
        }
    """
    try:
        # Lazy import — the extractor lives in a sibling package (companion-
        # docker) that may not be on the path in every test environment.
        from companion_docker.app.extractors.skyward import preprocess_rows  # type: ignore
    except ImportError:
        try:
            import importlib.util
            import os
            here = os.path.dirname(os.path.abspath(__file__))
            # Walk up to the repo root then into companion-docker.
            repo_root = os.path.normpath(os.path.join(here, "..", "..", ".."))
            module_path = os.path.join(
                repo_root, "companion-docker", "app", "extractors", "skyward.py",
            )
            if os.path.exists(module_path):
                spec = importlib.util.spec_from_file_location(
                    "_skyward_extractor", module_path,
                )
                mod = importlib.util.module_from_spec(spec)
                # The extractor's `normalize_header` lives in the package
                # __init__; we need to make that available.
                init_path = os.path.join(
                    repo_root, "companion-docker", "app", "extractors", "__init__.py",
                )
                init_spec = importlib.util.spec_from_file_location(
                    "_skyward_extractor_pkg", init_path,
                )
                init_mod = importlib.util.module_from_spec(init_spec)
                init_spec.loader.exec_module(init_mod)  # type: ignore
                import sys
                sys.modules["_skyward_extractor_pkg"] = init_mod
                # Patch the extractor's relative import.
                mod.__dict__["normalize_header"] = init_mod.normalize_header
                spec.loader.exec_module(mod)  # type: ignore
                preprocess_rows = mod.preprocess_rows
            else:
                logger.warning("skyward extractor not found at %s", module_path)
                return {
                    "records": list(rows),
                    "skipped_write_paths": [],
                    "stats": {
                        "total_rows": len(rows),
                        "records_emitted": len(rows),
                        "write_paths_skipped": 0,
                        "extractor_loaded": False,
                    },
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("skyward extractor load failed: %s", exc)
            return {
                "records": list(rows),
                "skipped_write_paths": [],
                "stats": {
                    "total_rows": len(rows),
                    "records_emitted": len(rows),
                    "write_paths_skipped": 0,
                    "extractor_loaded": False,
                },
            }

    processed = preprocess_rows(rows)
    skipped: list[dict[str, Any]] = []
    cleaned: list[dict[str, str]] = []
    for idx, row in enumerate(processed):
        record = {k: v for k, v in row.items() if k not in _READ_ONLY_KEYS}
        for ro_key in _READ_ONLY_KEYS:
            if ro_key in row and row[ro_key]:
                skipped.append({
                    "row_index": idx,
                    "field": ro_key,
                    "value": row[ro_key],
                })
        cleaned.append(record)
    return {
        "records": cleaned,
        "skipped_write_paths": skipped,
        "stats": {
            "total_rows": len(rows),
            "records_emitted": len(cleaned),
            "write_paths_skipped": len(skipped),
            "extractor_loaded": True,
        },
    }


def read_only_field_names() -> tuple[str, ...]:
    """Return the set of fields counsel has blocked write paths on. Returning
    them lets the migration UI tell the concierge specialist exactly what
    data is being dropped."""
    return _READ_ONLY_KEYS
