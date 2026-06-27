# PROMPT 1 — Implement the tenant HTMLs: width-to-width, intelligent, page-aware (tenant-wide)

> Paste this as a single instruction. It is **surgical**: every gap below was audited against the live
> code on 2026-06-26, so do NOT rebuild what already ships — close the named gaps only.

## Mission

Make every tenant + control-plane page render **width-to-width** — the surface and body used edge to edge,
nothing clustered to the left with a dead right gutter — while staying **intelligent, balanced and
page-aware**: a page FILLS the width when its content is a catalog/list/workflow/config, and CENTERS to a
readable measure ONLY when its content is a single narrow form where full-width inputs would be unreadable.
This is a **tenant-wide** contract: fixes land in shared utilities, shells and partials so they apply to
**past, present and future tenant profiles** — never per-tenant patches.

Align to the goal: be the AWS / Salesforce / Shopify of school management. Apple-tier, premium, luxury,
best-in-class. Nothing saved for later.

Source-of-truth design files (read them first):
- `docs/generated/blueprint_width_fix_proposals.html` — the width cure (FILL vs CENTER, ~50-page map)
- `var/design-previews/tenant-surface-world-class-proposal.html` — zero-friction 3-pane "fill, no void" canvas
- `var/design-previews/tenant-implemented-shell-live.html` — the live shell contract (already full-width)
- `var/design-previews/tenant-dashboard-style-branding.html` — the visual presets
- `docs/generated/ask_ai_before_after_review.html` — Ask-with-AI must be a bounded dock, never a full-width post-footer frame

## Non-negotiable constraints

1. **No hardcoding.** Route every value through the 7-layer configurability cascade. New measure/grid sizes
   become **tokens** in `static/css/design-tokens.css` or `static/css/rmc-class-grammar.css`, never inline literals.
2. **Define before you reference.** `scan_undefined_css_classes.py` baseline is **0** — any new class
   (`.content-measure`, `.cp-form-grid`, `.cp-card-grid`) MUST be defined in a CSS file under `static/css/`
   or the gate fails. Same for `scan_inline_style_off_token.py` (no off-token inline styles) and
   `scan_horizontal_overflow_risk.py` (no new overflow).
3. **Page-aware, not blanket.** Apply the decision rule below per template. Do NOT center catalogs; do NOT
   stretch single short forms to full width.
4. **Extend the grammar, don't fork it.** Reuse the existing `.cp-grid`/`.cp-grid-2`/`.cp-grid-3` auto-fit
   grids and `.content-max-*` family. Add only the 3 missing primitives.
5. **Tenant-wide = shared layer.** Land fixes in shells (`portal_base.html`, `control_plane_skeleton.html`),
   shared partials, `components/form_field.html`, and CSS utilities — so all profiles inherit them.
6. **Preserve all routes / behavior.** Reference-integrity gates are RUNTIME and zero-baseline
   (url-name, template-ref, field-ref, relation-path, import, get_model). Don't break a `{% url %}` or a route.
7. **Shared tree discipline.** Never `git add -A` (a concurrent agent "Cursor" works the same tree); stage
   only your own paths. Never stash/reset peer work. Bump `static/js/service-worker.js` `CACHE_VERSION`
   per the deploy checklist (coordinate if it is held dirty).
8. **Verify, don't fabricate.** AUDIT-FIRST each template before editing; show diffs; run the gates.

## The rule: FULL WIDTH everywhere (owner clarification)

"Width to width" = **full width, edge to edge.** Every page uses the whole canvas. Centering a column is NOT a
cure — it just moves the dead space to both sides. The ONLY question is *how* to fill the width usefully:

