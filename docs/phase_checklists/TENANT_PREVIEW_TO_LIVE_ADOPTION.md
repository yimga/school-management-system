# Tenant preview → live adoption program

**SOT anchor:** `RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` §11.4 batch **1727+**
**Validation hub (canonical index):** `var/design-previews/tenant-threshold-all-in-one-validation.html`
**Role index:** `var/design-previews/tenant-role-dashboards-hub.html`
**Machine registry:** `scripts/generated/tenant_preview_to_live_registry.json`
**Gate:** `python scripts/verify_tenant_preview_to_live_adoption.py`

---

## Mission (good → best)

Every static HTML under `var/design-previews/` that represents a **tenant role surface** (Admin, Teacher/Staff, Parent, Student) must become the **live Django shell + role-home canvas** — not a parallel mock. Previews are the visual contract; production must match them in layout, density, chrome, copilot/tools rail, surfaces, and fold discipline.

**Non-negotiables**

- Semantic tokens only (`design-tokens.css`, `.rmc-*` grammar). No forked hex in templates.
- **4 viewport folds max** on task surfaces; use tabs, numbered pagination, bottom sheets, slide-over panels, and section anchor nav — never infinite scroll on task UIs (`data-rmc-scroll-policy="paginate"`).
- Copilot + Tools = **one 56px right column** on desktop (preview: `tenant-admin-workspace-preview.html` aside.copilot).
- Copilot panel **expanded during onboarding** (<70% setup) so first-run schools see the preview’s open panel, not a mystery icon strip.
- MFA **never** hides chrome — it redirects to setup only in `strict` mode after grace expires.
- Every wave ends with a **named verifier green** + SW bump + §11.4 row — no narrative-only completion.

---

## Agent copy-paste prompt (use verbatim to start a wave)

```
You are adopting RunMyCampus tenant design previews into live Django templates.

READ FIRST:
- docs/phase_checklists/TENANT_PREVIEW_TO_LIVE_ADOPTION.md (this file)
- scripts/generated/tenant_preview_to_live_registry.json
- var/design-previews/tenant-threshold-all-in-one-validation.html (PREVIEWS[] manifest)
- var/design-previews/full-width-sweep-browsable.html (4-role horizontal contract)

SCOPE FOR THIS WAVE: <WAVE_ID> only (e.g. W0-shell, W1-admin, W2-teacher, W3-parent, W4-student).

RULES:
1. Open the preview HTML side-by-side with the live template(s) listed in the registry for this wave.
2. Port layout/structure using existing partials — extend .rmc-* / tp-* / rmc-dh-* classes; add CSS to static/css/rmc-tenant-preview-live-bridge.css when preview grammar is missing.
3. Long pages → tabs (rmc-section-nav), paginated tables (components/pagination.html), Bootstrap offcanvas/sheets (rmc-tp-pulse-sheet pattern), collapsible cockpit sections (rmc-collapsable).
4. Wire portal_base.html shell once per wave — do not fork per-role headers.
5. Real data only — no fabricated counts; empty states with CTA (rmc-empty-engine).
6. Run: python scripts/verify_tenant_preview_to_live_adoption.py --wave <WAVE_ID>
   plus wave-specific gates from registry.verifiers[].
7. Bump static/js/service-worker.js CACHE_VERSION; record §11.4 + autonomous log AFTER gates pass.

DONE WHEN: verifier PASS + Playwright role-home sweep includes this role’s new needles (if shell-touching).
```

---

## Preview → live mapping

