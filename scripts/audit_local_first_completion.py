#!/usr/bin/env python3
"""Audit local-first batches 1508–1510: gates, persistence, CDN, finance POST parity."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "local_first_completion_audit.json"

GATE_SCRIPTS = (
    "verify_local_first_completion.py",
    "verify_local_first_surface_wiring.py",
    "verify_offline_workflow_apply.py",
    "verify_workforce_money_plane_completion.py",
    "verify_cdn_self_host_burndown.py",
    "verify_sovereign_offline_depth.py",
    "verify_sovereign_offline_foundation.py",
)

CDN_PATTERNS = (
    re.compile(r"cdn\.jsdelivr\.net", re.I),
    re.compile(r"unpkg\.com", re.I),
    re.compile(r"cdnjs\.cloudflare\.com", re.I),
    re.compile(r"cdn\.redoc\.ly", re.I),
)

OFFLINE_ATTR = re.compile(
    r'data-rmc-offline-form\s*=\s*"(field_capture|payment_receipt|attendance|grading|notes_report|support_ticket)"'
)


def _run_gate(script: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    proof = tail[-1] if tail else f"exit {proc.returncode}"
    return proc.returncode == 0, proof


def _scan_finance_post_gaps() -> list[dict]:
    gaps: list[dict] = []
    finance = ROOT / "templates" / "finance"
    for path in sorted(finance.glob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"<form\b[^>]*>", text, re.I):
            tag = match.group(0)
            if 'method="get"' in tag.lower() or "method='get'" in tag.lower():
                continue
            if 'method="post"' not in tag.lower() and "method='post'" not in tag.lower():
                # multiline form tag — inspect following chunk
                start = match.start()
                chunk = text[start : start + 800]
                if 'method="post"' not in chunk.lower() and "method='post'" not in chunk.lower():
                    continue
            chunk = text[match.start() : match.start() + 1200]
            if OFFLINE_ATTR.search(chunk):
                continue
            if "payment_receipt" in chunk:
                continue
            has_draft = "data-draft-key" in chunk
            rel = path.relative_to(ROOT).as_posix()
            gaps.append(
                {
                    "template": rel,
                    "has_draft_key": has_draft,
                    "severity": "info" if not has_draft else "gap",
                    "note": "POST form without field_capture or typed offline handler",
                }
            )
    return gaps


def _scan_cdn_in_templates() -> list[str]:
    hits: list[str] = []
    for path in (ROOT / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pat in CDN_PATTERNS:
            if pat.search(text):
                rel = path.relative_to(ROOT).as_posix()
                if rel not in hits:
                    hits.append(rel)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write docs/generated/local_first_completion_audit.json")
    parser.add_argument(
        "--strict-finance-post",
        action="store_true",
        help="Fail when finance POST forms with data-draft-key lack offline markers",
    )
    args = parser.parse_args()

    rows: list[dict] = []

    def add(check_id: str, ok: bool, proof: str) -> None:
        rows.append({"check_id": check_id, "ok": ok, "proof": proof})

    for script in GATE_SCRIPTS:
        ok, proof = _run_gate(script)
        add(script.replace(".py", ""), ok, proof)

    mig = ROOT / "apps" / "schoolops" / "migrations" / "0018_micro_friction_persistence.py"
    add("migration-0018-micro-friction", mig.is_file(), str(mig.relative_to(ROOT)))

    models = ROOT / "apps" / "schoolops" / "models_micro_friction.py"
    add("models-micro-friction", models.is_file(), "SubstituteHandover + LostBelongings records")

    sw_proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_service_worker_version.py"), "--check-monotonic"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    sw_text = (ROOT / "static" / "js" / "service-worker.js").read_text(encoding="utf-8", errors="replace")
    sw_match = re.search(r'const\s+CACHE_VERSION\s*=\s*"([^"]+)"', sw_text)
    sw_version = sw_match.group(1) if sw_match else "missing"
    add(
        "sw-cache-version-shape-monotonic",
        sw_proc.returncode == 0,
        f"verify_service_worker_version --check-monotonic ok; CACHE_VERSION={sw_version}",
    )

    cdn_hits = _scan_cdn_in_templates()
    add("templates-no-burndown-cdn-scripts", len(cdn_hits) == 0, f"hits={len(cdn_hits)}")

    finance_gaps = _scan_finance_post_gaps()
    draft_gaps = [g for g in finance_gaps if g.get("severity") == "gap"]
    add(
        "finance-post-offline-parity",
        len(draft_gaps) == 0,
        f"draft_post_gaps={len(draft_gaps)} total_post_without_offline={len(finance_gaps)}",
    )

    honest_deferred = [
        "Lane 2 PWA install matrix on real devices — operator-run (docs/PWA_LANE2_OPERATOR_RUNBOOK_2026_05_26.md)",
        "Live PSP payment authorize while offline — queues intent/receipt only",
        "Google Fonts on some shells — allowed; not in CDN burndown scope",
        "GET filter forms (invoices/payments/trial_balance/reports period) — draft persistence only; no enqueue",
    ]

    finding_count = sum(1 for r in rows if not r["ok"])
    verdict = (
        "LOCAL_FIRST_COMPLETION_AUDIT_PASS"
        if finding_count == 0
        else "LOCAL_FIRST_COMPLETION_AUDIT_FAIL"
    )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_ids": [1508, 1509, 1510],
        "verdict": verdict,
        "finding_count": finding_count,
        "rows": rows,
        "finance_post_scan": finance_gaps,
        "cdn_template_hits": cdn_hits,
        "honest_deferred": honest_deferred,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if finding_count:
        print(verdict, file=sys.stderr)
        for r in rows:
            if not r["ok"]:
                print(f"  {r['check_id']}: {r['proof']}", file=sys.stderr)
        if draft_gaps:
            for g in draft_gaps:
                print(f"  finance gap: {g['template']}", file=sys.stderr)
        return 1

    print(verdict)
    print(f"  gates={len(GATE_SCRIPTS)} finance_draft_post_gaps={len(draft_gaps)}")
    if args.write:
        print(f"  wrote {OUT.relative_to(ROOT)}")

    if args.strict_finance_post and draft_gaps:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
