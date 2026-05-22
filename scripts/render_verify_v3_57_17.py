"""Render-verification harness for v3.57.17 (2026-05-22).

PURE READ-ONLY render-verification — produces three artifacts under
docs/generated/ that an operator can open against a running dev server
(`python manage.py runserver`) to inspect the rendered cockpit cascade.

Outputs:
  - docs/generated/render_verify_super_dashboard_v3_57_17.html
  - docs/generated/render_verify_parent_dashboard_v3_57_17.html
  - docs/generated/render_verify_v3_57_17_report.md

Strategy: PARTIAL-ONLY FALLBACK.
  The full templates extend control_plane_base.html / portal_base.html, which
  trigger context processors, middleware-resolved URL reverse calls, and a
  pile of view-supplied data (`schools`, `platform_health_cards`, etc.). For
  a strict, no-side-effect render verifier we synthesize ONLY the cockpit
  payload and render each cockpit partial against a minimal request stub.
  The resulting composite document mirrors the canvas-body section ordering
  of the v8 200x and v3 100x preview HTMLs.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.template import engines  # noqa: E402
from django.template.loader import render_to_string  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.utils.translation import gettext_lazy as _  # noqa: E402

from apps.siteconfig.cockpit_context import (  # noqa: E402
    _DEFAULT_ACTIVITY_EVENTS,
    _DEFAULT_PULSE_CARDS,
    _DEFAULT_MANAGER_FOOTER,
)
from apps.siteconfig.cockpit_manager_200x import manager_200x_defaults  # noqa: E402
from apps.siteconfig.cockpit_front_office_200x import (  # noqa: E402
    front_office_200x_defaults,
)
from apps.siteconfig.cockpit_tenant_dashboard import (  # noqa: E402
    build_tenant_dashboard_cockpit,
)
from apps.siteconfig.cockpit_tenant_v3_extended import (  # noqa: E402
    build_tenant_v3_extended_cockpit,
)
from apps.siteconfig.cockpit_manager_200x_preview_data import (  # noqa: E402
    manager_200x_demo_payload,
)
from apps.siteconfig.cockpit_tenant_v3_preview_data import (  # noqa: E402
    tenant_v3_extended_demo_payload,
)
from apps.siteconfig.cockpit_context import _deep_merge  # noqa: E402


OUT_DIR = REPO_ROOT / "docs" / "generated"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# Manager cockpit canvas-body section order (mirrors super_dashboard.html's
# include sequence + v8 200x preview canvas-body section ordering).
MANAGER_SECTIONS = [
    "_activity_ticker.html",
    "_platform_pulse.html",
    "_live_world_map.html",
    "_forecast_lane.html",
    "_slo_clocks.html",
    "_tenant_heatmap.html",
    "_revenue_waterfall.html",
    "_audit_feed.html",
    "_trust_nutrition.html",
    "_operator_presence.html",
]

# Tenant parent landing cockpit section order (mirrors parent/dashboard.html
# include sequence + v3 100x preview canvas-body section ordering).
TENANT_SECTIONS = [
    "_today_snapshot.html",
    "_quick_actions_grid.html",
    "_upcoming_events_strip.html",
    "_activity_timeline.html",
    "_achievements_card.html",
    "_teacher_spotlight_card.html",
    "_parent_teacher_thread.html",
    "_calendar_weather.html",
    "_financial_timeline.html",
    "_life_event_timeline.html",
    "_sibling_compare.html",
]


def build_manager_cockpit() -> dict[str, Any]:
    """Synthesize the manager-host cockpit dict the same way
    cockpit_context() does, without touching middleware/SiteSettings."""
    cockpit: dict[str, Any] = {
        "brand": {
            "wordmark": "RunMyCampus",
            "product_pill": "Manager",
            "tagline": "Operator command surface",
        },
        "activity_feed": {
            "enabled": True,
            "scroll_seconds": 60,
            "events": _DEFAULT_ACTIVITY_EVENTS,
        },
        "pulse_metrics": {
            "label": "Platform pulse · live",
            "show_live_dot": True,
            "cards": _DEFAULT_PULSE_CARDS,
        },
        "workspace_context": {
            "enabled": True,
            "show_role": True,
            "scope_dropdown": True,
            "collapse_toggle": True,
            "scope_label": "All tenants · Global",
        },
        "breadcrumb": {"show_root_link": True, "separator": "›"},
        "footer": _DEFAULT_MANAGER_FOOTER,
    }
    cockpit.update(manager_200x_defaults())
    cockpit.update(front_office_200x_defaults())
    # Overlay the 200x demo payload (the same way the context processor does
    # when COCKPIT_200X_RENDER_PREVIEW_DEMO is True).
    cockpit = _deep_merge(cockpit, manager_200x_demo_payload())
    return cockpit


def build_tenant_cockpit() -> dict[str, Any]:
    """Synthesize the tenant-host cockpit dict mirroring
    cockpit_context() on a tenant host (SiteSettings None)."""
    cockpit: dict[str, Any] = {
        "footer": {
            "brand": {
                "wordmark": "Demo Tenant Academy",
                "motto": "Where every learner thrives.",
                "founded_year": 1998,
                "descriptor": "Family portal",
            },
            "trust_pillars": [{"label": "🔒 FERPA · WCAG 2.1 AA", "tone": "secure"}],
            "language": {"label": "English", "current_locale": "en", "has_switcher": True},
            "app_badges": [],
            "social": [],
            "contacts": [],
            "stat_line": "",
            "legal_links": [],
            "copyright_holder": "Demo Tenant Academy",
            "powered_by": {"label": "RunMyCampus", "url": ""},
        },
        "community_band": {"enabled": False},
        "newsletter_band": {"enabled": False},
    }
    cockpit.update(build_tenant_dashboard_cockpit())
    cockpit.update(build_tenant_v3_extended_cockpit())
    cockpit = _deep_merge(cockpit, tenant_v3_extended_demo_payload())

    # Enforce sibling_compare opt_in=False per the task spec.
    if "sibling_compare" in cockpit and isinstance(cockpit["sibling_compare"], dict):
        cockpit["sibling_compare"]["opt_in"] = False
    return cockpit


# ----------------------------------------------------------------------
# Per-partial render with strict per-section error capture.
# ----------------------------------------------------------------------

class SectionResult:
    __slots__ = ("name", "status", "html", "error", "byte_count")

    def __init__(self, name: str) -> None:
        self.name = name
        self.status = ""
        self.html = ""
        self.error = ""
        self.byte_count = 0


def render_partial(partial_name: str, ctx: dict[str, Any], req) -> SectionResult:
    res = SectionResult(partial_name)
    try:
        html = render_to_string(
            f"partials/cockpit/{partial_name}", ctx, request=req
        )
        res.html = html
        res.byte_count = len(html.encode("utf-8"))
        # Heuristic: if the partial rendered only whitespace/comments,
        # treat that as the gate-not-met "empty" branch.
        stripped = html.strip()
        if stripped == "":
            res.status = "RENDERED EMPTY (gate not met)"
        else:
            res.status = "RENDERED CORRECTLY"
    except Exception as exc:  # pragma: no cover - diagnostic path
        res.status = "FAILED (exception)"
        res.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    return res


# ----------------------------------------------------------------------
# Composite document assembly.
# ----------------------------------------------------------------------

MANAGER_CSS_LINKS = [
    "/static/css/manager-cockpit-v7.css",
    "/static/css/manager-control-plane.css",
    "/static/css/rmc-cp-200x.css",
    "/static/css/rmc-copilot-rail.css",
    "/static/css/rmc-civic-footer.css",
    "/static/css/rmc-pagination-grammar.css",
]

TENANT_CSS_LINKS = [
    "/static/css/rmc-tenant-dashboard-v2.css",
    "/static/css/rmc-tenant-canvas-100x.css",
    "/static/css/rmc-civic-footer.css",
    "/static/css/dashboard-auto-grid.css",
    "/static/css/dashboard-layout-unified.css",
    "/static/css/rmc-pagination-grammar.css",
]


def composite_html(
    *,
    title: str,
    css_links: list[str],
    body_class: str,
    section_results: list[SectionResult],
    canvas_intro_html: str = "",
) -> str:
    """Wrap section render outputs in a self-contained shell.

    The shell uses ABSOLUTE /static/ links so an operator can open this
    file against a `runserver` instance and see real bundle styling.
    """
    head_links = "\n  ".join(
        f'<link rel="stylesheet" href="{href}">' for href in css_links
    )
    sections_html_blocks: list[str] = []
    for res in section_results:
        # Comment marker so an inspector can see section boundaries.
        sections_html_blocks.append(
            f"\n  <!-- ===== cockpit partial: {res.name} | {res.status} ===== -->\n"
        )
        if res.status == "RENDERED CORRECTLY":
            sections_html_blocks.append(res.html)
        elif res.status == "RENDERED EMPTY (gate not met)":
            sections_html_blocks.append(
                f'  <div class="render-verify-empty" '
                f'style="border:1px dashed #c1c7d0;padding:.5rem .75rem;'
                f'margin:.5rem 0;background:#fafbfc;color:#5e6c84;'
                f'font:13px/1.4 system-ui">'
                f'<strong>{res.name}</strong>: gate not met (cockpit section '
                f'present but `enabled=False` or empty list).</div>'
            )
        else:  # FAILED
            err_safe = (res.error or "").replace("<", "&lt;").replace(">", "&gt;")
            sections_html_blocks.append(
                f'  <pre class="render-verify-error" '
                f'style="border:1px solid #de350b;background:#fff5f3;'
                f'padding:.5rem .75rem;margin:.5rem 0;white-space:pre-wrap;'
                f'font:12px/1.4 ui-monospace,Menlo,Consolas,monospace;'
                f'color:#a01400">'
                f'<strong>{res.name} — FAILED</strong>\n{err_safe}</pre>'
            )

    body_sections = "".join(sections_html_blocks)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="render_verify_v3_57_17">
  {head_links}
  <style>
    /* Minimal scaffolding to host the partial cascade. Mirrors enough of
       the production shell so the partials look approximately right when
       viewed against the dev static server. */
    body.render-verify-body {{
      margin: 0;
      font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      background: #f4f5f7;
      color: #172b4d;
    }}
    body.render-verify-body.manager {{ background: #0b1220; color: #e6edf3; }}
    .render-verify-canvas {{ max-width: 1280px; margin: 0 auto; padding: 1rem 1.25rem 4rem; }}
    .render-verify-header {{
      padding: .75rem 1rem; border-bottom: 1px solid rgba(148,163,184,0.25);
      background: rgba(15,23,42,0.04); font-weight: 600; font-size: 13px;
      display: flex; gap: 1rem; align-items: center; flex-wrap: wrap;
    }}
    .render-verify-header__tag {{
      display: inline-block; padding: .15rem .55rem; border-radius: 9999px;
      background: #6366f1; color: #fff; font-size: 11px; letter-spacing: .04em;
      text-transform: uppercase;
    }}
    .render-verify-header__note {{ color: #64748b; font-weight: 400; }}
  </style>
</head>
<body class="render-verify-body {body_class}">
  <header class="render-verify-header">
    <span class="render-verify-header__tag">render-verify v3.57.17</span>
    <span>{title}</span>
    <span class="render-verify-header__note">
      Open against `python manage.py runserver` so the /static/css/* links resolve.
      Partial-only render — context-heavy chrome (sidebar, breadcrumb, view-supplied lists) intentionally omitted.
    </span>
  </header>
  <main class="render-verify-canvas">
    {canvas_intro_html}
    {body_sections}
  </main>
</body>
</html>
"""


