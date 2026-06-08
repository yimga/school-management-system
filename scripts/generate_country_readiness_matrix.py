#!/usr/bin/env python
"""
Generate docs/COUNTRY_READINESS_MATRIX.md from the Country Readiness Register.

The doc, the operator dashboard (/super/.../country-readiness/), and the register
all render from the SAME SOT (apps.finance.country_readiness_register), so they
cannot drift. Re-run after any PSP adapter status change:

    python scripts/generate_country_readiness_matrix.py

Pure projection — no DB, read-only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.finance.country_readiness_register import all_assessments, summary  # noqa: E402

OUT = ROOT / "docs" / "COUNTRY_READINESS_MATRIX.md"

TONE_ICON = {"success": "🟢", "warning": "🟡", "info": "🟠", "danger": "🔴", "secondary": "⚪"}


def main() -> int:
    s = summary()
    rows = all_assessments()
    lines: list[str] = []
    a = lines.append

    a("# Country Readiness Matrix")
    a("")
    a("> **Generated** from `apps/finance/country_readiness_register.py` "
      "(`python scripts/generate_country_readiness_matrix.py`). Do not hand-edit — "
      "it is a projection over the payment-profile, PSP-adapter, and "
      "local-experience SOT registers. The operator dashboard at "
      "`/super/.../country-readiness/` renders the same data.")
    a("")
    a("## The headline")
    a("")
    a(f"- **{s['total_countries']} ISO countries**, but only **{s['defined_corridors']} have a "
      f"researched payment corridor** (real currency + dominant rails). The other "
      f"**{s['placeholder_corridors']} are placeholder stubs** — defining a corridor is *data* work, "
      "distinct from the *adapter* work below.")
    a(f"- **{s['live_rail_count']} payment rails are LIVE.** A rail is only **config-only** (tenant just "
      "adds an API key) once its adapter is `live`. Until then a defined corridor is **config-blocked** "
      "(the platform must finish/certify the rail) — manual/offline receipts still work everywhere.")
    a("- Leverage / localization / risk figures below are computed over the **defined corridors only** — "
      "counting stubs would inflate every number (the \"one card PSP covers 240 countries\" artifact is "
      "really 200 stubs sharing a fake USD currency).")
    a("")
    a("### Readiness distribution")
    a("")
    a("| Tier | Countries | Meaning |")
    a("|---|---:|---|")
    for t in s["tier_order"]:
        icon = TONE_ICON.get(s["tier_tone"][t], "")
        a(f"| {icon} `{t}` | {s['by_tier'].get(t, 0)} | {s['tier_labels'][t]} |")
    a("")
    a("### Highest-leverage adapters")
    a("")
    a("Among the **defined** corridors, countries unblocked if this single adapter is promoted to "
      "`live`. This is the adapter build order. Note the two distinct workstreams: **(1) define the "
      "remaining corridors** (data — research currency + rails per market) and **(2) promote these "
      "adapters to live** (engineering). A country needs both before it becomes pure tenant config:")
    a("")
    a("| Adapter | Countries unblocked |")
    a("|---|---:|")
    for label, count in s["by_blocking_psp"].items():
        a(f"| {label} | {count} |")
    a("")
    a("### Localization")
    a("")
    a(f"- 🟢 Localized: **{s['by_locale'].get('localized', 0)}** · "
      f"🟡 Partial: **{s['by_locale'].get('partial', 0)}** · "
      f"⚪ English-fallback: **{s['by_locale'].get('english_fallback', 0)}** "
      "_(of the defined corridors)_")
    a("")
    a("### Risk tier (defined corridors)")
    a("")
    risk = s.get("by_risk_tier", {})
    a(" · ".join(f"**{k}**: {v}" for k, v in risk.items()) or "_n/a_")
    a("")
    a("## Per-country matrix")
    a("")
    a("> Rows tagged **stub** carry placeholder currency/rails (corridor not yet researched). "
      "Currencies marked **0d** are zero-decimal (charge whole units, not cents).")
    a("")
    a("| Country | Cur | Rails | Readiness | Risk | Tenant action | Platform action | Locale |")
    a("|---|---|---|---|---|---|---|---|")
    for cc in sorted(rows.keys()):
        r = rows[cc]
        icon = TONE_ICON.get(r["overall_tone"], "")
        rails = " ".join(r["primary_rails"][:3])
        label = r["label"] + (" **stub**" if r["data_state"] == "placeholder" else "")
        cur = r["currency"] + (" **0d**" if r.get("zero_decimal") else "")
        risk = r.get("risk_tier") or "—"
        a(f"| {label} (`{cc}`) | {cur} | {rails} | {icon} {r['overall_tier']} | {risk} "
          f"| {r['tenant_action']} | {r['platform_action']} | {r['locale_state']} |")
    a("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(rows)} countries).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
