# Handoff: Django admin approval HTML → live `/admin/` (operator + tenant)

**Audience:** Codex / next agent  
**Date:** 2026-07-20  
**Status:** v13 density + full-fill shipped locally pending push; live visual parity with approval HTML still requires deploy proof (v13 chip on both hosts).  
**Not a parallel strategy doc.** Execution ledger remains `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`. This file is an operational handoff only.

---

## Goal

Make **operator** `manager…/admin/` and **tenant** `{school}.…/admin/` match the approved design-preview **After** surfaces — not just pass CSS audits.

## Approval sources of truth

Open these first; do not invent ratios or chrome:

- `var/design-previews/django-admin-page-aware-full-fill-approval-2026-07-19.html`
- `var/design-previews/tenant-admin-config-engine-approval-2026-07-19.html`

### Contract from those files

| Piece | Spec |
| --- | --- |
| Operator `.ws` | `minmax(0,1fr) minmax(9.2rem,17%) 2.35rem` |
| Tenant `.ws` | `minmax(0,1fr) minmax(9.5rem,18%) 2.35rem` |
| Tables | `width:100%; table-layout:fixed` |
| TOOLS | Page-aware: index ≠ list ≠ form |
| Tenant chrome | School-centric: Config center / Feature control / Portal — **no** Studio / Invite school |
| Operator chrome | Platform Backoffice; fleet CTAs on **index only** |
| Forms | Compact Save ▾ (split primary + menu) |

---

## Why the user is frustrated (real root causes)

1. Earlier ships were **CSS-ratio-only**; the approval mock is a **full surface**. User correctly saw “nothing changed.”
2. Cascade killers: 2-col rules with `#cp-main-content` / `rmc-admin-workspace-10x.css` beat the 3-col approval grid.
3. Fixes sometimes sat **local / unpushed** while the user redeployed old SHAs.
4. Static + service-worker caching made even pushed CSS look unchanged unless `?v=` + SW bump landed.
5. **Audits green ≠ visual parity.** Do not claim done from verifier narrative alone.

---

## What is already on `main` (pushed)

| Commit | What |
| --- | --- |
| `405f5bc36` | Approval 3-col grid CSS attempt |
| `43ea2f780` | Visible tenant KPIs / search / Config primary |
| `ea69cc9e9` | Lock + CI / predeploy / pre-push seals |
| `f6e299afb` | **v8 chip on BOTH** operator + tenant indexes |
| `19258c3b4` | Baseline timestamp refresh |

### Intended deploy proof (must appear on BOTH `/admin/` indexes)

```text
v13 · density+full-fill · operator+tenant
```

### Lock file

`var/admin-approval-build-lock.json`

| Key | Value (as of handoff write) |
| --- | --- |
| `build_id` | `2026-07-21-v13` |
| `cache_bust` | `20260721-admin-density-full-fill-v13` |
| `sw_version` | `sms-v4.05.166-admin-density-full-fill-v13-2026-07-21` |

When bumping a wave: edit the **lock first**, then templates / CSS / SW / auditors together.

---

## Current tree hazard (fix first)

The v12 repair aligns the lock, template cache-bust, audit pins, security
baseline and service worker on
`sms-v4.05.166-admin-density-full-fill-v13-2026-07-21`. Any future bump must
update all of them together or `verify_django_admin_preview_parity.py` and the
service-worker monotonicity gate fail.

---

## Key files

### Templates

- `templates/admin/base_site.html` — critical inline CSS + cache bust
- `templates/admin/base.html` — shell root `data-rmc-admin-approval-build`
- `templates/admin/index_superadmin.html` — operator index + chip
- `templates/admin/index_tenant.html` — tenant index + chip + school KPIs
- `templates/admin/change_form.html`, `change_list.html`
- `templates/admin/submit_line.html` — compact Save
- `templates/admin/includes/admin_workspace_tools.html` — page-aware tools
- `templates/components/admin_nav_bridge.html` — tenant topbar escapes / search

### CSS

- `static/css/rmc-admin-approval-surface-v13.css` — sole final layout owner;
  exact desktop grids, native table fill, form/action fill, and the <=1024px
  one-column contract
- `static/css/rmc-admin-django-canvas-contract.css` — terminal seals + approval grids
- `static/css/rmc-admin-workspace-10x.css` — must stay 3-col (never 2-col clamp)
- `static/css/admin-nav-bridge-tenant.css`

### Gates / lock

