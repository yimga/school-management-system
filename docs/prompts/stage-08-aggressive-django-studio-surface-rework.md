# Stage 8 Aggressive Django And Studio Surface Rework

## Mission

Audit first, then redesign and implement the shared body-surface contract for RunMyCampus Django admin pages, tenant Studio work modes, tenant configuration pages, and operator configuration pages. Do not assume prior work is complete. Prove it by scanning templates, rendering pages, checking browser screenshots, and fixing every verified gap.

This prompt is intentionally stricter than the earlier configuration-engine-only prompt. The screenshots show active defects that must be addressed from the root:

- Django admin change forms are too narrow, poorly balanced, and blocked by sticky save bars.
- Studio Experience and Theme surfaces are cramped, overlapped, and leak content across columns.
- Studio work modes waste large blank space and then cram preview/configuration below the fold.
- Automation work mode can render a 500/502-style error instead of a native resilient surface.
- Live preview is not consistently usable. It must work inline, as a drawer, as a popout, or in a new tab.
- Tenant and operator surfaces must stay strictly separated. Tenant pages must never route into operator admin or manager-only surfaces unless explicitly switching to an operator context.

## Non-Negotiable Rules

1. Audit before editing production templates.
2. Produce browser-ready before/after HTML for approval before implementation.
3. Do not change headers, sidebars, or footers unless the defect is caused by a body/shell collision.
4. Preserve tenant/operator separation.
5. Use full available body width intelligently.
6. No overlap, no clipped controls, no hidden content, no content bleeding through sticky bars.
7. No iframe-only critical workflows. If an iframe fails, the page must still provide a native surface and a clear recovery path.
8. Live preview must have fallback presentation modes: inline, drawer, popout modal, and open in new tab.
9. Every page touched must be validated by route inventory, template scan, browser render, and tests.

## Surfaces To Inventory

Audit these page families page by page:

- Django admin change forms and changelists on `/admin/` and `/super/`.
- Tenant backend configuration pages.
- Operator configuration pages.
- Studio Overview, Experience, Automation, Outputs, Launch, and Control.
- Theme and Experience configuration.
- Feature Controls.
- Workflow Center and workflow builder pages.
- Report Card Builder and report preview surfaces.
- Dashboard previews and dashboards by role.
- Forms/admissions preview surfaces.
- Communications preview surfaces.
- Launch preview and setup studio pages.

## Audit Checks

For each page, record:

- Route and host plane: tenant, tenant backend, operator, manager, or shared.
- Template and CSS files used.
- Whether the page uses the shared body contract.
- Whether body width is capped unnecessarily.
- Whether any `iframe` is critical to the workflow.
- Whether live preview exists and which modes are available.
- Whether sticky bars overlap body content.
- Whether context rails are squeezing the main form or preview.
- Whether long labels, tokens, paths, password hashes, or JSON values wrap correctly.
- Whether the page redirects to the wrong host plane.
- Whether the page renders at 1366, 1536, 1920, and mobile widths without overlap.

## Target Layout Contract

Implement one shared body contract with these zones:

- `rmc-surface-command`: compact title, status, primary actions, and preview controls.
- `rmc-surface-grid`: responsive page grid that uses the full body width.
- `rmc-surface-main`: primary editor/form/list content.
- `rmc-surface-rail`: contextual guidance, audit, state, and actions. It may collapse into a drawer.
- `rmc-preview-system`: live preview controller with inline, drawer, popout, and new-tab modes.
- `rmc-save-dock`: compact save actions that never cover active fields.
- `rmc-error-recovery`: native fallback for iframe/service failures.

## Studio Work Mode Requirements

All Studio work modes must use the same contract:

- Overview: cockpit summary plus actionable next steps.
- Experience: brand/theme editor with live preview drawer or popout, not a cramped inline preview.
- Automation: native automation cockpit, diagnostics, simulation preview, and no blank iframe failure.
- Outputs: report/document preview with usable scale controls and new-tab fallback.
- Launch: readiness matrix, blockers, preview by role, and publish confidence panel.
- Control: governance/change preview with rollback and audit proof.

## Django Admin Requirements

Django change forms must become full-width operational forms:

- Fieldsets become responsive cards or grouped field matrices.
- Long password hashes, JSON, help text, and IDs wrap safely.
- Submit actions move into a right-side or bottom-safe dock that does not cover fields.
- Object tools and history remain available without stealing main content width.
- Tenant admin pages use tenant branding and tenant scope only.
- Operator admin pages use operator branding and operator scope only.

## Live Preview Requirements

Every configurable surface that changes user-visible output must support preview:

- Inline preview only for small confidence snapshots. Do not cram a full product screen into a narrow form column.
- Full-width preview theater for Studio Experience, Theme, dashboard, report, form, communication, launch, and other visual configuration work.
- Drawer preview for wide pages where inline would squeeze the form.
- Popout modal for direct comparison while editing.
- Open in new tab when frame restrictions or auth boundaries block embedding.
- Clear status labels: Draft, Published, Sandbox, Tenant, Operator, Role, Device.
- No `href="#"` placeholders.
- No hidden broken iframes as the only proof path.

## Full-Width Surface Requirements

The body canvas must use available width intelligently across tenant-wide and platform-wide pages:

- Remove unnecessary centered max-width wrappers from operational pages.
- Prefer full-width workbenches with stable zones over stacked narrow cards.
- Use compact left configuration panels only when the main preview/editor gets the majority of the width.
- Promote cramped inline previews into a full-width preview theater.
- Keep control groups close to the thing they affect, but never inside a crowded preview.
- If a page has complex configuration plus preview, use this rhythm:
  1. command strip
  2. full-width preview theater or builder canvas
  3. configuration drawer/panel
  4. audit/state rail
  5. safe save dock
- Pages must be tested at 1366, 1536, 1920, ultrawide, tablet, and mobile widths.

## Automation 502 Requirements

The Automation work mode must be audited from the route and view layer:

- Reproduce `/studio/automation/` locally.
- Capture the traceback or server log for the 500/502 state.
- Confirm whether failure comes from an embedded legacy URL, missing context, DB schema drift, permissions, or template error.
- Replace critical iframe dependency with native automation panels when possible.
- If a legacy embed is still needed, wrap it in `rmc-error-recovery` with retry, full-window open, diagnostics, and stable fallback content.

## Validation Loop

Run the loop until clean:

1. Route/template inventory.
2. Static CSS/template scan for narrow caps, sticky overlays, critical iframes, and tenant/operator links.
3. Browser render for representative tenant and operator pages.
4. Screenshot inspection at desktop and narrow widths.
5. Focused Django tests for Studio, admin surface boundaries, tenant/operator separation, live preview contracts, and automation routes.
6. `python manage.py check`
7. `python manage.py makemigrations --check --dry-run`
8. `python -m compileall -q apps config scripts`
9. Gap report with zero unowned critical gaps before commit.

## Approval Artifact

Before production implementation, render:

`var/design-previews/django-studio-aggressive-surface-rework-approval.html`

The artifact must show:

- Current problem patterns.
- Proposed Django admin change-form layout.
- Proposed Studio Experience layout.
- Proposed Automation recovery/cockpit layout.
- Live preview modes: inline, drawer, popout, and new tab.
- Explicit implementation checklist.

## Commit Rule

Only after approval:

- Implement the shared contract.
- Apply it platform-wide and tenant-wide.
- Re-audit all listed page families.
- Fix all critical gaps.
- Commit and push to `main`.
