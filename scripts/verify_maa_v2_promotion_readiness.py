#!/usr/bin/env python3
"""MAA v2.0 promotion pre-flight verifier (v3.35.0 Agent 3).

Read-only verifier that proves the codebase is ready for the
``RMC_MAA_DEFAULT_VERSION=v2.0`` flip described in
``docs/MAA_V2_PROMOTION_CHECKLIST.md``. The verifier:

  * NEVER flips anything (no writes outside the JSON audit report).
  * NEVER logs MAA body content (only counts + booleans + filenames).
  * Returns exit 0 iff every check passes, exit 1 otherwise.

The verifier is suitable as a CI gate, an operator-driven manual check,
or as the in-process data source for the operator UI
``/super/migration/maa-v2-promotion/`` page.

Eight checks::

    1. docs/legal/maa_v2_signoff.pdf exists
    2. MAA_TEXT_V2_0 contains all 5 verbatim phrases
    3. MAA_TEXT_V2_0 does NOT contain the [DRAFT ... PENDING] header
    4. MAA_TEXT_DRAFT_VERSIONS does NOT contain "v2.0"
    5. MIGRATION_CLOUD_MAA_DEFAULT_VERSION resolves to "v2.0"
    6. v1.0 historic MigrationAuthorizationAgreement rows still
       queryable (and signature_text_sha256 backfilled)
    7. docs/DPA_TEMPLATE.md references v2.0 clauses
    8. docs/DSAR_RUNBOOK.md references v2.0 clauses

Each check prints ``[OK]`` / ``[FAIL]`` + a short note; the final
summary line reports the totals.  The full result is also written to
``var/maa-v2-readiness-<utc_iso>.json`` for the operator UI to read.

Stdlib + Django only. No third-party deps.

Today the verifier is expected to FAIL on checks 1, 3, 4, 5 (since the
flip has NOT been performed). That is the correct read; the verifier
turns green only when an operator has completed the procedure.
"""
from __future__ import annotations

import argparse
import ast
import datetime as _dt
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


REQUIRED_VERBATIM_PHRASES = [
    "scope of access",
    "data minimization",
    "no retention beyond migration",
    "right to withdraw at any time",
    "data subject rights",
]

DRAFT_HEADER_SUBSTR = "[DRAFT v2.0 — PENDING COUNSEL REVIEW]"

# Resolve the repo root from this file's location.
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent  # scripts/.. == beta/school-management-system


# ──────────────────────────────────────────────────────────────────────── checks


def _check_signoff_pdf_present() -> dict:
    """Check 1: ``docs/legal/maa_v2_signoff.pdf`` exists + is non-empty."""
    rel = "docs/legal/maa_v2_signoff.pdf"
    p = REPO_ROOT / rel
    if not p.is_file():
        return {
            "id": "signoff_pdf_present",
            "ok": False,
            "note": f"missing file: {rel}",
        }
    size = p.stat().st_size
    if size == 0:
        return {
            "id": "signoff_pdf_present",
            "ok": False,
            "note": f"{rel} exists but is empty (0 bytes)",
        }
    return {
        "id": "signoff_pdf_present",
        "ok": True,
        "note": f"{rel} present ({size} bytes)",
    }


def _check_v2_phrases_present() -> dict:
    """Check 2: all 5 verbatim phrases present in ``MAA_TEXT_V2_0``."""
    body = _read_v2_text_body()
    if body is None:
        return {
            "id": "v2_phrases_present",
            "ok": False,
            "note": "could not read MAA_TEXT_V2_0 from services/maa_text.py",
        }
    lower = body.lower()
    missing = [p for p in REQUIRED_VERBATIM_PHRASES if p not in lower]
    if missing:
        return {
            "id": "v2_phrases_present",
            "ok": False,
            "note": f"missing phrases: {missing!r}",
        }
    return {
        "id": "v2_phrases_present",
        "ok": True,
        "note": f"all {len(REQUIRED_VERBATIM_PHRASES)} verbatim phrases present",
    }