- `scripts/verify_django_admin_preview_parity.py`
- `scripts/audit_django_admin_canvas_contract.py` (calls preview parity)
- `scripts/audit_django_admin_miss_nothing.py`
- `var/admin-approval-build-lock.json`
- Wired into: `architectural-boundaries.yml`, `pre_push_boundary_check.py`, `scripts/release/render_predeploy.sh`, `verify_render_deploy_readiness.py`, `verify_ci_gate_wiring.py` `REQUIRED_GATES`

---

## How to prove deploy (operator’s test)

1. Deploy the v12 commit with its synchronized lock and service worker.
2. Run migrations, then `collectstatic --noinput` before restarting web workers.
3. Hard refresh / unregister the previous service worker.
4. Open **operator** `/admin/` **and** **tenant** `/admin/` — both must show the chip.
5. View Source: search `2026-07-21-v13` and `preview-parity-v12`.
6. If the chip is missing → **production is not on that commit** (or HTML not rendered). Do not blame CSS first.

---

## v12 repair closeout (2026-07-20)

The previous page was visibly broken for concrete DOM/cascade reasons:

1. `app_index.html` emitted the canvas marker twice, creating a nested approval
   grid and confining the real catalog to the first inner track.
2. Unfold's changelist retained its old internal two-column grid even when the
   filter panel was hidden, so the native table remained left-aligned.
3. Change forms retained the old `fields | save sidebar` grid; large desktop
   padding also consumed too much of a 390px canvas.
4. Older ID-qualified `#cp-main-content` rules beat lower-specificity
   breakpoint rules at exactly 1024px on the tenant app index.
5. The tools strip kept a legacy sticky position after becoming full-width on
   mobile, producing a wide overlay band.
6. The row-detail drawer and back-to-top controls were included by more than
   one shell owner; tenant pages did not own all of the drawer's hide behavior.
7. Production-shaped local checks reused one session across both host scopes,
   allowing tenant state to contaminate operator evidence. Production Secure
   CSRF cookies also prevented the HTTP-local bulk-delete confirmation probe.
8. Auth/MFA checkpoint pages started authenticated shell pollers, leaving
   orphan background requests that contaminated later host runs.

The v12 owner fixes those causes, not just their screenshots. Real-host
evidence under `artifacts/django-admin-canvas-live/` covers operator and tenant
index, app index, native changelist, add/change/history/delete,
delete-selected confirmation, guided school actions, Site Settings,
registries, runtime and specialized templates. Representative routes pass in
light and dark at 1440, 1024, 768 and 390px with HTTP 200, correct scope, one
visible H1, no horizontal overflow, no duplicate/body stylesheet links, no
unexpected fixed overlays, full native tables and working split Save controls.
The specialized dark run reached 11 valid scoped custom-model forms and
recorded seven host/model combinations as expected scope skips.

The real-host verifier now:

- uses separate operator and tenant session cookies;
- treats authentication redirects and background 4xx/5xx resources as failures;
- verifies DOM cardinality, computed tracks, fill ratios, overlays and controls;
- seeds only the correct host-scoped CSRF cookie for the non-destructive
  delete-selected confirmation probe; and
- closes Chromium on thrown errors and hashes overlong Windows artifact names.

---

## Commands

```bash
python scripts/verify_django_admin_preview_parity.py
python scripts/audit_django_admin_canvas_contract.py
python scripts/audit_django_admin_surface_leftovers.py
python scripts/sweep_django_admin_platformwide_layout.py
python scripts/audit_django_admin_miss_nothing.py
python scripts/verify_service_worker_version.py --check-monotonic
node scripts/verify_django_admin_real_host_matrix.mjs --suite core ...
node scripts/verify_django_admin_real_host_matrix.mjs --suite specialized ...
```

---

## Do not

- Claim done from green audits alone.
- Ship CSS-only without a **visible** chip change on **both** hosts.
- Create parallel strategy / roadmap docs; update SOT §11.4 + autonomous log only after a validated ship.
- Touch `backend_*` portal shells for this task.

---

## Success criteria

User opens operator + tenant `/admin/` after deploy and sees:

1. The **v12 chip** (or the next synchronized chip from the lock), and
2. Layout matching approval **After**: full-fill main | ~17–18% rail | 2.35rem tools; no right void; page-aware tools; host-correct identity chrome.

---

## Related Cursor context

Prior Cursor work on this slice lived in the local agent transcript for this repo (admin full-fill / preview parity / approval HTML). Prefer this handoff + the two approval HTML files over re-auditing from scratch.

---

## AGGRESSIVE v13 PROMPT — paste into Codex / Cursor (2026-07-21)

