from __future__ import annotations

import json
from pathlib import Path


def normalize_fixture_allowlist_files(
    allowlist_files: dict[str, dict[str, int]] | None,
) -> dict[str, dict[str, object]]:
    if not allowlist_files:
        return {}
    out: dict[str, dict[str, object]] = {}
    for rel, entry in allowlist_files.items():
        merged = dict(entry)
        ec = merged.get("expected_count", 0)
        if isinstance(ec, int) and ec > 0:
            merged.setdefault("reason", "Test fixture allowlist justification.")
            merged.setdefault("last_reviewed", "2026-04-09")
        out[rel] = merged
    return out


def write_raw_sql_lint_fixture_repo(
    root: Path,
    *,
    allowlist_files: dict[str, dict[str, int]] | None = None,
    write_sql_user: bool = True,
) -> None:
    (root / "apps" / "demo").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "allowlists").mkdir(parents=True, exist_ok=True)
    if write_sql_user:
        (root / "apps" / "demo" / "sql_user.py").write_text(
            "\n".join(
                [
                    "from django.db import connection",
                    "",
                    "with connection.cursor() as cursor:",
                    '    cursor.execute("SELECT 1")',
                    "",
                ]
            ),
            encoding="utf-8",
        )
    normalized = normalize_fixture_allowlist_files(allowlist_files)
    doc: dict[str, object] = {"files": normalized}
    if any(
        isinstance(v.get("expected_count"), int) and v.get("expected_count", 0) > 0
        for v in normalized.values()
    ):
        doc["manifest_last_reviewed"] = "2026-04-09"
    (root / "scripts" / "allowlists" / "raw_sql_allowlist.json").write_text(
        json.dumps(doc, indent=2),
        encoding="utf-8",
    )