```
Is the page's primary content…
  • a CATALOG / LIST / QUEUE?                          → FILL: .cp-grid / .cp-card-grid (responsive card grid spans the canvas)
  • an OPERATOR WORKFLOW (gutter holds detail)?        → FILL: two-pane master-detail (list + .pane-detail)
  • an OPERATOR CONFIG FORM (many fields/toggles)?     → FILL: .cp-form-grid (responsive field grid spans the canvas)
  • a SPARSE / NARROW FORM (few fields)?               → FILL via .rmc-page-horizon: form in __main, USEFUL content in __aside
                                                          so the PAGE is full width without stretching one input to an
                                                          unreadable line. (Do NOT center it.)
  • marketing/* , admin/* , onboarding, tenant_wizard, direct_thread, chat? → LEAVE (their own deliberate measures)
```
Always `container-fluid` (never a centered `.container`/`col-lg-*` cap on a tenant/control-plane page).
**Centering is retired** as a strategy. `.content-measure` is reserved ONLY for the bounded Ask-with-AI help
DOCK (a floating panel the design review explicitly requires to be bounded, not full-width) — never for a page.

## Ground truth (audited 2026-06-26) — what EXISTS vs what to BUILD

EXISTS (reuse, do not recreate):
- `.cp-grid` / `.cp-grid-2` / `.cp-grid-3` auto-fit grids — `static/css/rmc-class-grammar.css:49-54`
- `.content-max-520/640/960/1200` — `static/css/rmc-class-grammar.css:31-34`
- `.page-wrap` — `static/css/portal-base-shell.css:208,403` (NOTE: `margin-inline:0` — does NOT center)
- `components/form_field.html` — `templates/components/form_field.html` (no width constraint)
- blueprint_marketplace already converted to `.cp-grid cp-grid-3` (the symptom page is done)

MISSING (build these — minimal, token-driven):
- `--rmc-measure` token (~1080px readable measure) in `design-tokens.css`
- `.content-measure { max-inline-size:var(--rmc-measure); margin-inline:auto; }` in `rmc-class-grammar.css`
- `.cp-form-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr)); gap:… }`
- (optional) `.cp-card-grid` alias if a list needs explicit card semantics distinct from `.cp-grid`

## Workstream W1 — Width-to-width content remediation (~35–40 templates, page-aware)

1. Add the 3 missing primitives above (tokens + classes). Confirm `scan_undefined_css_classes` stays 0.
2. Make `.page-wrap` page-aware: when a page opts into a narrow measure (a `data-page-archetype` /
   body flag), it centers via `.content-measure`; otherwise it fills. Do this in the shared CSS, not per page.
3. FILL — swap remaining single-column `.cp-list` catalogs to the responsive grid:
   - `templates/marketplace/package_rollout.html`
   - `templates/marketplace/governance_console.html`
   - `templates/marketplace/sandbox_inspector.html`
   - audit the rest of `templates/marketplace/*` + control-plane queues for `.cp-list` and convert where they are catalogs.
4. FILL — operator config forms → `.cp-form-grid`:
   - `templates/siteconfig/super/cockpit_configure.html` (currently `.container-fluid` full-width, un-gridded)
   - `templates/siteconfig/super/theme_personality_configure.html`
   - `templates/siteconfig/super_dashboard_defaults_admin.html`
   - any other `*_configure.html` / `*_defaults*.html` operator forms.
5. FILL (two-pane) — where the design doc calls for master-detail (gutter holds the preview/apply/rollback):
   - blueprint detail, `governance_console`, `monetization_inspector`, `sandbox_inspector`.
   - Build ONE reusable two-pane partial; wire selection by query-param (no heavy JS).
6. CENTER — narrow forms + settings family → `.content-measure` (or keep `.content-max-640`):
   - tenant forms: `templates/accounts/profile_edit.html`, `accounts/delegation_form.html`,
     `portal/faq_submit.html`, `portal/document_upload.html`, `portal/signature_*` (4 files)
   - settings family: all `*_settings.html` (≈15 under `templates/siteconfig/` + `portal/configure/` +
     `assist_dock/power/settings.html` + `apicenter/super/ai_center_settings.html`) — most already use
     `.content-max-640`; migrate them to the shared `.content-measure` token so the measure is configurable once.
7. CAPPED/mixed — decide per page (A or C): `monetization_inspector`, `bulk_letters`,
   `installed_packages_rollback`, `sync_center`.
