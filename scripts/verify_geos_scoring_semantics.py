#!/usr/bin/env python3
"""
Verify 6-dimension honest GEOS scoring semantics on top of the legacy matrix.

Reads `docs/generated/greatest_education_os_matrix.json`, projects each pillar
into the 6-dimension model from apps.platform_runtime.geos_scoring_semantics,
and writes:

  docs/generated/geos_scoring_semantics_hardening.json
  docs/generated/geos_scoring_semantics_hardening.md

Exits 0 even when public_live_pct / external_vendor_pct are downgraded — the
gate exists to surface the honest reading, not to block CI on external
blockers.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apps.platform_runtime.geos_scoring_semantics import (  # noqa: E402
    aggregate,
    score_pillar,
)


LEGACY_MATRIX = ROOT / "docs" / "generated" / "greatest_education_os_matrix.json"
OUT_JSON = ROOT / "docs" / "generated" / "geos_scoring_semantics_hardening.json"
OUT_MD = ROOT / "docs" / "generated" / "geos_scoring_semantics_hardening.md"


# Honest evidence rules — flip to True only when on-disk proof lands.
PUBLIC_LIVE_EVIDENCE: dict[str, bool] = {
    "google": False,
    "shopify": False,
    "amazon": False,
    "linux": False,
    "aws": False,
    "localglobal": False,
    "dailyops": False,
    "salesforce": False,
}
EXTERNAL_VENDOR_EVIDENCE: dict[str, bool] = {
    "google": False,
    "shopify": False,
    "amazon": False,
    "linux": False,
    "aws": False,
    "localglobal": False,
    "dailyops": False,
    "salesforce": False,
}
PWA_BROWSER_EVIDENCE: dict[str, bool] = {
    # PWA proof artifacts present + service worker registered, but
    # install-prompt + offline-browser proof not yet harness-captured.
    "google": False,
    "shopify": False,
    "amazon": False,
    "linux": False,
    "aws": False,
    "localglobal": False,
    "dailyops": False,
    "salesforce": False,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write artifacts.")
    args = parser.parse_args()

    if not LEGACY_MATRIX.exists():
        print(f"missing {LEGACY_MATRIX}", file=sys.stderr)
        return 2
    data = json.loads(LEGACY_MATRIX.read_text(encoding="utf-8"))
    pillars = data.get("pillars", [])
    if not pillars:
        print("no pillars in legacy matrix", file=sys.stderr)
        return 2

    scores = []
    rows = []
    for p in pillars:
        pid = p["pillar_id"]
        score = score_pillar(
            pillar_id=pid,
            repo_pct=float(p.get("repo_pct", 0.0)),
            legacy_live_pct=float(p.get("live_pct", 0.0)),
            has_public_live_evidence=PUBLIC_LIVE_EVIDENCE.get(pid, False),
            has_external_vendor_evidence=EXTERNAL_VENDOR_EVIDENCE.get(pid, False),
            has_pwa_browser_evidence=PWA_BROWSER_EVIDENCE.get(pid, False),
        )
        scores.append(score)
        rows.append(score.to_dict())

    overall = aggregate(scores)

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch": 1504,
        "policy_note": (
            "6-dimension honest reading. composite_pct = min(repo, "
            "internal_pilot, public_live, pwa, external_vendor). Native app "
            "status is always DEFERRED in this batch — not failed."
        ),
        "evidence_flags": {
            "public_live": PUBLIC_LIVE_EVIDENCE,
            "external_vendor": EXTERNAL_VENDOR_EVIDENCE,
            "pwa_browser": PWA_BROWSER_EVIDENCE,
        },
        "overall": overall,
        "pillars": rows,
    }

    if args.write:
        OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(_render_md(payload), encoding="utf-8")
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_MD}")

    print(
        f"overall: repo={overall['repo_pct']}% internal_pilot={overall['internal_pilot_pct']}% "
        f"public_live={overall['public_live_pct']}% pwa={overall['pwa_pct']}% "
        f"external_vendor={overall['external_vendor_pct']}% composite={overall['composite_pct']}%"
    )
    return 0


def _render_md(payload: dict) -> str:
    lines = [
        "# GEOS Scoring Semantics Hardening (Honest 6-Dimension Matrix)",
        "",
        f"Generated: {payload['generated_at']} (batch {payload['batch']})",
        "",
        payload["policy_note"],
        "",
        "## Overall (averaged across pillars)",
        "",
        "| Dimension | Value |",
        "| --- | ---: |",
        f"| repo_pct | {payload['overall']['repo_pct']} |",
        f"| internal_pilot_pct | {payload['overall']['internal_pilot_pct']} |",
        f"| public_live_pct | {payload['overall']['public_live_pct']} |",
        f"| pwa_pct | {payload['overall']['pwa_pct']} |",
        f"| external_vendor_pct | {payload['overall']['external_vendor_pct']} |",
        f"| market_ready_pct | {payload['overall']['market_ready_pct']} |",
        f"| composite_pct | {payload['overall']['composite_pct']} |",
        f"| native_app_status | {payload['overall']['native_app_status']} |",
        "",
        "## Per-pillar",
        "",
        "| Pillar | Repo | Pilot | Public | PWA | External | Market | Composite | Verdict |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in payload["pillars"]:
        lines.append(
            f"| {r['pillar_id']} | {r['repo_pct']} | {r['internal_pilot_pct']} | "
            f"{r['public_live_pct']} | {r['pwa_pct']} | {r['external_vendor_pct']} | "
            f"{r['market_ready_pct']} | {r['composite_pct']} | {r['verdict']} |"
        )
    lines.extend([
        "",
        "## Native app posture",
        "",
        payload["overall"]["native_app_strategy"],
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
