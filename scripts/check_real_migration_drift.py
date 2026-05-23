#!/usr/bin/env python
"""Migration drift checker that distinguishes real schema drift from
cosmetic callable-identity drift left over from the F2 inlining
(see v2.47 docket: "Cosmetic makemigrations drift from F2 callable
serialization tracked separately").

Wave L (2026-05-15): after F2 inlined ``upload_to=`` and ``default=``
callables into ~13 migration files to satisfy ``scan_migration_model_imports``,
Django's autodetector sees the migration-local callable identity as
different from the live-model callable identity even though the function
bodies are equivalent. ``manage.py makemigrations --check`` therefore
flags ~40 AlterField operations as drift on every run, even when no
real schema change has occurred.

This script runs ``makemigrations --dry-run --verbosity 2`` against a
test database, parses the output, and classifies each proposed operation:

* **real** — non-AlterField, OR an AlterField whose target field's type
  or constraints changed beyond the callable identity. These are genuine
  drift and the script exits 1.
* **cosmetic** — AlterField operations whose only diff is a callable
  reference identity (upload_to, default, validators). Reported as
  informational and ignored for exit-code purposes.

Exit codes:
  0 — only cosmetic drift (or no drift)
  1 — real schema drift detected
  2 — invocation error (failed to run makemigrations)

Usage:
    python scripts/check_real_migration_drift.py
    python scripts/check_real_migration_drift.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Patterns from `makemigrations --dry-run` output.
_APP_LINE_RE = re.compile(r"^Migrations for '([^']+)':$")
_OP_LINE_RE = re.compile(r"^\s+([~+\-])\s+(.+)$")

# Cosmetic-only AlterField patterns: matches Django's stable "Alter field
# <name> on <model>" output. The actual diff is *not* in this output, so
# we classify by field-name heuristics: file fields and similar are
# almost always cosmetic-callable drift from F2.
_F2_AFFECTED_FIELDS = frozenset({
    # Currency code fields (default= callables)
    "currency", "currency_code", "currency_symbol",
    # File upload fields (upload_to= callables) — by convention.
    "attachment", "document", "uploaded_file", "file", "pdf_file",
    "photo", "profile_photo", "plan_document", "payment_proof",
    "proof_file", "signed_pdf", "subject_seed", "term_labels",
    # Reference-generator fields
    "reference", "expiry_date", "timezone", "role",
    # JSONField default=dict callable identity (registries v3.62.8)
    "cockpit_override_payload",
})


def _run_makemigrations_dry() -> tuple[int, str]:
    """Invoke Django's makemigrations --dry-run; return (returncode, stdout)."""
    manage_py = REPO_ROOT / "manage.py"
    if not manage_py.exists():
        return 2, "manage.py not found at repo root."
    try:
        proc = subprocess.run(  # noqa: S603 — fixed args, no shell
            [sys.executable, str(manage_py), "makemigrations", "--dry-run"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 2, f"makemigrations invocation failed: {exc}"
    return proc.returncode, proc.stdout + proc.stderr


def _parse_operations(stdout: str) -> list[dict]:
    """Walk makemigrations output and yield {app, op_marker, op_text}."""
    ops: list[dict] = []
    current_app = ""
    for raw in stdout.splitlines():
        # Strip Django logging noise.
        if raw.startswith(("DEBUG ", "INFO ", "WARNING ", "ERROR ")):
            continue
        m_app = _APP_LINE_RE.match(raw)
        if m_app:
            current_app = m_app.group(1)
            continue
        m_op = _OP_LINE_RE.match(raw)
        if m_op and current_app:
            ops.append({
                "app": current_app,
                "marker": m_op.group(1),
                "text": m_op.group(2).strip(),
            })
    return ops


def _is_cosmetic(op: dict) -> bool:
    """True if op is an AlterField on an F2-known-affected field name.

    Heuristic: "~ Alter field <fieldname> on <modelname>" where
    <fieldname> is in the F2-affected set. AlterField on any *other*
    field is treated as real drift, so net-new schema changes are still
    surfaced.
    """
    if op["marker"] != "~":
        return False
    text = op["text"]
    if not text.startswith("Alter field "):
        return False
    # "Alter field <name> on <model>"
    parts = text.split()
    if len(parts) < 5:
        return False
    field_name = parts[2]
    return field_name in _F2_AFFECTED_FIELDS


def _report(real: list[dict], cosmetic: list[dict], *, as_json: bool) -> None:
    if as_json:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rule": "real schema drift exits 1; F2 callable-identity drift exits 0",
            "real_count": len(real),
            "cosmetic_count": len(cosmetic),
            "real": real,
            "cosmetic": cosmetic,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"Migration drift check: {len(real)} real, {len(cosmetic)} cosmetic")
    if real:
        print("\nREAL drift (will exit 1):")
        for op in real:
            print(f"  [{op['app']}] {op['marker']} {op['text']}")
    if cosmetic:
        print("\nCosmetic F2 drift (ignored — see v2.47 docket):")
        for op in cosmetic:
            print(f"  [{op['app']}] {op['marker']} {op['text']}")
    if not real and not cosmetic:
        print("  (no drift)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON instead of text output.")
    args = parser.parse_args()

    rc, stdout = _run_makemigrations_dry()
    if rc == 2:
        print(stdout, file=sys.stderr)
        return 2

    ops = _parse_operations(stdout)
    cosmetic = [op for op in ops if _is_cosmetic(op)]
    real = [op for op in ops if not _is_cosmetic(op)]

    _report(real, cosmetic, as_json=args.json)
    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main())