| Preview file | Role | Live route (tenant) | Primary live templates | Wave |
| --- | --- | --- | --- | --- |
| `tenant-admin-workspace-preview.html` | Admin | `accounts:backend_dashboard` | `portal_base.html`, `backend_base_tenant.html`, `accounts/backend_dashboard.html`, `partials/tenant/setup_command_surface.html` | W0, W1 |
| `tenant-teacher-dashboard-preview.html` | Teacher | `portal:teacher_dashboard` | `teacher/dashboard.html`, `partials/tenant/hero_greeting.html`, cockpit partials | W0, W2 |
| `tenant-parent-dashboard-preview.html` | Parent | `portal:parent_dashboard` | `parent/dashboard.html`, `parent/partials/threshold_window_hero.html` | W0, W3 |
| `tenant-student-dashboard-enrichment-100x.html` | Student | `portal:student_portal_grades` | `student/learning_home.html`, `student/_rmc_dh_student_home.html` | W0, W4 |
| `full-width-sweep-browsable.html` | All 4 | (composite) | Same as above — acceptance: tab switch shows full shell each role | W5 |
| `mfa-wizard-review-void-fix-preview.html` | Setup | `setup_studio:tenant_wizard` (mfa) | MFA wizard templates + `rmc-wizard-index.css` | W6 |
| `wizard-step-assist-preview.html` | Setup | setup studio runner | wizard runner shell + assist panel | W6 |
| Inline parent mock in validation hub | Parent WOW | `portal:parent_dashboard` | `cockpit.threshold_parent_window` partial + `rmc-threshold-parent-window.css` | W3 (P1 shipped) |

**Out of scope for this program:** Operator globes, marketing threshold era, archived campus-pulse lab — separate tracks.

---

## Shared shell contract (W0 — all roles)

Match `tenant-admin-workspace-preview.html` header + `full-width-sweep-browsable.html` grid:

| Element | Preview | Live target |
| --- | --- | --- |
| Header | Single frosted row: brand + role pill + inline nav + search + actions | `tp-header` / `rmc-tenant-header-100x.css` — suppress duplicate LIVE band at lg+ |
| Brand pill | “Admin workspace” / “Teacher workspace” / etc. | `tp_brand_surface_pill` in `tenant_role_home.py` |
| Sidebar | ~260px deduped groups | `portal_sidebar.html` + intelligent filter; no duplicate labels |
| Canvas | `--canvas` / `--elevated` cards | `rmc-tenant-canvas-100x.css` + `rmc-tenant-preview-live-bridge.css` |
| Right rail | 56px: copilot icons + Tools at bottom | `rmc-tenant-portal-copilot-mount` + `rmc-operator-tools-tray.css` merge |
| Copilot | Expanded panel visible during onboarding | `cockpit.ai_copilot_rail.default_state=expanded` when onboarding <70% |
| Cmd+K | Search row | `components/rmc_command_palette.html` |

**W0 proof:** `TENANT_PREVIEW_TO_LIVE_W0_PASS`, `PREVIEW_SHELL_TENANT_V3_PARITY_PASS`, `TENANT_COPILOT_EXPAND_PASS`.

---

## Per-role canvas contracts

### W1 — Admin (`tenant-admin-workspace-preview.html`)

- **Hero:** setup ring + “Set up your school” (`rmc-setup-surface__hero`) — already partial; align spacing/gradient to preview.
- **Stages:** wizard cards in responsive grid (`rmc-setup-surface__cards`); **one stage visible** via stage tabs (shipped 1724 — verify visual parity).
- **Post-onboarding:** Overview | Cockpit bento tabs (`data-rmc-admin-bento`) — not during setup landing.
- **Fold:** section nav for setup stages; paginate any table >1 fold.
- **Innovation:** copilot insights chip “Finish setup to unlock value” from live onboarding API (`views_copilot_rail.py`).

### W2 — Teacher (`tenant-teacher-dashboard-preview.html`)

- **Hero:** teaching day headline + contextual line.
- **Fast workflows:** horizontal chip row above fold.
- **Attention queue:** paginated list or sheet if >6 items.
- **Today’s classes:** card grid; empty state with “Open gradebook” CTA.
- **Section jump nav:** `.rmc-page-fold-nav` linking `#attention`, `#classes`, `#cockpit`.

### W3 — Parent (`tenant-parent-dashboard-preview.html` + threshold)

