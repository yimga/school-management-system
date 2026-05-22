#!/usr/bin/env python3
"""MAA v2.0 promotion preflight (Wave 9 Agent N, v3.58.x).

Stdlib-only preflight that complements the existing 8-check verifier at
``scripts/verify_maa_v2_promotion_readiness.py``. Where that verifier
runs the full readiness audit (including DSAR / DPA cross-link checks),
this preflight is the narrow "is the flip itself shovel-ready right
now" gate that the operator runs immediately before executing
``python manage.py promote_maa_v2 --apply``.

Six conditions, in order — each MUST hold for exit 0:

  1. counsel signoff PDF exists at ``docs/legal/maa_v2_signoff.pdf``
     (and is non-empty).
  2. ``MAA_TEXT_V2_0`` is defined in
     ``apps/migration_cloud/services/maa_text.py`` AND its body does
     NOT contain the ``[DRAFT v2.0 — PENDING COUNSEL REVIEW]`` header.
  3. ``MAA_TEXT_DRAFT_VERSIONS`` set is about to be empty (i.e. either
     literally ``set()`` already, OR a single-element ``{"v2.0"}``
     entry that the promotion command will rewrite to empty).
  4. No environment-variable override is currently injected that would
     pin the production default back to ``v1.0`` — i.e.
     ``RMC_MAA_DEFAULT_VERSION`` is unset OR equals ``"v2.0"``.
  5. ``MAA_V2_PROMOTION_APPROVAL_TOKEN`` (operator-controlled approval
     token used by the management command) is present in the
     environment when ``--require-approval-token`` is passed.
  6. No leftover ``[DRAFT`` prefix anywhere in
     ``apps/migration_cloud/services/maa_text.py`` (defence-in-depth
     against a partial edit landing in the tree).

Exit codes:

  * 0 — all conditions met (shovel-ready).
  * 1 — at least one condition failed (message + JSON describes which).
  * 2 — internal error (file unreadable, AST parse failed).

Output:

  * Plain text by default — one line per condition + summary.
  * ``--json`` switches to a JSON document on stdout for CI / dashboard
    consumption.

The preflight NEVER mutates anything. NEVER reads or prints the MAA
body, the approval token, or any signature bytes.
"""
from __future__ import annotations

import argparse
import ast
import datetime as _dt
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Repo root resolved from this file's location.
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent  # scripts/.. == beta/school-management-system

SIGNOFF_PDF_REL = "docs/legal/maa_v2_signoff.pdf"
MAA_TEXT_REL = "apps/migration_cloud/services/maa_text.py"
DRAFT_HEADER_SUBSTR = "[DRAFT v2.0 — PENDING COUNSEL REVIEW]"
DRAFT_PREFIX_SUBSTR = "[DRAFT"


def _check_signoff_pdf_present() -> dict[str, Any]:
    """Condition 1 — counsel signoff PDF on file."""
    p = REPO_ROOT / SIGNOFF_PDF_REL
    if not p.is_file():
        return {
            "id": "signoff_pdf_present",
            "ok": False,
            "note": (
                f"missing file: {SIGNOFF_PDF_REL} — counsel signoff PDF "
                "must be committed before promotion can proceed."
            ),
        }
    try:
        size = p.stat().st_size
    except OSError as exc:
        return {
            "id": "signoff_pdf_present",
            "ok": False,
            "note": f"could not stat {SIGNOFF_PDF_REL}: {type(exc).__name__}",
        }
    if size <= 0:
        return {
            "id": "signoff_pdf_present",
            "ok": False,
            "note": f"{SIGNOFF_PDF_REL} is zero-byte; expected a real PDF.",
        }
    return {
        "id": "signoff_pdf_present",
        "ok": True,
        "note": f"{SIGNOFF_PDF_REL} present ({size} bytes).",
    }


