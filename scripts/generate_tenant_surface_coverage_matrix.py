#!/usr/bin/env python3
"""Generate preview_tenant_surface_coverage_matrix.html from route ledger + sweep artifacts (batch 1729)."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES_JSON = ROOT / "docs" / "generated" / "portal_tenant_sweep_routes.json"
P0_LEDGER = ROOT / "docs" / "generated" / "tenant_p0_menu_sweep_surfaces.json"
ABRUPT_ARTIFACT = ROOT / "var" / "tenant-abrupt-end-sweep.json"
OUT = ROOT / "docs" / "generated" / "preview_tenant_surface_coverage_matrix.html"

# Cycle 8 role-home homes + backend dashboard root are always proven.
STATIC_PROVEN_INNER = {
    "/authentication/backend/",
    "/portal/parent/",
    "/portal/teacher/",
    "/portal/student-portal/",
    "/portal/student-portal/grades/",
}

MATRIX_TIMESTAMP_RE = re.compile(
    r"Generated at <code>[^<]+</code>",
    re.IGNORECASE,
)


def _family_key(inner: str) -> str:
    stripped = inner.strip("/")
    if not stripped:
        return "(root)"
    parts = stripped.split("/")
    if len(parts) >= 2 and parts[0] == "authentication" and parts[1] == "backend":
        return "authentication/backend"
    if len(parts) >= 2 and parts[0] == "portal":
        return f"portal/{parts[1]}"
    if len(parts) >= 2 and parts[0] == "school" and parts[1] == "studio":
        return "school/studio"
    return parts[0] + ("/" if len(parts) == 1 else "")


def _load_proven_inner() -> set[str]:
    proven = set(STATIC_PROVEN_INNER)
    if P0_LEDGER.is_file():
        data = json.loads(P0_LEDGER.read_text(encoding="utf-8"))
        for row in data.get("surfaces") or []:
            url = str(row.get("url") or "").strip()
            if url:
                proven.add(url if url.endswith("/") else f"{url}/")
    if not ABRUPT_ARTIFACT.is_file():
        return proven
    data = json.loads(ABRUPT_ARTIFACT.read_text(encoding="utf-8"))
    for row in data.get("results") or []:
        if row.get("skipped"):
            continue
        if row.get("ok") is not True:
            continue
        inner = row.get("inner") or row.get("url") or ""
        if not inner:
            continue
        if not str(inner).startswith("/"):
            inner = f"/{inner}"
        if not str(inner).endswith("/"):
            inner = f"{inner}/"
        proven.add(str(inner))
    return proven


def _build_matrix() -> tuple[dict, list[dict]]:
    routes_data = json.loads(ROUTES_JSON.read_text(encoding="utf-8"))
    routes = routes_data.get("routes") or []
    proven_inner = _load_proven_inner()
    proven_families = {_family_key(p) for p in proven_inner}

    rows: list[dict] = []
    for route in routes:
        inner = route.get("inner") or route.get("path", "")
        if not str(inner).startswith("/"):
            inner = f"/{inner}"
        family = _family_key(str(inner))
        if str(inner) in proven_inner:
            status = "proven"
        elif family in proven_families:
            status = "partial"
        else:
            status = "queued"
        rows.append(
            {
                "path": inner,
                "name": route.get("name") or "",
                "family": family,
                "status": status,
            }
        )

    family_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "proven": 0})
    for row in rows:
        fam = row["family"]
        family_counts[fam]["total"] += 1
        if row["status"] == "proven":
            family_counts[fam]["proven"] += 1

    families: list[dict] = []
    for fam, counts in sorted(family_counts.items()):
        total = counts["total"]
        proven_n = counts["proven"]
        if proven_n == total and total > 0:
            fam_status = "proven"
        elif proven_n > 0 or fam in proven_families:
            fam_status = "partial"
        else:
            fam_status = "queued"
        families.append({"family": fam, "routes": total, "status": fam_status})

    stats = {
        "proven": sum(1 for r in rows if r["status"] == "proven"),
        "partial": sum(1 for r in rows if r["status"] == "partial"),
        "queued": sum(1 for r in rows if r["status"] == "queued"),
        "families": len(families),
        "total": len(rows),
    }
    return stats, rows, families


def _render_html(stats: dict, rows: list[dict], families: list[dict]) -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    fam_opts = "".join(
        f'<option value="{html.escape(f["family"])}">{html.escape(f["family"])}</option>'
        for f in families
    )
    fam_rows = "".join(
        f'<tr data-family="{html.escape(f["family"])}" data-status="{f["status"]}">'
        f'<td>{html.escape(f["family"])}</td><td>{f["routes"]}</td>'
        f'<td><span class="pill {f["status"]}">{f["status"]}</span></td></tr>'
        for f in families
    )
    route_rows = "".join(
        f'<tr data-family="{html.escape(r["family"])}" data-status="{r["status"]}" '
        f'data-q="{html.escape(r["path"])} {html.escape(r["name"])}">'
        f'<td><code>{html.escape(r["path"])}</code></td>'
        f'<td>{html.escape(r["name"])}</td>'
        f'<td>{html.escape(r["family"])}</td>'
        f'<td><span class="pill {r["status"]}">{r["status"]}</span></td></tr>'
        for r in rows
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tenant surface coverage matrix — {stats["total"]} routes</title>
<style>
:root{{--bg:#0b0f1a;--card:#12182b;--hairline:rgba(255,255,255,.08);--text:#f1f5f9;--muted:#94a3b8;--mono:ui-monospace,monospace}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--text)}}
.wrap{{max-width:1200px;margin:0 auto;padding:2rem 1.25rem 3rem}}
h1{{margin:0 0 .5rem;font-size:1.6rem}}a.back{{color:#a5b4fc;text-decoration:none;font-size:.9rem}}
.stats{{display:flex;flex-wrap:wrap;gap:.75rem;margin:1.25rem 0 1.5rem}}
.stat{{background:var(--card);border:1px solid var(--hairline);border-radius:12px;padding:.75rem 1rem;min-width:120px}}
.stat strong{{display:block;font-size:1.4rem}}.stat span{{font-size:.8rem;color:var(--muted)}}
.toolbar{{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1rem}}
.toolbar input,.toolbar select{{background:#1a2238;border:1px solid var(--hairline);color:var(--text);border-radius:8px;padding:.45rem .65rem}}
table{{width:100%;border-collapse:collapse;font-size:.82rem}}
th,td{{padding:.5rem .6rem;border-bottom:1px solid var(--hairline);text-align:left;vertical-align:top}}
th{{color:var(--muted);font-weight:600;position:sticky;top:0;background:#151b2e}}
code{{font-family:var(--mono);font-size:.78rem;color:#c4b5fd}}
.pill{{display:inline-block;padding:.15rem .45rem;border-radius:999px;font-size:.68rem;text-transform:uppercase;font-weight:600}}
.pill.proven{{background:rgba(34,197,94,.15);color:#86efac}}
.pill.partial{{background:rgba(245,158,11,.15);color:#fcd34d}}
.pill.queued{{background:rgba(100,116,139,.2);color:#cbd5e1}}
.scroll{{max-height:62vh;overflow:auto;border:1px solid var(--hairline);border-radius:12px}}
.note{{color:var(--muted);font-size:.9rem;margin-bottom:1rem;max-width:70ch}}
</style></head><body><div class="wrap">
<p><a class="back" href="preview_tenant_elevation_hub.html">← Elevation hub</a></p>
<h1>Surface &amp; menu coverage matrix</h1>
<p class="note">Generated from <code>portal_tenant_sweep_routes.json</code> ({stats["total"]} routes).
Generated at <code>{html.escape(ts)}</code>.
<strong>Proven</strong> = individually swept or Cycle 8 P0 home.
<strong>Partial</strong> = same family as a proven route.
<strong>Queued</strong> = not yet layout-proven.</p>
<div class="stats">
<div class="stat"><strong>{stats["proven"]}</strong><span>Proven</span></div>
<div class="stat"><strong>{stats["partial"]}</strong><span>Partial (family)</span></div>
<div class="stat"><strong>{stats["queued"]}</strong><span>Queued</span></div>
<div class="stat"><strong>{stats["families"]}</strong><span>Route families</span></div>
</div>
<h2>Families</h2>
<div class="scroll" style="max-height:28vh;margin-bottom:1.5rem"><table><thead><tr><th>Family</th><th>Routes</th><th>Status</th></tr></thead><tbody>{fam_rows}</tbody></table></div>
<h2>All routes</h2>
<div class="toolbar">
<input id="q" placeholder="Filter path or name…" style="min-width:220px">
<select id="status"><option value="">All statuses</option><option>proven</option><option>partial</option><option>queued</option></select>
<select id="family"><option value="">All families</option>{fam_opts}</select>
</div>
<div class="scroll"><table><thead><tr><th>Path</th><th>URL name</th><th>Family</th><th>Status</th></tr></thead><tbody id="rows">{route_rows}</tbody></table></div>
<script nonce="">
document.getElementById('q').addEventListener('input', filterRows);
document.getElementById('status').addEventListener('change', filterRows);
document.getElementById('family').addEventListener('change', filterRows);
function filterRows(){{
  const q=(document.getElementById('q').value||'').toLowerCase();
  const st=document.getElementById('status').value;
  const fam=document.getElementById('family').value;
  document.querySelectorAll('#rows tr').forEach(tr=>{{
    const okQ=!q||(tr.dataset.q||'').toLowerCase().includes(q);
    const okS=!st||tr.dataset.status===st;
    const okF=!fam||tr.dataset.family===fam;
    tr.style.display=(okQ&&okS&&okF)?'':'none';
  }});
}}
</script>
</div></body></html>
"""


def _normalize_for_check(text: str) -> str:
    return MATRIX_TIMESTAMP_RE.sub("Generated at <code>TIMESTAMP</code>", text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if not ROUTES_JSON.is_file():
        print(f"missing {ROUTES_JSON}", file=sys.stderr)
        return 1

    stats, rows, families = _build_matrix()
    rendered = _render_html(stats, rows, families)

    if args.write or (not args.check and not OUT.is_file()):
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(rendered, encoding="utf-8")
        print(
            f"generate_tenant_surface_coverage_matrix: wrote {OUT} "
            f"({stats['proven']} proven / {stats['partial']} partial / {stats['queued']} queued)"
        )
        return 0

    if args.check:
        if not OUT.is_file():
            print("generate_tenant_surface_coverage_matrix: missing HTML — run --write", file=sys.stderr)
            return 1
        existing = _normalize_for_check(OUT.read_text(encoding="utf-8"))
        expected = _normalize_for_check(rendered)
        if existing != expected:
            print("generate_tenant_surface_coverage_matrix: DRIFT — run --write", file=sys.stderr)
            return 1
        print("generate_tenant_surface_coverage_matrix: OK (no drift)")
        return 0

    print(rendered[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