Copy everything below the line into a fresh agent run. Do **not** dilute it.

---

```text
YOU ARE AN UNCOMPROMISING LEAD UI/UX ARCHITECT + DJANGO ADMIN SURFACE ENGINEER.

MISSION (NON-NEGOTIABLE)
Implement the APPROVED design-preview HTML on EVERY Django admin surface for BOTH hosts:
  • Operator: manager…/admin/  (Platform Backoffice)
  • Tenant:   {school}.…/admin/  (school configuration engine)
This is PLATFORM-WIDE. Screenshots of “Change user” are PROOF OF FAILURE CLASS — not the only pages to fix.
Tenant /admin/ must look and feel as premium as operator /admin/. Host chrome differs (identity, CTAs, rail copy) — density, fill, and polish do NOT.

APPROVAL SOURCES OF TRUTH (OPEN FIRST — DO NOT INVENT)
1. var/design-previews/django-admin-page-aware-full-fill-approval-2026-07-19.html
2. var/design-previews/tenant-admin-config-engine-approval-2026-07-19.html
3. docs/HANDOFF_DJANGO_ADMIN_APPROVAL_HTML.md
4. var/admin-approval-build-lock.json  (bump to v13 together with SW + ?v=)

CONTRACT FROM APPROVAL HTML (LOCK THESE)
• Operator .ws = minmax(0,1fr) minmax(9.2rem,17%) 2.35rem
• Tenant   .ws = minmax(0,1fr) minmax(9.5rem,18%) 2.35rem
• Main track FULL-FILL — no right void, no decorative empty column inside main
• Tables: width 100%; table-layout: fixed; no left-aligned skinny table
• TOOLS strip page-aware: index ≠ list ≠ form (no inert Filters / View site / + when surface cannot use them)
• Operator: Platform Backoffice; fleet CTAs on INDEX ONLY
• Tenant: school Config / Feature control / Portal — NEVER Studio / Invite school / Operator boundary chrome
• Forms: Compact Save ▾ (split primary + menu), actions in-flow (not a floating wall)

WHY THE OPERATOR STILL HATES THE LIVE SURFACE (FIX THESE EXACT DEFECTS)
Live Change user / forms still show:
1. LEAKING / BLEEDING — regions collide: left nav bleed into canvas, rail into main, Unfold/Bootstrap leftovers piercing approval owner CSS, sticky overlays, double chrome, nested workspace grids.
2. CRAMPING WHILE SPACE EXISTS — huge vertical dual-list “Available | Chosen” permission/group/role widgets, tall multi-selects, sparse one-column field stacks, oversized left nav density with tiny type.
3. LEFTLY ALIGNED WASTE — labels/inputs cling to the left ~50–60% of the MAIN track; the right half of MAIN is dead air. That is NOT “full-fill.” Full-fill means the MAIN column’s content grid USES the main track width (2-up / auto-fit field rows; wide widgets only when needed).
4. UNNECESSARILY LONG PAGES — filter_horizontal / selector stacks force multi-viewport scrolls when creative condensation would keep the form ≤ ~2–3 folds.
5. PREMIUM GAP — tenant /admin/ must match operator polish (tokens, radii, hairlines, empty states, skeletons, compact Save, page-aware tools). Different identity chrome ≠ cheaper UI.

CREATIVE CONDENSATION (REQUIRED — NOT OPTIONAL POLISH)
Replace or wrap Django’s vertical space hogs with premium patterns that KEEP functionality:
A. PERMISSIONS / GROUPS / ROLES / M2M
   - Default: collapsible “Transfer” accordion sections with numbered headers (1 Permissions · 2 Groups · 3 Roles).
   - Prefer searchable dual-pane that is HEIGHT-CAPPED (e.g. max 12–14 rem lists) + internal scroll — NEVER unbounded page-length growth.
   - Where ModelAdmin allows, offer a compact mode: searchable multi-select / combobox / chip-picker instead of full-height selector (keep Django POST field names intact).
B. FIELD LAYOUT
   - Short scalar fields: 2-column (desktop) / 1-column (≤1024) auto-fit grid spanning FULL main width.
   - Only textarea / selector / related-widget / readonly blocks span full row.
   - Kill leftover max-width caps on .vTextField / Unfold form shells that recenter or left-pin fields.
C. SIDEBAR / NAV
   - Reduce visual cramp: clearer section hierarchy, truncate long labels with title tooltips, no double “ADVANCED” walls; keep scroll inside nav — do not shrink MAIN to feed nav.
D. RAIL
   - Dense but calm: numbered “On this page” anchors, Form pulse compact, no endless empty list items.
E. INDEX / LIST / APP INDEX
   - Catalog cards auto-fit full main; changelist native table 100% fill; no left void beside hidden filter panel.

CASCADE / OWNERSHIP RULES (ALREADY BIT US)
• Sole final layout owner remains the approval surface CSS (bump v12 → v13 file or evolve v12 in place + rename owner attr).
• Beat #cp-main-content / rmc-admin-workspace-10x 2-col clamps — NEVER collapse tools away on desktop.
• No nested [data-rmc-django-workspace] grids (app_index double-marker class of bug).
• Bump lock + cache_bust + SW + template ?v= + chip on BOTH index_superadmin.html AND index_tenant.html TOGETHER.
• Visible proof chip MUST change (e.g. `v13 · density+full-fill · operator+tenant`) so deploy cannot look “unchanged.”

SCOPE (AUDIT THEN IMPLEMENT — PLATFORM WIDE)
Hosts: operator + tenant.
Surfaces (all must pass density + fill + no-bleed):
  index, app_index, changelist, change_form, add, history, delete, delete_selected,
  object tools, inlines, custom admin templates under templates/admin/**,
  school guided delete / waive, Site Settings, registries, runtime defaults,
  specialized model forms on both hosts.
Do NOT “fix only Change user.” Change user is the canary.

AUDIT FIRST (WRITE FINDINGS, THEN CODE)
1. Diff live templates/CSS against BOTH approval HTMLs section-by-section (Before vs After).
2. AST/CSS scan for: max-width caps on form controls, 2-col workspace clamps, nested workspace, sticky tools overlays, filter_horizontal unbounded height, left-pinned Unfold form layouts.
3. List every leftover that causes left-void or page-length bloat; fix by severity.
4. Extend scripts/verify_django_admin_preview_parity.py + miss-nothing / canvas / real-host matrix with DENSITY checks:
   - main content fill ratio (no large empty right half inside MAIN)
   - .selector / .selector-available max-height capped
   - form-rows computed columns ≥ 2 at ≥1280px when ≥4 scalar fields present
   - page fold heuristic: change_form primary modules should not exceed policy without accordion/tabs
5. Run real-host matrix core + specialized on operator AND tenant after implement.

IMPLEMENTATION ORDER
1. Lock → v13 build_id / cache_bust / sw_version / seal
2. CSS owner: full-fill MAIN content grids + kill left-void; height-cap selectors; tighten nav/rail density
3. Templates: accordion/numbered M2M wrappers; compact Save; page-aware tools; tenant vs operator chrome honesty
4. JS (static, CSP-nonce safe): optional enhance search-filter inside capped selectors; no console.log
5. Chip on BOTH indexes
6. Gates green + commit + push
7. Deploy proof instructions: both /admin/ show v13 chip; View Source has new build id; Change user shows 2-up scalars + capped permission transfer (not a mile-long page)

DEFINITION OF DONE (USER-VISIBLE — AUDITS ALONE FAIL)
Operator AND tenant after hard refresh:
  ✓ v13 chip visible on both indexes
  ✓ No right void in MAIN; fields use width intelligently (2-up scalars)
  ✓ Permissions/groups/roles do NOT dominate page length (capped + accordion/numbered)
  ✓ No region bleed; tools page-aware; tables full width
  ✓ Tenant premium parity with operator (different chrome, same craft)
  ✓ python scripts/verify_django_admin_preview_parity.py PASS
  ✓ canvas / miss-nothing / platformwide sweep PASS
  ✓ real-host matrix core (both hosts) PASS for index + changelist + change_form canaries
  ✓ Pushed to main; SW monotonic; lock synchronized

BANNED
• Narrative-only “parity” without chip bump + visual density change
• Fixing only the two screenshot URLs
• CSS-ratio-only without form condensation
• Leaving filter_horizontal full-page-tall “because Django default”
• Parallel strategy docs — record in SOT §11.4 + autonomous log AFTER green ship
• Touching backend_* portal shells for this wave

START NOW: read both approval HTMLs + current rmc-admin-approval-surface-v13.css + change_form.html + submit_line.html + admin_workspace_tools.html, then implement v13 end-to-end.
```

---

### Operator feedback that triggered v13 (2026-07-21)

Screenshots of live Change user still show left-void in MAIN, mile-tall permission dual-lists, cramped nav, and incomplete approval HTML fidelity — despite v12 full-fill grid shipping. v13 is the **density + intelligent fill + condensation** wave on top of the grid contract.
