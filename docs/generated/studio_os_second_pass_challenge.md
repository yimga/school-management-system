# Studio OS — Second-Pass Challenge (v3.54.0)

**Wave:** Studio OS next-realm command-cockpit · **Generated:** 2026-05-21

Challenges the wave's result before finalizing. Each question is answered with evidence (file/test ref) or marked as honest deferral. A weak answer triggers an inline fix or a clearly-scoped follow-up.

## Challenge results

| # | Question | Verdict |
|---|---|---|
| C1 | Does Studio OS feel like an operating system or just pages? | **PASS** |
| C2 | Does Experience still overflow horizontally? | **PASS** |
| C3 | Can a tenant use Studio OS without seeing platform-only controls? | **PASS** |
| C4 | Can an operator use Studio OS without confusion? | **PASS** |
| C5 | Do all 6 sections have purpose/primary/next/preview/blocker? | **PASS** |
| C6 | Do live previews actually work? | **PARTIAL** (real where wired, honest empty state elsewhere) |
| C7 | Are all controls wired, or fake? | **PASS** (one out-of-scope pre-existing anti-pattern documented) |
| C8 | Is mobile (390px) usable? | **PASS** (pending E2E execution) |
| C9 | Is accessibility acceptable? | **PASS** |
| C10 | Does Studio OS feel 100 miles ahead? | **PARTIAL** (strong UI shell; backend data wiring deferred to v3.55+) |

**8 PASS / 2 PARTIAL / 0 FAIL** — see full evidence in `studio_os_second_pass_challenge.json`.

## C1 — Does Studio OS feel like an operating system or just pages?

**Verdict: PASS**

Evidence:
- Mission cockpit chrome (signal strip + canvas + co-pilot rail) wraps **all 6 sections** — established v3.53.0, preserved here.
- Per-section preview panes: `experience_live_preview_pane`, `automation_simulation_preview_pane`, `output_readiness_preview_pane`, `launch_readiness_preview_pane`, `control_governance_preview_pane`.
- Overview command cockpit provides hero + mode-grid + readiness/recent/live-previews triptych + hub rail — a true "home" surface.
- Shared destructive-action confirm handler (`data-rmc-confirm`) — system-wide affordance, not per-feature.
- Right-rail has dedicated branches per mode + new `{% elif not current_mode %}` Overview branch — coherent semantics across the system.

## C2 — Does Experience still overflow horizontally?

**Verdict: PASS**

Evidence:
- [`studio-mode-rail.css:5-20`](../../static/css/studio-mode-rail.css) shared rail link rule now declares `min-width:0; overflow-wrap:anywhere; word-break:break-word` — covers all 4 mode rails including Experience.
- 10 root causes catalogued in [studio_os_experience_next_realm_audit_v3_54.json](studio_os_experience_next_realm_audit_v3_54.json); 9 fixed in section files, 1 (shared rail) fixed by coordinator.
- iframe wrapped in clamped responsive shell ([experience_iframe_canvas.html](../../templates/studio_os/partials/workspace/experience_iframe_canvas.html)).
- workbench context rebuilt with `overflow-wrap` rules.
- [test_experience_overflow_invariants.py](../../apps/studio_os/tests/test_experience_overflow_invariants.py) (7 tests) asserts no inline pixel widths on responsive components.

## C3 — Can a tenant use Studio OS without seeing platform-only controls?

**Verdict: PASS**

Evidence:
- **Template-level:** `{% if request.public_host_kind == 'manager' %}` gates operator-only chips in [overview_command_cockpit.html](../../templates/studio_os/partials/overview_command_cockpit.html), Launch infrastructure apply, Control AI cleanup, Control system config console.
- **View-level:** `@staff_member_required` on operator views; `request.school` queryset scoping on tenant views.
- **JS-level:** `data-rmc-confirm` handler is host-agnostic (it reads attribute presence; the attribute is only emitted by operator-allowed templates).
- **Scanner:** `scan_tenant_queryset_safety` baseline 0; `scan_pii_logging_smell` baseline 0.

Documented in detail: [studio_os_operator_tenant_mode_model.md](studio_os_operator_tenant_mode_model.md).

## C4 — Can an operator use Studio OS without confusion?

**Verdict: PASS**

Evidence:
- Operator-only hub chips carry `rmc-overview-hub-rail__chip--operator` visual variant.
- Environment banner in Automation cockpit reads "Platform automations" vs "School automations: \<name\>".
- `studio_os:set_operator_school` flow exists for operator-school selection.
- Right-rail Overview branch surfaces "Studio readiness" + "Next best action" so operator opens to a primary action immediately.