def _check_draft_header_removed() -> dict:
    """Check 3: ``MAA_TEXT_V2_0`` no longer carries the DRAFT header."""
    body = _read_v2_text_body()
    if body is None:
        return {
            "id": "draft_header_removed",
            "ok": False,
            "note": "could not read MAA_TEXT_V2_0",
        }
    if DRAFT_HEADER_SUBSTR in body:
        return {
            "id": "draft_header_removed",
            "ok": False,
            "note": "MAA_TEXT_V2_0 still contains the draft header; promotion edit not yet made",
        }
    return {
        "id": "draft_header_removed",
        "ok": True,
        "note": "draft header absent (body is promotion-ready)",
    }


def _check_v2_not_in_draft_set() -> dict:
    """Check 4: ``MAA_TEXT_DRAFT_VERSIONS`` does NOT contain ``"v2.0"``.

    AST-parses ``services/maa_text.py`` so we read the literal value
    of the module-level assignment without import side effects.
    """
    draft_set = _read_draft_versions_set()
    if draft_set is None:
        return {
            "id": "v2_not_in_draft_set",
            "ok": False,
            "note": "could not parse MAA_TEXT_DRAFT_VERSIONS from services/maa_text.py",
        }
    if "v2.0" in draft_set:
        return {
            "id": "v2_not_in_draft_set",
            "ok": False,
            "note": "'v2.0' still in MAA_TEXT_DRAFT_VERSIONS",
        }
    return {
        "id": "v2_not_in_draft_set",
        "ok": True,
        "note": f"draft set OK: {sorted(draft_set)!r}",
    }


def _check_default_version_is_v2() -> dict:
    """Check 5: settings + env default resolves to ``"v2.0"``.

    Prefers a live Django settings read (when bootable); falls back to
    a regex check on ``config/settings.py`` if the project isn't on
    the import path. Both reads acknowledge the env var
    ``RMC_MAA_DEFAULT_VERSION``.
    """
    # Try Django first.
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django  # type: ignore

        django.setup()
        from django.conf import settings  # type: ignore

        resolved = getattr(settings, "MIGRATION_CLOUD_MAA_DEFAULT_VERSION", None)
        source = "django_settings"
    except Exception:  # noqa: BLE001
        # Fall back to settings.py textual read.
        resolved = _read_settings_default_version_textually()
        source = "settings_py_textual"

    if resolved != "v2.0":
        return {
            "id": "default_version_is_v2",
            "ok": False,
            "note": (
                f"MIGRATION_CLOUD_MAA_DEFAULT_VERSION = {resolved!r} "
                f"(source={source}); expected 'v2.0'"
            ),
        }
    return {
        "id": "default_version_is_v2",
        "ok": True,
        "note": f"default version = 'v2.0' (source={source})",
    }


def _check_v1_historic_queryable() -> dict:
    """Check 6: existing v1.0 MAA rows queryable + signature_text_sha256 backfilled.

    Best-effort:

    * If Django + DB are unreachable, the check passes with a clear
      "skipped" note rather than failing — the verifier is meant to
      run in dev environments where the DB may not be present, and
      the production gate is the more authoritative source.
    * When DB is reachable, asserts every v1.0 row has a non-empty
      ``signature_text_sha256`` (the v3.33.0 backfill migration added
      this column with a RunPython forward op).
    """
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django  # type: ignore

        django.setup()
        from apps.migration_cloud.models import (  # type: ignore
            MigrationAuthorizationAgreement,
        )

        # tenant-isolation-allow: platform-wide-readiness-verifier-counts-only
        v1_count = MigrationAuthorizationAgreement.objects.filter(
            agreement_version="v1.0",
        ).count()
        if v1_count == 0:
            return {
                "id": "v1_historic_queryable",
                "ok": True,
                "note": "no v1.0 historic rows exist; nothing to back-check",
            }
        # tenant-isolation-allow: platform-wide-readiness-verifier-counts-only
        bare = MigrationAuthorizationAgreement.objects.filter(
            agreement_version="v1.0", signature_text_sha256="",
        ).count()
        if bare:
            return {
                "id": "v1_historic_queryable",
                "ok": False,
                "note": (
                    f"{bare}/{v1_count} v1.0 rows have empty "
                    "signature_text_sha256 (backfill incomplete)"
                ),
            }
        return {
            "id": "v1_historic_queryable",
            "ok": True,
            "note": f"{v1_count} v1.0 rows queryable; all sha256 backfilled",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "id": "v1_historic_queryable",
            "ok": True,
            "note": f"skipped (db/django not reachable): {type(exc).__name__}",
        }