- **Hero:** child names + next-action chips (fees/messages).
- **Threshold window:** calm vs alert (`threshold_window_hero.html`) when `cockpit.threshold_parent_window.enabled`.
- **Cockpit:** collapsible sections only — never full-height stack; use pulse drill sheet for deep dives.
- **Financial timeline:** paginated or “show more” sheet.

### W4 — Student (`tenant-student-dashboard-enrichment-100x.html`)

- **Hero:** compass/momentum copy — no void below header.
- **Tiles:** timetable + due work in 2×2 or 4-col grid above fold.
- **Fold:** `data-rmc-page-fold-nav` on learning home; paginate assignment lists.

### W5 — Full-width sweep acceptance

- Playwright / manual: `full-width-sweep-browsable.html` checklist → mapped to `run_role_home_visual_sweep.mjs` assertions for all 4 roles.
- Each role: header + sidebar + canvas + copilot rail visible at 1280px width.

### W6 — Wizards & MFA

- MFA complete state: no `100dvh` void (`mfa-wizard-review-void-fix-preview.html`).
- Wizard assist: stepper + side assist panel (`wizard-step-assist-preview.html`).

---

## Long-page toolkit (mandatory patterns)

| Pattern | When | Implementation |
| --- | --- | --- |
| **Section tabs** | 2+ logical chapters on one URL | `.rmc-section-nav` + `data-rmc-section-anchor` |
| **Numbered pagination** | Tables, search results, logs | `components/pagination.html` + `Paginator` |
| **Bottom sheet** | Drill-down from metric/card | `partials/cockpit/_tp_pulse_drill_sheet.html` pattern |
| **Offcanvas sidebar** | Filters, detail preview | Bootstrap offcanvas + `.rmc-acx-drawer` |
| **Collapsible sections** | Optional cockpit blocks | `rmc-collapsable.css` — default collapsed if below fold |
| **Modal wizard step** | 3+ form steps | Setup studio runner — never one endless column |
| **Pop-over actions** | Row actions | `.rmc-row-actions` / More menu — avoid button clutter |

---

## Verification matrix

| Script | Covers |
| --- | --- |
| `verify_tenant_preview_to_live_adoption.py` | Registry integrity + per-wave needles |
| `verify_preview_shell_100x_tenant_parity.py` | Shell dedupe + hero gates |
| `verify_preview_shell_100x_completion.py` | Phase 5 bundle |
| `verify_tenant_copilot_expand_contract.py` | Copilot expand + body mount |
| `verify_operator_tools_tray.py` | Tools tray + empty states |
| `verify_page_fold_standards.py` | 4-fold cap |
| `run_role_home_visual_sweep.mjs` | Live browser proof (CI) |

---

## Execution order

1. **W0** — Shared shell (this batch starts here)
2. **W1** — Admin canvas
3. **W2** — Teacher
4. **W3** — Parent (+ threshold WOW)
5. **W4** — Student
6. **W5** — Full-width sweep CI
7. **W6** — Wizards/MFA void fixes

Do not skip W0 when touching role canvases — header/rail drift is the #1 “nothing changed” report.

---

## MFA vs features (operator FAQ)

| Question | Answer |
| --- | --- |
| Does MFA block copilot? | **No.** Copilot is gated by `enable_tenant_ai_copilot_rail` + `enable_ai_help_assistant`. |
| Grace period? | **Yes** — `grace` mode: full access until `date_joined + grace_period_days` (default 7). |
| Default platform posture | Configurable: `RuntimeDefaults.mfa_enforcement_mode` → `optional` / `grace` / `strict`. |
| What MFA blocks | **Page access** (redirect to MFA setup) in `strict` or post-grace — not individual widgets. |

---

## Honest status (2026-06-24)

- **W0–W6 DONE** — all four role profiles adopt preview-live layout; admin cockpit ≠ Setup Studio.
- Live Playwright sweep (`run_role_home_visual_sweep.mjs`) includes `previewLive` assertion — run in CI/operator for browser proof.
- Threshold parent window (`threshold_window_hero.html`) remains opt-in cockpit pack (W3 P1).