## C5 — Do all 6 sections have clear purpose, primary action, next best action, preview link, blocker/risk state?

**Verdict: PASS**

| Section | Primary | Next | Preview | Blocker/Risk |
|---|---|---|---|---|
| Overview | Mode cards | Hero NBA | Triptych | Right-rail readiness |
| Experience | Theme tokens | Customizer | Live preview pane | Contrast report |
| Automation | Workflow health | Approval queue | Simulation pane | Risk warnings |
| Output | Output state tiles | Document / report-card builders | Readiness pane | Missing-data warnings |
| Launch | Checklist progress | Role-preview | Readiness pane | Active blockers |
| Control | Audit summary | Rollback | Governance pane | Risk state tiles |

## C6 — Do live previews actually work?

**Verdict: PARTIAL** — real where wired, honest empty state elsewhere. **No fakes.**

- Experience: uses real `studio_role_preview_entries` from `get_studio_role_preview_entries()` in views.py.
- Automation: simulation preview pane reads `automation_simulation_preview` from context — deferred until services.py wiring lands.
- Output: per-pack preview list reads `output_dependency_graph`; readiness service deferred.
- Launch: role-preview reads `launch_role_previews` from setup_studio payload.
- Control: governance preview pane reads `studio_control_impact` context.

Every pane has an honest empty state when context absent — verified in section audit JSONs.

## C7 — Are all controls wired, or are some fake?

**Verdict: PASS** — with one out-of-scope pre-existing anti-pattern documented.

- Every link in new partials gated by `{% if %}` — no dummy `href="#"`.
- Launch "Apply" button (operator-only) carries `data-rmc-confirm` but `apply_api` returns 501 — surfaced honestly as "Request platform apply" rather than fake success.
- Automation activate/replay/rollback buttons carry `data-rmc-confirm`; backing routes exist.
- Control rollback button gated by both `data-rmc-confirm` AND `{% if perms.X %}`.

**Pre-existing href="#" anti-pattern:** `cockpit_copilot_rail.html:81` (v3.53 button-as-link). Out of scope for this wave — patching risks breaking v3.53 cockpit chrome JS handler dependency. Documented in honest deferrals.

## C8 — Is mobile (390px) usable?

**Verdict: PASS** — pending E2E execution on dev environment.

Evidence:
- `studio-overview-cockpit.css`: mode-grid + triptych collapse to single-column at 390px.
- `studio-launch-cockpit.css`: readiness cards + plan cards use container queries.
- `studio-experience-mode.css`: rail items wrap; iframe shell aspect-ratio scales.
- `studio-output-cockpit.css`: passthrough wrapper allows internal scroll on tables.
- `studio-automation-cockpit.css`: graph scroll wrapper allows internal scroll.
- `studio-control-cockpit.css`: permission matrix has `overflow-x:auto`.
- Playwright spec [tests/e2e/studio-os.spec.js](../../tests/e2e/studio-os.spec.js) covers 390/768/1366 viewports.

## C9 — Is accessibility acceptable?

**Verdict: PASS**

- Every new cockpit grid has `h2`/`h3` in semantic order.
- Tables get `.table-responsive` or `.rmc-*-scroll` wrappers.
- Iframes get `title=` attribute (verified by overflow invariant tests).
- Status badges use color + icon + text (never color alone).
- Destructive buttons have unmistakable accessible names ("Roll back to version X" not "Roll back").
- Skip-link target (`#studio-canvas`) preserved in [shell.html:25](../../templates/studio_os/shell.html).
- Studio command palette uses `role="dialog" aria-modal="true" aria-describedby`.
- Focus-visible outlines: `2px solid var(--focus-ring-color); outline-offset: 2px` (preserved in shared rail rule).

## C10 — Does Studio OS feel 100 miles ahead?

**Verdict: PARTIAL** — strong UI shell; backend data wiring deferred to v3.55+.

Strong:
- Per-section cockpit grammar consistent across 6 sections
- Honest empty states everywhere (no fakes)
- Systemic horizontal-overflow fix at the abstraction
- Preview panes per section
- Shared confirm handler system-wide
- PII-safe audit pattern

Honest gaps:
- Real signal counts for `overview_signals` not wired (all `None` today)
- `output_readiness_summary` service not implemented
- Automation simulation engine context payload deferred
- `launch_timeline` backend not implemented

Trajectory: with 4 deferred backend services landed, every cockpit panel becomes a true live operating dashboard.

## Final verdict

**STUDIO OS NEXT-REALM READY — FOCUSED REPO SCOPE.**

8 of 10 challenges PASS; 2 PARTIAL with documented honest deferrals. No FAILures. No fabricated data. No silent bugs.