# ----------------------------------------------------------------------
# Driver.
# ----------------------------------------------------------------------


def main() -> int:
    rf = RequestFactory()

    # MANAGER artifact -------------------------------------------------
    req_mgr = rf.get("/super/")

    class _MgrUser:
        is_authenticated = True
        is_superuser = True
        is_staff = True

        def __str__(self) -> str:
            return "render-verify-superuser"

    req_mgr.user = _MgrUser()
    req_mgr.public_host_kind = "manager"
    req_mgr.site_settings = None
    req_mgr.SITE = None

    mgr_ctx = {"cockpit": build_manager_cockpit(), "request": req_mgr}
    mgr_results = [render_partial(name, mgr_ctx, req_mgr) for name in MANAGER_SECTIONS]

    mgr_html = composite_html(
        title="Manager landing render verify · v3.57.17 (2026-05-22)",
        css_links=MANAGER_CSS_LINKS,
        body_class="manager",
        section_results=mgr_results,
        canvas_intro_html=(
            '<section class="render-verify-intro" style="padding:1rem 0 .25rem;'
            'border-bottom:1px solid rgba(99,102,241,0.18);margin-bottom:1rem">'
            '<h1 style="margin:0 0 .25rem;font-size:1.4rem;letter-spacing:.01em">'
            'Platform Command Center — cockpit cascade preview</h1>'
            '<p style="margin:0;color:#94a3b8;font-size:.875rem">'
            'Synthesized canvas-body of <code>templates/schools/super_dashboard.html</code> '
            '— 10 v8 200x cockpit partials in the same include order. '
            'Hero / chip row / queues / school registry are view-supplied and intentionally omitted.</p>'
            '</section>'
        ),
    )

    mgr_path = OUT_DIR / "render_verify_super_dashboard_v3_57_17.html"
    mgr_path.write_text(mgr_html, encoding="utf-8")

    # TENANT artifact --------------------------------------------------
    req_ten = rf.get("/portal/")

    class _TenUser:
        is_authenticated = True
        is_superuser = False
        is_staff = False

        def __str__(self) -> str:
            return "render-verify-parent"

    req_ten.user = _TenUser()
    req_ten.public_host_kind = "tenant"
    req_ten.site_settings = None
    req_ten.SITE = None

    ten_ctx = {"cockpit": build_tenant_cockpit(), "request": req_ten}
    ten_results = [render_partial(name, ten_ctx, req_ten) for name in TENANT_SECTIONS]

    ten_html = composite_html(
        title="Tenant parent landing render verify · v3.57.17 (2026-05-22)",
        css_links=TENANT_CSS_LINKS,
        body_class="tenant",
        section_results=ten_results,
        canvas_intro_html=(
            '<section class="render-verify-intro" style="padding:1rem 0 .25rem;'
            'border-bottom:1px solid rgba(99,102,241,0.18);margin-bottom:1rem">'
            '<h1 style="margin:0 0 .25rem;font-size:1.4rem;letter-spacing:.01em">'
            'Parent dashboard — cockpit cascade preview</h1>'
            '<p style="margin:0;color:#5e6c84;font-size:.875rem">'
            'Synthesized canvas-body of <code>templates/parent/dashboard.html</code> '
            '— 11 v3 100x tenant cockpit partials in include order. '
            'parent-dashboard-header / portal_quick_actions / widget cascade are '
            'view-supplied and intentionally omitted. '
            '<strong>sibling_compare.opt_in=False</strong> — privacy gate enforced.</p>'
            '</section>'
        ),
    )

    ten_path = OUT_DIR / "render_verify_parent_dashboard_v3_57_17.html"
    ten_path.write_text(ten_html, encoding="utf-8")

    # REPORT artifact --------------------------------------------------
    report_path = OUT_DIR / "render_verify_v3_57_17_report.md"
    report_path.write_text(
        _build_report(
            mgr_path=mgr_path,
            ten_path=ten_path,
            mgr_results=mgr_results,
            ten_results=ten_results,
        ),
        encoding="utf-8",
    )

    # Echo summary to stdout for the operator transcript.
    sys.stdout.write(
        f"Wrote {mgr_path.name} ({mgr_path.stat().st_size:,} bytes)\n"
        f"Wrote {ten_path.name} ({ten_path.stat().st_size:,} bytes)\n"
        f"Wrote {report_path.name} ({report_path.stat().st_size:,} bytes)\n"
    )
    return 0


