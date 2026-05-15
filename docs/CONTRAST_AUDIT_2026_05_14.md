# WCAG 2.2 AA Contrast Audit — 2026-05-14

Re-audit of `static/css/design-tokens.css` token pairs against WCAG 2.2 success
criterion 1.4.3 (Contrast — Minimum). Two tokens out of compliance; both patched in
this wave.

## WCAG 2.2 AA contrast floors

- **1.4.3 Normal text:** 4.5:1
- **1.4.3 Large text (≥18pt regular or ≥14pt bold):** 3:1
- **1.4.11 Non-text contrast (UI components, graphical objects):** 3:1

## Ratios checked (light mode, `--surface-canvas ≈ #fbfbfd`)

| Token | Value | Ratio vs canvas | AA verdict |
|---|---|---|---|
| `--text-primary` | `#1d1d1f` | ~16.4:1 | Pass (AAA) |
| `--text-secondary` | `#424245` | ~9.05:1 | Pass (AAA) |
| `--text-tertiary` | `#6e6e73` | ~4.96:1 | Pass (AA) |
| `--text-muted` (was) | `#86868b` | ~3.57:1 | **FAIL normal text**, pass large text |
| `--text-muted` (after fix) | `#6c6c70` | ~5.10:1 | **Pass (AA)** |

## Ratios checked (admin sidebar, `--admin-sidebar-bg = #0f172a`)

| Token | Value | Ratio vs sidebar | AA verdict |
|---|---|---|---|
| `--admin-sidebar-text` | `#f1f5f9` | ~16.7:1 | Pass (AAA) |
| `--admin-sidebar-text-muted` | `#94a3b8` | ~6.65:1 | Pass (AA) — unchanged |
| `--admin-sidebar-heading` | `#e2e8f0` | ~14.4:1 | Pass (AAA) |

## Ratios checked (footer, dark gradient bg)

| Token | Value | Ratio | AA verdict |
|---|---|---|---|
| `--footer-text` | `#e2e8f0` | ~13:1 | Pass (AAA) |
| `--footer-text-muted` | `#64748b` | ~5.5:1 | Pass (AA) — already tightened in earlier pass |

## Header gradient (the hard case)

`--header-brand-bg` is `linear-gradient(135deg, var(--brand-gradient-start), var(--brand-gradient-end))`. Start defaults to indigo `#4f46e5`; end defaults to indigo-deeper `#3730a3`. With a tenant override the end can be any color including emerald (the historical default).

Worst-case test: `--header-brand-fg = #f8fafc` (slate-50) against an emerald-500 (`#10b981`) gradient endpoint **without** overlay:
- Slate-50 L ≈ 0.957; emerald-500 L ≈ 0.394 → ratio ≈ **2.27:1** (fail).

With the 0.25 overlay (75% emerald + 25% slate-900 = effective bg ≈ #157854, L ≈ 0.20):
- ratio ≈ **4.03:1** (still under AA 4.5).

After this wave: overlay tightened to **0.35** (65% emerald + 35% slate-900 ≈ #0e6647, L ≈ 0.146):
- ratio ≈ **(1.007) / (0.196) ≈ 5.14:1** → **Pass (AA).**

The default indigo→indigo gradient was already comfortably above AA; the overlay
bump only affects tenants who configure an emerald (or lighter brand-end) color.

## Dark-mode tokens

| Token | Value | Bg | Ratio | AA |
|---|---|---|---|---|
| `--text-muted` (dark) | `#8e8e93` | `--surface-canvas ≈ #1c1c1e` | ~5.20:1 | Pass |
| `--text-tertiary` (dark) | `#aeaeb2` | `#1c1c1e` | ~7.95:1 | Pass |
| `--text-secondary` (dark) | `#ebebf5` | `#1c1c1e` | ~14.7:1 | Pass AAA |

Dark-mode tokens are clean. No changes.

## Stone-theme tokens (alternate palette block ~line 700) — FIXED 2026-05-14 wave NS-3

| Token | Was | Now | Bg | Ratio | AA |
|---|---|---|---|---|---|
| `--text-muted` (light) | `#a8a29e` (stone-400) | `#6b6660` | `#fafaf9` (stone-50) | 5.04:1 | **AA pass** |
| `--text-tertiary` (light) | `#78716c` (stone-500) | `#57534e` (stone-600) | `#fafaf9` | 7.65:1 | **AA pass** |
| `--text-muted` (dark) | `#78716c` (stone-500) | `#a8a29e` (stone-400) | `#0c0a09` (stone-950) | 5.18:1 | **AA pass** |
| `--text-tertiary` (dark) | `#a8a29e` (stone-400) | `#d6d3d1` (stone-300) | `#0c0a09` | 10.55:1 | **AA pass** |

Stone palette is now WCAG 2.2 AA compliant on every text role in both
light and dark mode. The warm-gray tonal character is preserved — the
shift is one Tailwind step in each direction, which is invisible
adjacent to the brand color but lifts every muted/tertiary chip above
the 4.5:1 threshold.

## Changes shipped this wave

1. `--text-muted` (light): `#86868b` → `#6c6c70`.
2. `--header-brand-overlay`: `rgba(15,23,42,0.25)` → `rgba(15,23,42,0.35)`.

Both edits include inline rationale comments referencing this audit.

## Items NOT shipped (deferred to design-lead review)

- ~~Stone-theme `--text-muted: #a8a29e` (3.04:1)~~ — **CLOSED** in wave NS-3 (see stone-theme table above).
- `--admin-sidebar-active-bg: #1e293b` matching `--admin-sidebar-bg-hover` matches
  `--admin-sidebar-surface` — three tokens collapse to the same value. Not a contrast
  violation but a hierarchy nit; leave for the next aesthetic pass.

## Acceptance evidence

- `static/css/design-tokens.css` lines 51, 161-162 carry post-edit values + comments.
- Compute relative-luminance method used: WCAG formula `((sRGB+0.055)/1.055)^2.4` per channel; luminance = 0.2126*R + 0.7152*G + 0.0722*B.
- Numbers reproducible via `python -c "from wcag_contrast import ratio; …"` or any browser-devtools contrast picker.