8. Acceptance: no template renders a sparse left-clustered column on a wide viewport; `scan_undefined_css`,
   `scan_inline_style_off_token`, `scan_horizontal_overflow_risk`, `audit_template_render_safety` all clean;
   regenerate `docs/generated/blueprint_width_fix_proposals.html` mapping → 0 remaining BEFORE-state pages.

## Workstream W2 — Ask-with-AI: kill the full-width post-footer frame

The bounded dock already exists as the copilot-rail **Help tab** (`templates/partials/cockpit/_ai_copilot_rail.html:271-315`,
CSS `static/css/rmc-copilot-help-mode.css`, JS `static/js/rmc-kb-ai-assistant.js`) — bounded, closed-by-default,
same endpoints. Just retire the inline panel:
1. Remove the conditional `{% include "partials/help_module_inline_assistant.html" %}` from the 5 pages:
   `finance/dashboard.html`, `evals/compliance_dashboard.html`, `siteconfig/console_domains_hub.html`,
   `teacher/attendance.html`, `migration_cloud/operator/command_center.html`.
2. Retire `templates/partials/help_module_inline_assistant.html` (clean delete; add a CSS_RETIREMENT_DOCKET note).
3. Repurpose `apps/portal/help_proactive_inline.py::module_inline_assistant_for_request` to pass the
   `help_module_slug` into the rail Help tab context (so the tab pre-targets the right KB domain) instead of
   gating a full-page panel.
4. PRESERVE routes: `ai-support-assistant`, `ai-support-assistant-stream`, `ai-support-session-rating`
   (`apps/api/urls.py`). Verify with url-name + template-ref gates.

## Workstream W3 — Finish the zero-friction last mile (already 5/8 shipped)

1. One-click presets beyond the wizard: where a role landing offers a multi-step setup, surface a single
   "apply preset" action (reuse the wizard preset pattern `setup_studio/partials/wizard_migration_scope_zero_friction.html`).
2. Reusable sticky action dock with a path breadcrumb ("Path: Scope → Upload → Done in 3 clicks"): extract
   ONE partial from the wizard, usable on any task page; pin to bottom of the canvas (respect the
   sticky+overflow gate — never `overflow:hidden` on a sticky column).
3. Action copilot: confirm the rail "Actions" tab actually EXECUTES (1-tap) — trace
   `static/js/rmc-copilot-rail.js`; if execution is stubbed, wire it to real page actions with RBAC via
   `services/ai_copilot_rbac.py` (keep `verify_ai_copilot_rbac_coverage` at 0).

## Workstream W4 — Visual presets land on every tenant profile

The cascade + 50-item registry exist (`apps/siteconfig/portal_visual_presets_registry.py`,
`DashboardUserPreference.role_visual_presets`, → `data-rmc-aesthetic`). Close the coverage gap:
1. Ensure a **per-role default preset** resolves for every role even when a tenant set nothing (RuntimeDefaults
   seed). Reconcile the legacy 8 slugs vs the registry so no role falls back to a blank/“none”.
2. Make it apply to **past/present/future** tenants: seed defaults via a data migration / `RuntimeDefaults`
   so existing schools inherit, and the signup path sets them for new schools.
3. Verify the 8 named looks from the gallery all have CSS token blocks under `[data-rmc-aesthetic=...]`.

## Validation / acceptance (run before claiming done)

- `python manage.py check`
- Gates: `scan_undefined_css_classes`, `scan_inline_style_off_token`, `scan_off_token_colors`,
  `scan_horizontal_overflow_risk`, `audit_template_render_safety`, the reference-integrity family
  (import / get_model / url-name / template-ref / field-ref / relation-path), `scan_theme_locked_token_text`.
- Revert any scanner baseline writes if `finding_count` is unchanged (keep commits to your files only).
- Bump SW `CACHE_VERSION`; update `docs/CSS_RETIREMENT_DOCKET.md`; update memory.
- Re-render the width proof: 0 left-clustered pages remain.

## Output

Per workstream: the files touched, the diff rationale, the gate results, and an honest "what's left / what was
deliberately left centered." No silent truncation — if you cap coverage, say which templates were dropped and why.
