# Global navigation — information architecture (§8.0.4)

**Authority:** Single execution plan [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). **Implementation:** `apps/schools/control_plane_nav.py` (control plane), tenant backend sidebar (`portal_base` / backend), portal role nav.

## 1. Control plane (manager host, `/super/`)

| Group | Purpose |
|-------|---------|
| Platform Overview | Dashboard, Command Center |
| Studio OS | Experience hub (unified operator studio) |
| Schools | List, Setup Studio, curriculum/geography packs, education systems |
| Runtime & governance | Inspector, registries, trust-adjacent tools |
| Workflows / Marketplace / Migration | As registered in `build_control_plane_nav` |

**Rules:** One sidebar; pin favorites; Ctrl+K palette; no duplicate “System config” vs “Settings” — **System config** = bounded console (`console_domains_hub`). Legacy Django admin only where inventory allows.

## 2. Tenant backend (`/accounts/backend-*`, staff)

Primary areas: **Dashboard** (role-home, Workflow Center, quick actions) → **People** → **Finance** → **Academics / Evals / Reports** (by permission) → **Site config** (hubs) → **Studio** (settings-capable roles).

**Rules:** Backend shell matches `portal_base` + backend theme tokens; command palette (BR-02); Setup Studio entry for launch readiness.

## 3. Portal (parent / teacher / student)

Role-specific sidebars only; no mixing parent links on teacher home. **Trust** links on marketing/public, not inside tenant academic flows unless compliance-specific.

## 4. Low-click targets

See [TOP_20_LOW_CLICK_TASKS.md](TOP_20_LOW_CLICK_TASKS.md) and `apps/dashboard/action_registry.py`.

## 5. Tours (BR-13)

| Surface | Mechanism |
|---------|-----------|
| Tenant backend | `tour_steps_api?context=backend_dashboard` + first-login tour |
| Control plane | `context=super_trust` \| `super_migration` \| `super_governed` + **Page tour** button |

**Last aligned:** 2026-03-18 (Phase B/C/E of UI/UX closure plan).
