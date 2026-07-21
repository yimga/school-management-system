# Handoff: Django admin approval HTML → live `/admin/` (operator + tenant)

**Audience:** Codex / next agent  
**Date:** 2026-07-20  
**Status:** Partial ship on `main`; live visual parity with approval HTML still disputed by operator.  
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
v12 · approval canvas · operator+tenant
```

### Lock file

`var/admin-approval-build-lock.json`

| Key | Value (as of handoff write) |
| --- | --- |
| `build_id` | `2026-07-20-v12` |
| `cache_bust` | `20260720-admin-preview-parity-v12` |
| `sw_version` | `sms-v4.05.165-admin-preview-parity-v12-2026-07-20` |

When bumping a wave: edit the **lock first**, then templates / CSS / SW / auditors together.

---

## Current tree hazard (fix first)

The v12 repair aligns the lock, template cache-bust, audit pins, security
baseline and service worker on
`sms-v4.05.165-admin-preview-parity-v12-2026-07-20`. Any future bump must
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

- `static/css/rmc-admin-approval-surface-v12.css` — sole final layout owner;
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
5. View Source: search `2026-07-20-v12` and `preview-parity-v12`.
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
