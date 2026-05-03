#!/usr/bin/env python3
"""
Emit docs/generated/category_scope_review.{json,md} from system_closure_map.json.

systems_in_registry mirrors closure-map rows with honest classifications:
  - closed: gap_status closed and empty missing_pieces
  - partial_external_blocker: global_payments (explicit)
  - partial_repo_gaps: other partial rows with repo-expandable missing_pieces

Does not claim FULL MARKET category defining when partial_repo_gaps exist.

Usage:
  python scripts/generate_category_scope_review.py --write \\
      [--merge-proof-gates docs/generated/category_scope_review.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLOSURE_PATH = REPO / "docs" / "generated" / "system_closure_map.json"
EXT_REG_PATH = REPO / "docs" / "generated" / "external_dependencies_register.json"
OUT_JSON = REPO / "docs" / "generated" / "category_scope_review.json"
OUT_MD = REPO / "docs" / "generated" / "category_scope_review.md"


def _external_register_bundle(partial_external_ids: list[str]) -> dict:
    """Summarize generated external-dependencies ledger when present."""
    rel = "docs/generated/external_dependencies_register.json"
    missing = {
        "external_dependency_register_path": None,
        "external_blockers_summary": (
            "External dependency register not generated — run "
            "`python scripts/generate_external_dependencies_register.py --write`."
        ),
        "external_blockers_by_blocking_level": {},
        "systems_blocked_by_external_dependencies": sorted(partial_external_ids),
    }
    if not EXT_REG_PATH.is_file():
        return missing
    try:
        reg = json.loads(EXT_REG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return missing

    counts = dict(reg.get("blocking_level_counts") or {})
    flat = reg.get("entries_flat") or []
    n = len(flat)
    summary = (
        f"{n} tracked dependencies; blocking_level_counts={counts}; "
        f"see `{rel}` for PSP/KYC/settlement rows."
    )
    impacted = sorted(set(reg.get("systems_impacted") or []) | set(partial_external_ids))
    return {
        "external_dependency_register_path": rel,
        "external_blockers_summary": summary,
        "external_blockers_by_blocking_level": counts,
        "systems_blocked_by_external_dependencies": impacted,
    }


def _classify_row(row: dict) -> tuple[str, bool, bool, str]:
    """
    Returns:
      classification label,
      repo_actionable_remaining,
      external_only_remaining,
      missing_pieces_summary (short)
    """
    sid = row.get("id") or ""
    gap = (row.get("gap_status") or "").lower()
    missing = row.get("missing_pieces") or []
    summary = "; ".join(str(x) for x in missing[:3]) if missing else ""

    if gap == "closed" and not missing:
        return "closed", False, False, ""

    if sid == "global_payments" and gap == "partial":
        return "partial_external_blocker", False, True, summary or (
            "live PSP / production gateway truth external to repo"
        )

    if sid == "marketplace_monetization" and gap == "partial":
        return "partial_external_blocker", False, True, summary or (
            "live PSP settlement truth external (ties to global_payments)"
        )

    if gap == "partial":
        return "partial_repo_gaps", True, False, summary or "(see closure map missing_pieces)"

    return "unknown", True, False, summary


def _build_review(closure: dict, merge_proof: dict | None) -> dict:
    systems = closure.get("systems") or []
    rows_out = []
    requested_missing = []
    want = {"experience_control", "marketplace_monetization", "enterprise_security"}
    seen = set()

    for row in systems:
        sid = row.get("id")
        if not sid:
            continue
        seen.add(sid)
        clsf, repo_gap, ext_only, summ = _classify_row(row)
        rows_out.append(
            {
                "id": sid,
                "gap_status": row.get("gap_status"),
                "missing_pieces_summary": summ or None,
                "repo_actionable_remaining": repo_gap,
                "external_only_remaining": ext_only,
                "classification": clsf,
            }
        )

    for label in sorted(want - seen):
        requested_missing.append(label)

    partial_repo = [r["id"] for r in rows_out if r["classification"] == "partial_repo_gaps"]
    partial_ext = [r["id"] for r in rows_out if r["classification"] == "partial_external_blocker"]

    if partial_repo:
        joined = ", ".join(partial_repo)
        cat = (
            "CATEGORY DEFINING — LIMITED REGISTRY SCOPE — partial_repo_gaps on "
            + joined
            + "; not FULL MARKET"
        )
        floor = (
            "PLATFORM LEVEL READY — repo gaps on expanded pillars + external PSP residual "
            "(global_payments)"
        )
        verdict = (
            "CATEGORY DEFINING — LIMITED REGISTRY SCOPE — "
            + joined
            + " remain partial with repo-expandable missing_pieces"
        )
    else:
        cat = "CATEGORY DEFINING — REPO SCOPE — external blockers remain"
        floor = "PLATFORM LEVEL READY — external blockers remain"
        verdict = "CATEGORY DEFINING — REPO SCOPE"

    full_market_blocked = []
    full_market_blocked.extend(partial_ext)
    full_market_blocked.extend([f"{pid} repo-expandable gaps" for pid in partial_repo])

    proof_gates = dict(merge_proof or {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    ext_bundle = _external_register_bundle(partial_ext)

    return {
        "schema_version": 3,
        "generated_at": now,
        "review_engine": "Category Scope Review (derived from system_closure_map)",
        "source_closure_map": "docs/generated/system_closure_map.json",
        **ext_bundle,
        "systems_in_registry": rows_out,
        "systems_requested_but_not_in_closure_map": requested_missing,
        "note_not_in_registry": (
            "These labels were flagged before closure-map expansion; should be empty "
            "once experience_control, marketplace_monetization, enterprise_security "
            "exist in PROGRAM_SYSTEMS."
            if requested_missing
            else "All Path B expansion labels present in closure map systems[]."
        ),
        "repo_controlled_scope": [
            "Application code paths covered by shipped slices",
            "Tests and mechanical verifiers",
            "Operator dashboards and configuration contracts surfaced in-repo",
            "Adaptor/metadata gateway health checks without live charges",
            "Tenant isolation and audit logs where implemented",
        ],
        "external_controlled_scope": [
            "PSP merchant account approval and production credentials",
            "Production payment-gateway connectivity probes beyond honest metadata checks",
            "Bank/partner contracts",
            "SOC2/ISO attestations not represented as code",
            "App store publication and third-party edu vendor approvals where applicable",
        ],
        "category_classification": cat,
        "floor_classification": floor,
        "full_market_blocked_by": full_market_blocked or ["(none enumerated)"],
        "proof_gates": proof_gates,
        "final_verdict": verdict,
    }


def _render_md(data: dict) -> str:
    lines = [
        "# Category scope review (program_gap_registry / system_closure_map)",
        "",
        f"**Date:** {data['generated_at']}  ",
        f"**Inputs:** `{data['source_closure_map']}`  ",
        f"**Verdict:** **{data['final_verdict']}**",
        "",
        "## Systems in `systems[]`",
        "",
        "| System | gap_status | Classification | Repo-actionable gap? | External-only? | Notes |",
        "|--------|------------|----------------|----------------------|----------------|-------|",
    ]
    for r in data["systems_in_registry"]:
        repo = "yes" if r["repo_actionable_remaining"] else "no"
        ext = "yes" if r["external_only_remaining"] else "no"
        gp = r.get("gap_status") or ""
        cls = r.get("classification") or ""
        summ = r.get("missing_pieces_summary") or ""
        note = summ.replace("|", "\\|")[:120] + ("…" if len(summ) > 120 else "") if summ else "—"
        lines.append(f"| {r['id']} | {gp} | {cls} | {repo} | {ext} | {note} |")
    lines.extend(
        [
            "",
        "## External dependency register linkage",
        "",
        f"- **Path:** `{data.get('external_dependency_register_path') or '(not generated)'}`",
        f"- **Summary:** {data.get('external_blockers_summary') or '—'}",
        f"- **Blocking levels:** `{data.get('external_blockers_by_blocking_level')}`",
        f"- **Systems impacted / blocked-by-external union:** "
        f"{', '.join(data.get('systems_blocked_by_external_dependencies') or [])}",
        "",
        "## Labels previously missing from closure map",
        "",
    ]
    )
    missing = data.get("systems_requested_but_not_in_closure_map") or []
    if missing:
        lines.append("Still missing as `systems[]` rows: **" + ", ".join(missing) + "**")
    else:
        lines.append(
            "_None — `experience_control`, `marketplace_monetization`, `enterprise_security` "
            "are present in the closure map registry._"
        )
    lines.extend(
        [
            "",
            "## Classification rule summary",
            "",
            "- **partial_repo_gaps:** `missing_pieces` require more in-repo tests/surfaces "
            "(not honest to claim FULL MARKET category defining).",
            "- **partial_external_blocker:** `global_payments` live PSP truth outside repo.",
            "- Marketing route/chrome cleanup supports **experience_control** evidence only; "
            "it does not close marketplace monetization or enterprise security.",
            "",
            "## Proof gates",
            "",
            "See `category_scope_review.json` key `proof_gates` (populated after verifier runs).",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="Write JSON + MD")
    ap.add_argument(
        "--merge-proof-gates",
        type=Path,
        help="Existing JSON file whose proof_gates object to preserve/merge",
    )
    args = ap.parse_args(argv)

    if not CLOSURE_PATH.is_file():
        print(f"missing {CLOSURE_PATH}", file=sys.stderr)
        return 1
    closure = json.loads(CLOSURE_PATH.read_text(encoding="utf-8"))

    merge_proof = None
    if args.merge_proof_gates and args.merge_proof_gates.is_file():
        merge_proof = json.loads(args.merge_proof_gates.read_text(encoding="utf-8")).get(
            "proof_gates"
        )

    data = _build_review(closure, merge_proof)

    if args.write:
        OUT_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(_render_md(data), encoding="utf-8")
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_MD}")
        return 0

    print(json.dumps(data, indent=2))
    print("Dry-run; pass --write", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
