#!/usr/bin/env python3
"""DISCOVERY audit: which in-app pages waste the horizontal canvas ("unused right gutter").

Root cause (durable): the authenticated shells render a FULL-WIDTH canvas
(`control_plane_base` -> `container-fluid ... cp-main-col`; `portal_base` ->
`portal-main-col ... portal-page-body`). Nothing caps or centers the content,
so a page whose body is a single narrow column (a `.cp-list`, a stack of
panels, or a short form) with no width strategy clusters on the LEFT and leaves
a large empty gutter on the right. That is exactly what the owner reported on
`/super/marketplace/blueprints/`.

The platform already ships every primitive needed to fix this WITHOUT new CSS:
  * FILL   -> `.cp-grid` + `.cp-grid-2/3/4` (responsive auto-fit card grid) on
              `.cp-card` / `.cp-panel`; or `container-fluid` + `row g-* col-*`.
  * CENTER -> `.content-max-520/640/960/1200/narrow` (margin-inline:auto) for
              reading / single-form pages that SHOULD stay narrow.
  * RAIL   -> `data-rmc-balanced-layout="...-rail"` (operator-detail-rail /
              operator-form-rail / tenant-dashboard-rail) defined in
              `static/css/rmc-platform-inner-pages.css` for two-pane
              primary+context workflow pages.

The sibling `audit_platform_layout_balance.py` only ENFORCES the rail contract
on ~6 hand-picked templates; it does not DISCOVER which other pages still waste
the gutter. This script closes that gap: it classifies every page-level
template into a recommended fix bucket, with the evidence behind each verdict,
so the remediation is driven by what each page actually needs rather than by
pattern-grepping (which historically over-counted ~10x).

Outputs:
  docs/generated/width_utilization_audit.json   (machine-readable)
  docs/generated/width_utilization_audit.html   (browser report)
  stdout summary table

Run:  python scripts/audit_width_utilization.py [--write] [--limit N]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
OUT_JSON = ROOT / "docs" / "generated" / "width_utilization_audit.json"
OUT_HTML = ROOT / "docs" / "generated" / "width_utilization_audit.html"

# --- Shell families ---------------------------------------------------------
# Bases whose canvas is a full-width authenticated workspace (in scope: a page
# that does not fill or center wastes the gutter).
IN_APP_BASES = {
    "control_plane_base.html",
    "backend_base.html",
    "backend_base_manager.html",
    "backend_base_tenant.html",
    "portal_base.html",
    "control_plane_skeleton.html",
    "studio_os/shell.html",
    "super/wedges/_surface_base.html",
    "siteconfig/zero_ticket_shell.html",
}
# Bases that are centered / editorial / chrome-less BY DESIGN (out of scope:
# narrow centered content is intentional, not a defect).
OUT_OF_SCOPE_BASES = {
    "base.html",  # auth / registration / standalone — centered auth-shell by design
    "marketing/base_marketing.html",
    "schools/marketing_base.html",
    "schools/marketing_page_layout.html",
    "admin/base.html",
    "admin/base_site.html",
    "admin/change_form.html",
    "admin/change_list.html",
    "admin/index_superadmin.html",
    "admin/app_index.html",
    "emails/base_branded.html",
    "migration_cloud/connector/_wizard_base.html",
    "studio_os/studio_embed_minimal.html",
    "schools/tenant_minimal_shell.html",
    "schools/404_tenant.html",
}
# Path prefixes that are out of scope regardless of base (editorial / centered /
# deliberately narrow surfaces — established exclusions).
OUT_OF_SCOPE_PREFIXES = (
    "templates/marketing/",
    "templates/schools/marketing",
    "templates/emails/",
    "templates/errors/",
    "templates/admin/",
    "templates/unfold/",
    "templates/registration/",  # auth checkpoints — centered auth-shell
    "templates/auth/",
    "templates/setup_studio/",  # onboarding wizards — centered by design
    "templates/components/",  # partials, not pages
    "templates/partials/",
    "templates/widgets/",
    "templates/archetypes/",
)
# Within-page markers of deliberately narrow surfaces (chat threads, wizards).
NARROW_BY_DESIGN = re.compile(
    r"direct_thread|chat-thread|wizard-shell|onboarding-shell|auth-shell|auth-card",
    re.I,
)
# Intentional minimal micro-states (guard / error / empty / completed): a short
# centered message by design, NOT a width defect — exclude by filename stem.
MICRO_STATE = re.compile(
    r"(forbidden|no_tenant|no_academic_year|_empty|_disabled|_expired|maintenance"
    r"|_lock|_completed|_done|_complete|^40\d|^50\d|403|404|410|500|503)",
    re.I,
)

EXTENDS = re.compile(r"""{%\s*extends\s+['"]([^'"]+)['"]""")
INCLUDE = re.compile(r"""{%\s*include\s+['"]([^'"]+)['"]""")
COMMENT = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", re.S)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def strip_noise(text: str) -> str:
    text = COMMENT.sub(" ", text)
    text = HTML_COMMENT.sub(" ", text)
    return text


def resolve_base_chain(rel: str, seen: set[str] | None = None) -> list[str]:
    """Return the extends chain (direct base first) for a template, max depth 4."""
    seen = seen or set()
    if rel in seen or len(seen) > 4:
        return []
    seen.add(rel)
    path = TEMPLATES / rel
    if not path.exists():
        return []
    m = EXTENDS.search(path.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return []
    base = m.group(1)
    return [base, *resolve_base_chain(base, seen)]


def shell_family(rel: str, chain: list[str]) -> str:
    """Classify the page's shell: in-app | out-of-scope | unknown."""
    for prefix in OUT_OF_SCOPE_PREFIXES:
        if rel.startswith(prefix):
            return "out-of-scope"
    for base in chain:
        if base in IN_APP_BASES:
            return "in-app"
        if base in OUT_OF_SCOPE_BASES:
            return "out-of-scope"
    return "unknown"


def gather_signal_text(rel: str) -> str:
    """Page body text + one level of resolved {% include %} partials (deduped)."""
    path = TEMPLATES / rel
    text = strip_noise(path.read_text(encoding="utf-8", errors="replace"))
    parts = [text]
    for inc in set(INCLUDE.findall(text)):
        # ignore dynamic includes and components/partials chrome we don't own
        if "{" in inc or inc.endswith(("_open.html", "_close.html")):
            continue
        ip = TEMPLATES / inc
        if ip.exists():
            parts.append(strip_noise(ip.read_text(encoding="utf-8", errors="replace")))
    return "\n".join(parts)


# --- Signals ----------------------------------------------------------------
def signals(text: str) -> dict:
    has_grid = bool(
        re.search(r"\bcp-grid\b", text)
        or re.search(r'class="[^"]*\brow\b[^"]*"[\s\S]{0,1200}\bcol-(sm|md|lg|xl)-', text)
        or re.search(r"\bd-flex\b[^\"]*\bflex-wrap\b", text)
        # custom/component grid classes (e.g. rmc-*-grid, *__grid, *-hub-grid) and inline grids
        or re.search(r'class="[^"]*[\w-]*grid[\w-]*[^"]*"', text)
        or re.search(r"display\s*:\s*grid", text)
    )
    return {
        "container_fluid": bool(re.search(r"\bcontainer-fluid\b", text)),
        "container_fixed": bool(re.search(r'class="[^"]*\bcontainer\b(?!-fluid)', text)),
        "content_max": bool(re.search(r"\bcontent-max-[a-z0-9]+\b", text)),
        "balanced_rail": bool(re.search(r"data-rmc-balanced-layout", text)),
        "grid": has_grid,
        "table": bool(re.search(r"<table\b", text)),
        "mx_auto": bool(re.search(r"\bmx-auto\b|margin-inline\s*:\s*auto", text)),
        "cp_list": bool(re.search(r"\bcp-list\b", text)),
        "n_form": len(re.findall(r"<form\b", text)),
        "n_panel": len(re.findall(r"\bcp-(panel|card)\b", text)),
        "n_table": len(re.findall(r"<table\b", text)),
        "narrow_by_design": bool(NARROW_BY_DESIGN.search(text)),
    }


def classify(sig: dict) -> tuple[str, str, str]:
    """Return (bucket, confidence, reason)."""
    if sig["narrow_by_design"]:
        return ("LEAVE", "high", "deliberately narrow surface (chat/wizard/auth shell)")

    fills = sig["grid"] or (sig["table"] and sig["n_table"] >= 1)
    centers = sig["content_max"] or sig["balanced_rail"] or sig["mx_auto"]

    if sig["balanced_rail"]:
        return ("LEAVE", "high", "already uses a balanced-layout rail")
    if fills and centers:
        return ("LEAVE", "high", "already fills (grid/table) and has a width strategy")
    if fills:
        return ("LEAVE", "high", "already fills the canvas with a responsive grid/table")
    if centers:
        return ("LEAVE", "high", "already centered (content-max / mx-auto)")

    # No fill, no center -> candidate. Pick the fix from the content shape.
    if sig["cp_list"]:
        return ("FILL", "high", "single-column .cp-list in a full-width canvas -> convert to .cp-grid cards")
    if sig["n_panel"] >= 3:
        return ("FILL", "medium", f"{sig['n_panel']} stacked panels/cards, no grid -> wrap in .cp-grid")
    if sig["n_form"] >= 1 and sig["n_panel"] <= 2:
        return ("CENTER", "medium", "form/reading content, left-aligned, uncentered -> wrap in .content-max-*")
    if sig["n_panel"] in (1, 2):
        return ("CENTER", "low", "1-2 panels, no width strategy -> likely center with .content-max-*")
    return ("REVIEW", "low", "no clear width strategy; needs a human look")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write JSON + HTML artifacts")
    ap.add_argument("--limit", type=int, default=0, help="print only first N candidates")
    ap.add_argument("--bucket", default="", help="filter stdout to one bucket")
    args = ap.parse_args()

    # Templates that are themselves extended by another are bases/layouts, not
    # leaf pages — exclude them (a base never has a width defect of its own).
    all_html = list(TEMPLATES.rglob("*.html"))
    extended_targets: set[str] = set()
    for p in all_html:
        for m in EXTENDS.finditer(p.read_text(encoding="utf-8", errors="replace")):
            extended_targets.add(m.group(1))

    rows: list[dict] = []
    for path in sorted(all_html):
        rel = path.relative_to(TEMPLATES).as_posix()
        repo_rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if not EXTENDS.search(text):
            continue  # not a page (partial/component/fragment)
        if rel in extended_targets:
            continue  # this template is a base/layout (extended by others)
        chain = resolve_base_chain(rel)
        family = shell_family(rel, chain)
        if family != "in-app":
            continue  # only in-app full-width canvases are in scope
        sig = signals(gather_signal_text(rel))
        if MICRO_STATE.search(path.stem):
            bucket, conf, reason = ("LEAVE", "high", "intentional minimal micro-state (guard/error/empty/done)")
        else:
            bucket, conf, reason = classify(sig)
        rows.append(
            {
                "file": repo_rel,
                "base": chain[0] if chain else "",
                "bucket": bucket,
                "confidence": conf,
                "reason": reason,
                "signals": sig,
            }
        )

    counts = Counter(r["bucket"] for r in rows)
    by_conf = Counter((r["bucket"], r["confidence"]) for r in rows)
    candidates = [r for r in rows if r["bucket"] in ("FILL", "CENTER", "REVIEW")]
    candidates.sort(key=lambda r: ({"high": 0, "medium": 1, "low": 2}[r["confidence"]], r["bucket"], r["file"]))

    # ---- stdout summary ----
    print(f"In-app page templates scanned: {len(rows)}")
    print("Buckets:", dict(counts))
    print("FILL by confidence:", {c: n for (b, c), n in by_conf.items() if b == "FILL"})
    print("CENTER by confidence:", {c: n for (b, c), n in by_conf.items() if b == "CENTER"})
    print(f"\nActionable candidates (FILL/CENTER/REVIEW): {len(candidates)}\n")
    shown = candidates
    if args.bucket:
        shown = [r for r in shown if r["bucket"] == args.bucket.upper()]
    if args.limit:
        shown = shown[: args.limit]
    for r in shown:
        print(f"  [{r['bucket']:6} {r['confidence']:6}] {r['file']}")
        print(f"          -> {r['reason']}")

    if args.write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "scanned": len(rows),
            "buckets": dict(counts),
            "by_confidence": {f"{b}:{c}": n for (b, c), n in by_conf.items()},
            "rows": rows,
        }
        OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        OUT_HTML.write_text(render_html(rows, counts, by_conf), encoding="utf-8")
        print(f"\nWrote {OUT_JSON.relative_to(ROOT).as_posix()}")
        print(f"Wrote {OUT_HTML.relative_to(ROOT).as_posix()}")

    return 0


def render_html(rows, counts, by_conf) -> str:
    def esc(s):
        return html.escape(str(s))

    badge = {
        "FILL": "#b45309",
        "CENTER": "#1d4ed8",
        "RAIL": "#7c3aed",
        "LEAVE": "#15803d",
        "REVIEW": "#be123c",
    }
    order = {"high": 0, "medium": 1, "low": 2}
    actionable = sorted(
        [r for r in rows if r["bucket"] in ("FILL", "CENTER", "REVIEW")],
        key=lambda r: (order[r["confidence"]], r["bucket"], r["file"]),
    )
    leave = [r for r in rows if r["bucket"] == "LEAVE"]

    def row_html(r):
        s = r["signals"]
        sig_chips = " ".join(
            f"<span class='chip'>{k}</span>"
            for k, v in s.items()
            if v and k not in ("n_form", "n_panel", "n_table", "narrow_by_design")
        )
        return (
            f"<tr><td><code>{esc(r['file'])}</code></td>"
            f"<td><span class='b' style='background:{badge[r['bucket']]}'>{r['bucket']}</span></td>"
            f"<td>{esc(r['confidence'])}</td>"
            f"<td>{esc(r['reason'])}</td>"
            f"<td class='chips'>{sig_chips}</td></tr>"
        )

    cards = "".join(
        f"<div class='kpi'><div class='n' style='color:{badge.get(k,'#334155')}'>{v}</div><div class='l'>{esc(k)}</div></div>"
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1])
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Width-utilization audit — unused gutter discovery</title>
<style>
 body{{font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#f8fafc;color:#0f172a}}
 .wrap{{max-width:1200px;margin:0 auto;padding:28px 20px 64px}}
 h1{{font-size:24px;margin:0 0 6px}} .sub{{color:#475569;margin:0 0 20px}}
 .kpis{{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}}
 .kpi{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 18px;min-width:120px}}
 .kpi .n{{font-size:28px;font-weight:700}} .kpi .l{{color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
 table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;margin:10px 0 32px}}
 th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid #f1f5f9;vertical-align:top;font-size:13px}}
 th{{background:#f1f5f9;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#475569}}
 code{{font:12px ui-monospace,Consolas,monospace}}
 .b{{color:#fff;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700}}
 .chips{{max-width:260px}} .chip{{display:inline-block;background:#eef2ff;color:#3730a3;border-radius:5px;padding:1px 6px;font-size:11px;margin:1px}}
 h2{{margin:30px 0 6px;font-size:18px}} .legend{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 18px}}
 .legend li{{margin:4px 0}}
</style></head><body><div class="wrap">
<h1>Width-utilization audit — "unused right gutter" discovery</h1>
<p class="sub">Classifies every in-app page (full-width canvas) by whether it fills, centers, or wastes the horizontal space — and what fix it needs. Reproducible via <code>python scripts/audit_width_utilization.py --write</code>.</p>
<div class="kpis">{cards}</div>
<div class="legend"><strong>Fix buckets — apply the page-aware primitive that matches the page's content</strong><ul>
<li><b style="background:{badge['FILL']}" class="b">FILL</b> single-column content in a wide canvas → for a <em>tall form</em> use <code>.cp-form-grid</code> (flows fields into 2–4 columns, shortens AND fills); for a <em>browse-able list</em> use <code>.cp-grid .cp-grid-2/3</code> on <code>.cp-card</code> (or <code>row g-3 col-*</code>).</li>
<li><b style="background:{badge['CENTER']}" class="b">CENTER</b> genuinely narrow single form / settings toggle that is unreadable full-width → <code>.content-measure</code> (page-aware readable measure via <code>--rmc-measure</code>; symmetric margins). Older equivalent already on main: <code>.content-max-640/520</code>.</li>
<li><b style="background:{badge['RAIL']}" class="b">RAIL</b> primary work + secondary context/aside → two-pane via <code>.rmc-page-horizon</code> (relocates stacked content into the right gutter; auto-stacks on narrow screens) or <code>data-rmc-balanced-layout="*-rail"</code>.</li>
<li><b style="background:{badge['LEAVE']}" class="b">LEAVE</b> already fills/centers/rails, or narrow by design — no change.</li>
<li><b style="background:{badge['REVIEW']}" class="b">REVIEW</b> ambiguous — needs a human read before acting.</li>
</ul><p style="margin:8px 0 0;color:#64748b"><strong>Note:</strong> the page-aware primitives <code>.content-measure</code> / <code>.cp-form-grid</code> / <code>.rmc-page-horizon</code> were authored in <code>static/css/rmc-class-grammar.css</code> as the canonical cure for this exact problem and are the preferred fix. Zero new CSS — every fix reuses an existing utility. Read each candidate before editing — static signals locate, they don't prove.</p></div>
<h2>Actionable candidates ({len(actionable)})</h2>
<table><thead><tr><th>Template</th><th>Fix</th><th>Conf.</th><th>Why</th><th>Signals</th></tr></thead>
<tbody>{''.join(row_html(r) for r in actionable)}</tbody></table>
<h2>Already handled — LEAVE ({len(leave)})</h2>
<table><thead><tr><th>Template</th><th>Fix</th><th>Conf.</th><th>Why</th><th>Signals</th></tr></thead>
<tbody>{''.join(row_html(r) for r in leave)}</tbody></table>
</div></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