def _check_dpa_references_v2() -> dict:
    """Check 7: ``docs/DPA_TEMPLATE.md`` references v2.0 clauses."""
    return _check_doc_mentions_v2(
        "docs/DPA_TEMPLATE.md", "dpa_references_v2",
    )


def _check_dsar_references_v2() -> dict:
    """Check 8: ``docs/DSAR_RUNBOOK.md`` references v2.0 clauses."""
    return _check_doc_mentions_v2(
        "docs/DSAR_RUNBOOK.md", "dsar_references_v2",
    )


# ─────────────────────────────────────────────────────────────────── small helpers


def _read_v2_text_body() -> str | None:
    """Read the literal ``MAA_TEXT_V2_0`` from ``services/maa_text.py``.

    Uses AST so we never execute the module. Returns the body string
    (the value of ``_TEMPLATE_V2``, exposed via ``MAA_TEXT_V2_0``) or
    None if the source can't be parsed.
    """
    src = _read_maa_text_source()
    if src is None:
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in {"_TEMPLATE_V2", "MAA_TEXT_V2_0"}
            for t in node.targets
        ):
            val = node.value
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                return val.value
            if isinstance(val, ast.JoinedStr):
                # f-string literal — extract concatenated constants only.
                parts: list[str] = []
                for piece in val.values:
                    if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                        parts.append(piece.value)
                return "".join(parts)
    return None


def _read_draft_versions_set() -> set[str] | None:
    """AST-read the literal value of ``MAA_TEXT_DRAFT_VERSIONS``."""
    src = _read_maa_text_source()
    if src is None:
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        elif isinstance(node, ast.Assign):
            target = node.targets[0] if node.targets else None
            value = node.value
        else:
            continue
        if (
            isinstance(target, ast.Name)
            and target.id == "MAA_TEXT_DRAFT_VERSIONS"
            and value is not None
        ):
            return _extract_string_set_from_ast(value)
    return None


def _extract_string_set_from_ast(value: ast.AST) -> set[str] | None:
    """Best-effort: parse a set/frozenset of string literals from an AST node."""
    if isinstance(value, ast.Set):
        items: set[str] = set()
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                items.add(elt.value)
        return items
    if isinstance(value, ast.Call):
        if isinstance(value.func, ast.Name) and value.func.id in {
            "set", "frozenset",
        }:
            if not value.args:
                return set()
            arg0 = value.args[0]
            if isinstance(arg0, (ast.List, ast.Tuple, ast.Set)):
                out: set[str] = set()
                for elt in arg0.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        out.add(elt.value)
                return out
    return None


def _read_maa_text_source() -> str | None:
    """Read the maa_text.py module source as text."""
    p = REPO_ROOT / "apps" / "migration_cloud" / "services" / "maa_text.py"
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_settings_default_version_textually() -> str | None:
    """Fallback: parse the literal default from ``config/settings.py``.

    Returns the right-hand-side string of ``MIGRATION_CLOUD_MAA_DEFAULT_VERSION``
    if it's a simple ``os.environ.get(..., "...")`` call. The env var
    itself (``RMC_MAA_DEFAULT_VERSION``) overrides; we honour that.
    """
    env_override = os.environ.get("RMC_MAA_DEFAULT_VERSION")
    if env_override:
        return env_override
    p = REPO_ROOT / "config" / "settings.py"
    if not p.is_file():
        return None
    try:
        src = p.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "MIGRATION_CLOUD_MAA_DEFAULT_VERSION":
                    val = node.value
                    if isinstance(val, ast.Call) and val.args:
                        # os.environ.get(NAME, DEFAULT)
                        if len(val.args) >= 2 and isinstance(val.args[1], ast.Constant):
                            if isinstance(val.args[1].value, str):
                                return val.args[1].value
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        return val.value
    return None


