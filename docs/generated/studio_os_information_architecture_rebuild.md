# Studio OS — Information Architecture Rebuild (v3.54.0)

**Generated:** 2026-05-21. The IA as it stands after the v3.54.0 wave.

## Global navigation

- **Rail order:** Overview · Experience · Automation · Outputs · Launch · Control
- **Rail template:** [`shell.html` lines 71-79](../../templates/studio_os/shell.html)
- **Command palette:** `Ctrl+K` (33 actions per v3.53.0 registry)
- **Skip-link target:** `#studio-canvas` (preserved at shell.html:25)
- **Host indicator:** operator-only when `request.public_host_kind == 'manager'`

## Per-section IA

### Overview

| Field | Value |
|---|---|
| Purpose | Studio OS home — what needs attention, what is ready, what changed, what is blocked |
| Primary action | Open next-best-action (mission hero CTA) |
| Secondary action | Open any of the 5 mode cards |
| Next best action | `studio_recommendations[0]` |
| Preview action | Live previews triptych card |
| Blocker indicator | `overview_signals['open_blockers']` (honest unknown placeholder if `None`) |
| Help | Studio guidance panel |
| Operator-only | RBAC chip, Feature control chip |
| Tenant-safe | All 5 mode openers, approval/workflow/import/library hub chips for own tenant |

### Experience

| Field | Value |
|---|---|
| Purpose | Visual experience control room — design + tenant-safe live preview + theme state |
| Primary action | Theme & colors |
| Secondary action | Customizer overview |
| Next best action | Compare or AI recommendations |
| Preview action | `experience_live_preview_pane.html` — iframe + role selector + state badges |
| Blocker indicator | `theme_contrast_report` status pill |
| Help | Studio guidance panel + Customizer CTA |
| Operator-only | Platform template management, cross-tenant Compare |
| Tenant-safe | Theme tokens (draft), publish own, preview as role |

### Automation

| Field | Value |
|---|---|
| Purpose | Workflow simulation cockpit — trigger/action map + sim preview + approval + rollback |
| Primary action | Open Workflow center |
| Secondary action | Open Approval hub |
| Next best action | Run simulation on a draft workflow |
| Preview action | `automation_simulation_preview_pane.html` |
| Blocker indicator | `failing_count` + `paused_count` (v3.54.0 health extension) |
| Help | Flow gallery CTA in right-rail |
| Operator-only | Platform template publish, cross-tenant approval |
| Tenant-safe | Draft workflow, simulate, request activation |

### Outputs

| Field | Value |
|---|---|
| Purpose | Output readiness center — preview + publish readiness + version state + missing-data warnings |
| Primary action | Open Document library |
| Secondary action | Open Report card builder |
| Next best action | Resolve missing-data warnings on packs with missing deps |
| Preview action | `output_readiness_preview_pane.html` — per-pack state badges + service-state indicator |
| Blocker indicator | `packs_missing_deps` from `get_output_readiness_summary` |
| Help | Branding inheritance chain |
| Operator-only | Platform template publish, cross-tenant export |
| Tenant-safe | Draft report/document, publish own, export own |

### Launch

| Field | Value |
|---|---|
| Purpose | Launch readiness command center — checklist + timeline + blockers + approvals |
| Primary action | Preview infrastructure |
| Secondary action | Validate (dry-run) |
| Next best action | Request platform apply (operator-gated + `data-rmc-confirm`) |
| Preview action | `launch_readiness_preview_pane.html` |
| Blocker indicator | Active blockers via `launch_readiness_summary` (timeline backend deferred) |
| Help | Guided onboarding CTA |
| Operator-only | Infrastructure apply, plan management |
| Tenant-safe | Infrastructure preview, validate, role preview, request apply |

### Control

| Field | Value |
|---|---|
| Purpose | Governance cockpit — audit + rollback + dependencies + permissions + feature flags bridge + risk |
| Primary action | View audit summary |
| Secondary action | Open Feature control (external bridge) |
| Next best action | Review impact before rollback |
| Preview action | `control_governance_preview_pane.html` |
| Blocker indicator | Risk state tiles (backend deferred) |
| Help | Why-enabled summary + impact analysis |
| Operator-only | Rollback, AI cleanup, system config, cross-tenant feature flags |
| Tenant-safe | View audit (own school), impact analysis |

## No dead ends

Every section has a primary action resolving to a real route or an honest empty state.

**Pre-existing v3.53 button-as-link** (`cockpit_copilot_rail.html` server-rendered fallback anchor) was converted to `<button type="button">` in the v3.54.0 closeout pass — **zero NEW `href="#"` in any v3.54.0 partial**.

## Right-rail branch cascade (shell.html)

| Branch | Lines | Surfaces |
|---|---|---|
| `current_mode == 'experience'` | ~152-183 | Token properties · Contrast pill · Version history · Audit · Customizer CTA |
| `current_mode == 'launch'` (upper) | ~184-201 | Role preview · Launch confidence · Ready badge |
| `current_mode == 'automation'` | ~202-208 | Simulation summary · Flow gallery CTA |
| `current_mode == 'output'` | ~209-214 | Style & branding · Document library + Report card builder CTAs |
| `current_mode == 'control'` | ~217-243 | Impact · Why-enabled · Audit list (PII-safe `actor_display`) · Full audit CTA |
| `not current_mode` (**NEW v3.54.0**) | ~244-265 | Studio readiness mirror · Next best action CTA |
| `else` fallback | ~266-268 | Generic copy |

The **dead-code duplicate** `{% elif current_mode == 'launch' %}` (was at line 215) was removed in v3.54.0.