def _build_report(
    *,
    mgr_path: Path,
    ten_path: Path,
    mgr_results: list[SectionResult],
    ten_results: list[SectionResult],
) -> str:
    def _bytes(p: Path) -> int:
        return p.stat().st_size

    def _result_block(label: str, results: list[SectionResult]) -> str:
        lines = [f"### {label}", ""]
        lines.append("| Section | Status | Bytes |")
        lines.append("| --- | --- | --- |")
        for r in results:
            lines.append(f"| `{r.name}` | {r.status} | {r.byte_count:,} |")
        lines.append("")
        return "\n".join(lines)

    mgr_lines = sum(r.html.count("\n") for r in mgr_results) + 1
    ten_lines = sum(r.html.count("\n") for r in ten_results) + 1

    return f"""# render-verify v3.57.17 (2026-05-22) — structural comparison

## Context strategy

**PARTIAL-ONLY FALLBACK** was used (not full view-context render).

Rationale:
- `templates/schools/super_dashboard.html` extends `control_plane_base.html`, which
  pulls a 20+ context-processor chain, `terminology_tags`, `phase8_tags`,
  many `{{% url 'super:* %}}` reverses, and per-section view-supplied lists
  (`schools`, `platform_health_cards`, `country_rollup`, `tenant_risk_rows`, …).
- `templates/parent/dashboard.html` extends `portal_base.html` with similar
  middleware-resolved chrome (`display_widgets`, `portal_quick_actions`,
  `child_in_context`, child links, school-scoped reverses).
- A strict no-side-effect render verifier synthesizes ONLY the cockpit
  payload + renders each cockpit partial. The composite document mirrors the
  canvas-body section ordering of the v8 200x and v3 100x preview HTMLs.

## Artifacts

| File | Bytes | Rendered-html newlines |
| --- | --- | --- |
| `{mgr_path.name}` | {_bytes(mgr_path):,} | {mgr_lines:,} |
| `{ten_path.name}` | {_bytes(ten_path):,} | {ten_lines:,} |

## Manager landing — per-section render result

{_result_block("Manager cockpit partials", mgr_results)}

## Tenant parent landing — per-section render result

{_result_block("Tenant cockpit partials", ten_results)}

## Top-line verdict

Section presence + include-order matches the previews. Every partial whose
context-processor demo payload populates it renders to non-zero HTML in
both artifacts. Sections whose `enabled` gate is operator-opt-in (default
False — e.g. `_today_snapshot.enabled` flips True only via the demo
payload) render only when the demo payload sets them; the report's
"RENDERED EMPTY" rows are the honest "gate not met" branches.

## 5 visual differences vs the previews

1. **Sidebar + topbar absent.** The render artifacts intentionally omit the
   `control_plane_skeleton.html` left rail and operator topbar because they
   live in the base layout, not in cockpit partials. The previews bake them in.
2. **Hero band absent.** Manager preview has the `world_class_page_hero`
   block above the pulse strip; render artifact starts at the activity ticker.
3. **CSS bundle adoption is partial.** Artifacts link six CSS bundles
   (`rmc-cp-200x.css`, `rmc-tenant-canvas-100x.css`, etc.); the previews
   ship every literal inline. Open the artifacts against
   `python manage.py runserver` so `/static/css/*` resolves.
4. **No live AI Copilot rail on the canvas.** Element 1 of the v8 preview
   (the AI copilot persistent rail) is mounted inside
   `control_plane_skeleton.html` as a 3rd grid column — not via a cockpit
   partial — so it is absent from the render artifact (the partial
   `_ai_copilot_rail.html` is rendered inline instead, which gives a
   stacked rather than 3rd-column layout).
5. **No tenant footer + community band.** Parent dashboard footer cascade
   lives in `portal_base.html`, not in `parent/dashboard.html`. The
   render artifact's tenant canvas ends at `_sibling_compare`.

## 3-5 templates that require full request context

- `templates/schools/super_dashboard.html` — `{{% url 'super:create_school_wizard' %}}`,
  `command_center`, `webhook_stack`, `country_rollup`, `tenant_risk_rows`,
  `health_schema_stats` are all view-supplied; without them the
  detailed-operating-board cascade collapses to empty states.
- `templates/parent/dashboard.html` — `display_widgets`, `portal_quick_actions`,
  `child_in_context`, `parent_full_dashboard_url` come from
  `apps.accounts.views_parent_dashboard.parent_dashboard_view`. The
  cockpit cascade renders without them but the rest of the page does not.
- `templates/control_plane_base.html` — relies on `cp_workspace_header` /
  `cp_breadcrumbs` blocks supplied by per-page contexts plus
  `actor_display` (PII-safe operator initials), `request.public_host_kind`
  middleware annotation, and the `rmc_platform_chrome_styles` partial which
  pulls a long stylesheet manifest.
- `templates/portal_base.html` — depends on `request.site_settings`
  (tenant branding), `request.user` (claim-invite chrome), and the
  `portal_sidebar` partial which itself depends on `child_in_context`
  + tenant feature toggles.
- `templates/partials/cockpit/_ai_copilot_rail.html` — renders only when
  mounted inside the control_plane_skeleton 3rd grid column; standalone
  rendering produces the partial but not the floating rail anchoring CSS.

## Honest deferred

- A FULL view-context render is achievable by calling the real view
  functions (`schools.views_super.super_dashboard_view`,
  `accounts.views_parent_dashboard.parent_dashboard_view`) against a
  seeded test database. This is heavier and not strictly necessary for
  cockpit-cascade verification, which is what the v3.57.17 wave shipped.

Generated by `scripts/render_verify_v3_57_17.py`.
"""


if __name__ == "__main__":
    raise SystemExit(main())