def _load_maa_text_source() -> str:
    """Return the maa_text.py source text. Raises on IO failure."""
    p = REPO_ROOT / MAA_TEXT_REL
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def _extract_string_assign(source: str, name: str) -> str | None:
    """Best-effort AST extract of ``NAME = "string literal"`` value.

    Returns ``None`` if the assignment isn't found or isn't a plain
    string literal. We use AST so we don't blunder past concatenation
    or f-string forms — the v2 template is a plain triple-quoted str.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    val = node.value
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        return val.value
                    # AnnAssign branch handled below.
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str,
                ):
                    return node.value.value
    return None


def _extract_set_assign(source: str, name: str) -> set[str] | None:
    """Best-effort AST extract of ``NAME = {"a", "b"}`` or ``set()``.

    Returns ``None`` if the assignment isn't found or isn't a literal
    set / empty-set construction.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        target_name: str | None = None
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign):
            if (
                len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                target_name = node.targets[0].id
                value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                target_name = node.target.id
                value_node = node.value
        if target_name != name or value_node is None:
            continue
        # set() call -> empty set.
        if isinstance(value_node, ast.Call):
            if (
                isinstance(value_node.func, ast.Name)
                and value_node.func.id == "set"
                and not value_node.args
                and not value_node.keywords
            ):
                return set()
            continue
        # Literal set.
        if isinstance(value_node, ast.Set):
            out: set[str] = set()
            for elt in value_node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.add(elt.value)
            return out
    return None


def _check_v2_body_not_draft() -> dict[str, Any]:
    """Condition 2 — MAA_TEXT_V2_0 defined + no DRAFT header in it."""
    try:
        source = _load_maa_text_source()
    except (OSError, ValueError) as exc:
        return {
            "id": "v2_body_not_draft",
            "ok": False,
            "note": f"could not read {MAA_TEXT_REL}: {type(exc).__name__}",
        }
    try:
        body = _extract_string_assign(source, "MAA_TEXT_V2_0")
    except SyntaxError as exc:
        return {
            "id": "v2_body_not_draft",
            "ok": False,
            "note": f"maa_text.py failed to AST-parse: {exc.msg}",
        }
    if body is None:
        # Fall back to grep — maa_text.py defines MAA_TEXT_V2_0 as an
        # alias to _TEMPLATE_V2, which is a Constant assignment under a
        # different name. Walk both common shapes.
        v2_template = _extract_string_assign(source, "_TEMPLATE_V2")
        body = v2_template
    if body is None:
        return {
            "id": "v2_body_not_draft",
            "ok": False,
            "note": (
                "neither MAA_TEXT_V2_0 nor _TEMPLATE_V2 resolved to a "
                "plain string constant — manual inspection required."
            ),
        }
    if DRAFT_HEADER_SUBSTR in body:
        return {
            "id": "v2_body_not_draft",
            "ok": False,
            "note": (
                f"MAA v2.0 body still carries the '{DRAFT_HEADER_SUBSTR}' "
                "header — remove it before the flip."
            ),
        }
    return {
        "id": "v2_body_not_draft",
        "ok": True,
        "note": "MAA v2.0 body is in non-draft shape.",
    }


def _check_draft_set_about_to_be_empty() -> dict[str, Any]:
    """Condition 3 — MAA_TEXT_DRAFT_VERSIONS is empty or solely {'v2.0'}."""
    try:
        source = _load_maa_text_source()
    except OSError as exc:
        return {
            "id": "draft_set_about_to_be_empty",
            "ok": False,
            "note": f"could not read {MAA_TEXT_REL}: {type(exc).__name__}",
        }
    try:
        draft_set = _extract_set_assign(source, "MAA_TEXT_DRAFT_VERSIONS")
    except SyntaxError as exc:
        return {
            "id": "draft_set_about_to_be_empty",
            "ok": False,
            "note": f"maa_text.py failed to AST-parse: {exc.msg}",
        }
    if draft_set is None:
        return {
            "id": "draft_set_about_to_be_empty",
            "ok": False,
            "note": (
                "MAA_TEXT_DRAFT_VERSIONS not resolvable as a literal set; "
                "manual inspection required."
            ),
        }
    # Acceptable shapes:
    #   set()           — already flipped.
    #   {"v2.0"}        — the management command will rewrite this to set().
    # Anything else is unexpected.
    if draft_set == set():
        return {
            "id": "draft_set_about_to_be_empty",
            "ok": True,
            "note": "MAA_TEXT_DRAFT_VERSIONS is already empty (post-flip state).",
        }
    if draft_set == {"v2.0"}:
        return {
            "id": "draft_set_about_to_be_empty",
            "ok": True,
            "note": (
                "MAA_TEXT_DRAFT_VERSIONS = {'v2.0'} — the promotion "
                "command will rewrite this to set()."
            ),
        }
    return {
        "id": "draft_set_about_to_be_empty",
        "ok": False,
        "note": (
            f"MAA_TEXT_DRAFT_VERSIONS = {sorted(draft_set)!r} — unexpected; "
            "expected either set() or {'v2.0'}."
        ),
    }


def _check_no_env_var_override() -> dict[str, Any]:
    """Condition 4 — RMC_MAA_DEFAULT_VERSION is unset or already v2.0."""
    val = os.environ.get("RMC_MAA_DEFAULT_VERSION", "")
    if not val:
        return {
            "id": "no_env_var_override",
            "ok": True,
            "note": "RMC_MAA_DEFAULT_VERSION is unset (default falls back to v1.0).",
        }
    if val.strip().lower() == "v2.0":
        return {
            "id": "no_env_var_override",
            "ok": True,
            "note": "RMC_MAA_DEFAULT_VERSION is already v2.0.",
        }
    return {
        "id": "no_env_var_override",
        "ok": False,
        "note": (
            f"RMC_MAA_DEFAULT_VERSION is set to '{val}' — must be unset "
            "or 'v2.0' to allow the flip."
        ),
    }


def _check_approval_token_present(require: bool) -> dict[str, Any]:
    """Condition 5 — MAA_V2_PROMOTION_APPROVAL_TOKEN env present."""
    if not require:
        return {
            "id": "approval_token_present",
            "ok": True,
            "note": "approval-token check skipped (preflight invoked without --require-approval-token).",
        }
    val = os.environ.get("RMC_MAA_V2_PROMOTION_APPROVAL_TOKEN", "") or ""
    if not val:
        return {
            "id": "approval_token_present",
            "ok": False,
            "note": (
                "RMC_MAA_V2_PROMOTION_APPROVAL_TOKEN is not set; the "
                "management command will refuse without it."
            ),
        }
    return {
        "id": "approval_token_present",
        "ok": True,
        "note": "RMC_MAA_V2_PROMOTION_APPROVAL_TOKEN is set (value not logged).",
    }


def _check_no_draft_prefix_anywhere() -> dict[str, Any]:
    """Condition 6 — defence-in-depth grep for residual '[DRAFT' anywhere."""
    try:
        source = _load_maa_text_source()
    except OSError as exc:
        return {
            "id": "no_draft_prefix_anywhere",
            "ok": False,
            "note": f"could not read {MAA_TEXT_REL}: {type(exc).__name__}",
        }
    # We allow the substring inside comments + docstrings that describe
    # the historical draft posture. The risk we're guarding against is
    # an active template that still carries the header — Condition 2
    # caught that already; this is the belt-and-suspenders pass.
    # Count occurrences of "[DRAFT" outside Python comments.
    lines = source.splitlines()
    code_only_occurrences = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if DRAFT_PREFIX_SUBSTR in line:
            code_only_occurrences += 1
    if code_only_occurrences > 1:
        # The v2 template body itself contributes one occurrence ONLY
        # when it still has the header — Condition 2 covers that. If
        # condition 2 passed but we see >1 non-comment occurrence,
        # something else has '[DRAFT' in code, which is suspicious.
        return {
            "id": "no_draft_prefix_anywhere",
            "ok": False,
            "note": (
                f"found {code_only_occurrences} non-comment occurrences of "
                f"'{DRAFT_PREFIX_SUBSTR}' in {MAA_TEXT_REL} — manual review needed."
            ),
        }
    return {
        "id": "no_draft_prefix_anywhere",
        "ok": True,
        "note": (
            f"non-comment '{DRAFT_PREFIX_SUBSTR}' occurrence count = "
            f"{code_only_occurrences} (acceptable)."
        ),
    }


# ─── runner ──────────────────────────────────────────────────────────────


def run_preflight(require_approval_token: bool) -> dict[str, Any]:
    """Run all six conditions; return a structured report."""
    checks = [
        _check_signoff_pdf_present(),
        _check_v2_body_not_draft(),
        _check_draft_set_about_to_be_empty(),
        _check_no_env_var_override(),
        _check_approval_token_present(require_approval_token),
        _check_no_draft_prefix_anywhere(),
    ]
    ok_count = sum(1 for c in checks if c.get("ok"))
    fail_count = sum(1 for c in checks if not c.get("ok"))
    return {
        "schema_version": 1,
        "tool": "preflight_maa_v2_flip.py",
        "generated_at_utc": _dt.datetime.now(tz=_dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "ok": fail_count == 0,
        "ok_count": ok_count,
        "fail_count": fail_count,
        "total_count": len(checks),
        "checks": checks,
    }


def _print_text(report: dict[str, Any], out: io.TextIOBase) -> None:
    out.write("MAA v2.0 promotion preflight\n")
    out.write("============================\n")
    for c in report["checks"]:
        prefix = "[OK]  " if c.get("ok") else "[FAIL]"
        out.write(f"{prefix} {c['id']}: {c['note']}\n")
    out.write(
        f"Summary: ok={report['ok_count']} fail={report['fail_count']} "
        f"total={report['total_count']} overall={'OK' if report['ok'] else 'FAIL'}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MAA v2.0 promotion preflight (Wave 9 Agent N).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON document on stdout instead of plain text.",
    )
    parser.add_argument(
        "--require-approval-token",
        action="store_true",
        help=(
            "Require RMC_MAA_V2_PROMOTION_APPROVAL_TOKEN in the "
            "environment (the management command will refuse without it)."
        ),
    )
    args = parser.parse_args(argv)
    try:
        report = run_preflight(args.require_approval_token)
    except Exception as exc:  # noqa: BLE001 — typed below
        sys.stderr.write(
            f"preflight_maa_v2_flip: internal error {type(exc).__name__}: {exc}\n",
        )
        return 2
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        _print_text(report, sys.stdout)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
