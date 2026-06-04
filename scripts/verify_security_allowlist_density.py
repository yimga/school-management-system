#!/usr/bin/env python3
"""Security allowlist non-growth gate (raw SQL / csrf_exempt / AllowAny / broad except / tracked root).

v2: merged Phase 8 ledger summary must match live allowlist sizes (detect stale ledger).
v3: tracked_root_allowlist.json ``allowed`` array length capped (repo-root file discipline).
v4: embedded classification lints (raw SQL / csrf_exempt / AllowAny) so this script alone
    proves code↔allowlist parity, not only JSON size caps + ledger rows.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Baseline captured 2026-03-26 (non-growth discipline).
# OAuth token endpoint classified 2026-05-01 for external non-browser clients.
# 2026-05-14: reviewed CSP report ingestion and public catalog read-only endpoints.
# 2026-05-29: batch 1566 — classify OneRoster/OIDC/SAML/SCIM interop modules under apps/api/.
# email-provider webhook CSRF exemptions, raw SQL operational/vector/intake
# surfaces, Migration Cloud public API docs, and tracked root manifest growth;
# embedded classification lints still enforce exact path/count parity.
# tracked_root: repo-root file allowlist for mega-file / tree gates (shrink-only).
# 2026-05-29: batch 1578 final audit — OneRoster Demographics module (apps/api/oneroster_demographics.py).
# 2026-06-02: batch 1617 — sqlite_pragmas WAL PRAGMAs; OneRoster OAuth2 + LTI token +
# newsletter + wizard telemetry CSRF classifications; tracked_root manifest sync.
# 2026-06-04: CI-readiness closeout — classify SMS inbound webhook (Twilio HMAC-SHA1 /
# Africa's Talking shared-secret, signature-verified MO + status endpoints) and the
# RFC 8058 one-click newsletter unsubscribe POST (+1 csrf_exempt file, 36->37); and
# sync tracked_root baseline to the four standard repo-root governance files added with
# the OSS/CI manifest (CODE_OF_CONDUCT.md, LICENSE, README.md, THIRD_PARTY_NOTICES.md;
# 35->39). Both are classified growth, not silent expansion.
MAX_COUNTS: dict[str, tuple[str, int]] = {
    "raw_sql_allowlist.json": ("files", 21),
    "csrf_exempt_allowlist.json": ("files", 37),
    "allow_any_allowlist.json": ("files", 4),
    "broad_except_allowlist.json": ("allowed_counts", 189),
    "tracked_root_allowlist.json": ("allowed", 39),
}

_CLASSIFICATION_LINTS: tuple[tuple[str, str], ...] = (
    ("lint_raw_sql_usage", "lint_raw_sql_usage.py"),
    ("lint_csrf_exempt_usage", "lint_csrf_exempt_usage.py"),
    ("lint_allow_any_usage", "lint_allow_any_usage.py"),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify security allowlist non-growth and ledger parity "
            "(raw SQL / csrf_exempt / AllowAny / broad except / tracked root)."
        )
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to scan (default: this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _run_embedded_classification_lints(root: Path) -> list[str]:
    """Re-run path/count lints so density gate fails on drift even if this script is invoked alone."""
    errs: list[str] = []
    py = sys.executable
    for label, script_name in _CLASSIFICATION_LINTS:
        script_path = root / "scripts" / script_name
        if not script_path.is_file():
            errs.append(f"{label}: missing {script_path.relative_to(root)}")
            continue
        proc = subprocess.run(
            [py, str(script_path)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()
            if len(tail) > 4000:
                tail = tail[:4000] + "\n…(truncated)"
            errs.append(
                f"{label} failed ({script_name} exit {proc.returncode}); "
                "fix code or shrink-only allowlist updates.\n" + tail
            )
    return errs


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_security_allowlist_density: {exc}", file=sys.stderr)
        return 1

    allowlists = root / "scripts" / "allowlists"
    ledger = root / "scripts" / "generated" / "phase8_security_ledger.json"

    errors: list[str] = []
    observed: list[str] = []

    for filename, (key, max_count) in MAX_COUNTS.items():
        path = allowlists / filename
        if not path.is_file():
            errors.append(f"Missing allowlist file: {path.relative_to(root)}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        section = data.get(key)
        if key == "allowed":
            if not isinstance(section, list):
                errors.append(f"{path.relative_to(ROOT)}: 'allowed' must be a JSON array")
                continue
            count = len(section)
        else:
            if not isinstance(section, dict):
                errors.append(f"{path.relative_to(ROOT)}: '{key}' must be a JSON object")
                continue
            count = len(section)
        observed.append(f"{filename}:{count}")
        if count > max_count:
            errors.append(
                f"{filename} '{key}' count grew ({count} > {max_count}); "
                "shrink/classify instead of silent expansion."
            )

    errors.extend(_run_embedded_classification_lints(root))

    # v2: ledger summary must match denormalized allowlist sizes (run build_phase8_security_ledger --write if stale).
    if ledger.is_file():
        try:
            ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
            summary = ledger_data.get("summary") or {}
            raw = json.loads((allowlists / "raw_sql_allowlist.json").read_text(encoding="utf-8"))
            csrf = json.loads((allowlists / "csrf_exempt_allowlist.json").read_text(encoding="utf-8"))
            anyp = json.loads((allowlists / "allow_any_allowlist.json").read_text(encoding="utf-8"))
            expect_sql = len(raw.get("files", {}) or {})
            expect_csrf = len(csrf.get("files", {}) or {})
            expect_any = len(anyp.get("files", {}) or {})
            for label, actual, expected in (
                ("raw_sql_files", summary.get("raw_sql_files"), expect_sql),
                ("csrf_exempt_files", summary.get("csrf_exempt_files"), expect_csrf),
                ("allow_any_files", summary.get("allow_any_files"), expect_any),
            ):
                if actual != expected:
                    errors.append(
                        f"phase8_security_ledger.json summary.{label} is {actual!r}; "
                        f"allowlists imply {expected!r}. Regenerate: "
                        "python scripts/build_phase8_security_ledger.py --write"
                    )
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"Could not verify security ledger parity: {exc}")
    else:
        errors.append(
            f"Missing {ledger.relative_to(root)} — run "
            "python scripts/build_phase8_security_ledger.py --write"
        )

    if errors:
        print("verify_security_allowlist_density:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "verify_security_allowlist_density: PASS "
        f"(counts: {', '.join(observed)}; classification lints OK; ledger summary aligned)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