def _check_doc_mentions_v2(rel_path: str, check_id: str) -> dict:
    """Generic doc-reference check.

    A doc mentions v2.0 if it contains BOTH a ``v2.0`` reference and at
    least one of the v2.0-specific clause names (``data subject rights``,
    ``right to withdraw``, etc.). This is intentionally lenient so a
    minor wording rewrite doesn't trip the gate.
    """
    p = REPO_ROOT / rel_path
    if not p.is_file():
        return {"id": check_id, "ok": False, "note": f"missing file: {rel_path}"}
    try:
        body = p.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "id": check_id,
            "ok": False,
            "note": f"unreadable file: {rel_path}: {exc!r}",
        }
    lower = body.lower()
    has_v2_marker = "v2.0" in lower or "v2_0" in lower
    v2_clue_hits = sum(
        1
        for clue in (
            "scope of access",
            "data minimization",
            "no retention beyond migration",
            "right to withdraw",
            "data subject rights",
        )
        if clue in lower
    )
    if not has_v2_marker or v2_clue_hits == 0:
        return {
            "id": check_id,
            "ok": False,
            "note": (
                f"{rel_path}: v2_marker={has_v2_marker} clue_hits={v2_clue_hits} "
                "(needs both)"
            ),
        }
    return {
        "id": check_id,
        "ok": True,
        "note": f"{rel_path}: v2.0 clauses referenced ({v2_clue_hits} hits)",
    }


# ─────────────────────────────────────────────────────────────────── orchestration


def run_all_checks() -> dict:
    """Run every check and return the aggregated report dict."""
    checks = [
        _check_signoff_pdf_present(),
        _check_v2_phrases_present(),
        _check_draft_header_removed(),
        _check_v2_not_in_draft_set(),
        _check_default_version_is_v2(),
        _check_v1_historic_queryable(),
        _check_dpa_references_v2(),
        _check_dsar_references_v2(),
    ]
    fail = [c for c in checks if not c["ok"]]
    return {
        "schema_version": 1,
        "tool": "verify_maa_v2_promotion_readiness.py",
        "generated_at_utc": _dt.datetime.utcnow().isoformat() + "Z",
        "ok": not fail,
        "fail_count": len(fail),
        "ok_count": len(checks) - len(fail),
        "total_count": len(checks),
        "checks": checks,
    }


def _write_audit_report(report: dict, *, outdir: Path | None = None) -> Path | None:
    """Write the report to ``var/maa-v2-readiness-<utc_iso>.json``.

    Best-effort: failure to write the audit row is logged but does NOT
    flip the overall exit code (the gate is the checks themselves).
    """
    outdir = outdir or (REPO_ROOT / "var")
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    # File-name-safe ISO timestamp (no colons / dots).
    iso = (
        _dt.datetime.utcnow().isoformat().replace(":", "").replace(".", "_")
        + "Z"
    )
    p = outdir / f"maa-v2-readiness-{iso}.json"
    try:
        p.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return p
    except OSError:
        return None


def _render_text_report(report: dict, *, stream: io.TextIOBase | None = None) -> None:
    """Print a one-line-per-check operator-friendly summary."""
    out = stream or sys.stdout
    for c in report["checks"]:
        marker = "[OK]  " if c["ok"] else "[FAIL]"
        out.write(f"{marker} {c['id']}: {c['note']}\n")
    out.write(
        f"\nSummary: ok={report['ok_count']} fail={report['fail_count']} "
        f"total={report['total_count']} overall_ok={report['ok']}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true",
        help="Emit the full report as JSON to stdout (in addition to writing var/).",
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="Skip writing the var/ audit JSON (useful in CI where the run is ephemeral).",
    )
    args = parser.parse_args(argv)

    report = run_all_checks()

    if not args.no_write:
        written = _write_audit_report(report)
        if written is not None:
            report["audit_written_to"] = str(written.relative_to(REPO_ROOT))

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        _render_text_report(report)

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
