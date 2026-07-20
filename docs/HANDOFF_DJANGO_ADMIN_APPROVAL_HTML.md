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
v8 · approval canvas · operator+tenant
```

### Lock file

`var/admin-approval-build-lock.json`

| Key | Value (as of handoff write) |
| --- | --- |
| `build_id` | `2026-07-20-v11` |
| `cache_bust` | `20260720-admin-preview-parity-v11` |
| `sw_version` | `sms-v4.05.164-admin-preview-parity-v11-2026-07-20` |

When bumping a wave: edit the **lock first**, then templates / CSS / SW / auditors together.

---

## Current tree hazard (fix first)

As of merge `c59f60d97` (`agent/django-admin-v11-parity` → `main`), lock / SW / auditors are aligned on **v11** / `sms-v4.05.164-admin-preview-parity-v11-2026-07-20`. Offline MC upload remains on main; any future SW bump must update the approval lock + `EXPECTED_SW` pins together or `verify_django_admin_preview_parity.py` fails.

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

1. Deploy a commit that includes `f6e299afb` (or later with lock synced).
2. Hard refresh / unregister service worker.
3. Open **operator** `/admin/` **and** **tenant** `/admin/` — both must show the chip.
4. View Source: search `2026-07-20-v8` and `preview-parity-v8`.
5. If the chip is missing → **production is not on that commit** (or HTML not rendered). Do not blame CSS first.

---

## What is still NOT done (Codex should own)

Gates prove markers/grids exist **in the repo**. They do **not** prove live pixels match the approval mock.

Likely remaining gaps:

1. Confirm production HTML actually has the v8 chip (deploy / SW / `collectstatic`).
2. Changelist / form may still look like “Before” if Unfold or other CSS wins — compare DevTools computed `grid-template-columns` on `[data-rmc-django-workspace]`.
3. Tenant catalog storytelling vs approval domain cards (People / Academics / Finance / Brand) may still be a raw model dump.
4. Operator topbar / search / escapes may still not match operator approval “After” chrome.
5. Compact Save ▾ visual weight vs approval mock.
6. If chip is present but layout still wrong → **specificity / DOM structure**, not deploy.

---

## Commands

```bash
python scripts/verify_django_admin_preview_parity.py
python scripts/audit_django_admin_canvas_contract.py
python scripts/audit_django_admin_miss_nothing.py
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

1. The **v8 chip** (or the next bumped chip from the lock), and  
2. Layout matching approval **After**: full-fill main | ~17–18% rail | 2.35rem tools; no right void; page-aware tools; host-correct identity chrome.

---

## Related Cursor context

Prior Cursor work on this slice lived in the local agent transcript for this repo (admin full-fill / preview parity / approval HTML). Prefer this handoff + the two approval HTML files over re-auditing from scratch.
