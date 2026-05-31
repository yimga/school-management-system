# lux-workspace

Apple-grade luxury UI surface for the multi-tenant Global School Management OS.
Implements the four-pillar mandate (cursor-face shortcuts, expected
clickability, distinct spatial personalities, cubic-bezier progressive
disclosure) plus drift defense, offline-first hardening, and full
keyboard-first navigation.

## Architecture

```
PremiumUIOrchestratorProvider (context)
├── CustomKeyboardShortcutBus    (global Cmd+K + tier-local hotkeys)
├── PremiumWorkspaceOrchestrator (rail + main canvas)
│   └── ActiveTierCanvas         (tier-specific content)
├── GlobalCommandConsole         (Cmd+K palette)
├── KeyboardHelpOverlay          (Cmd+/ shortcuts cheat sheet)
├── NetworkStatusChannel         (offline/reconnecting banner)
├── PerformanceHud               (dev-only FPS HUD)
└── LuxErrorBoundary             (crash isolation, retries gracefully)
```

## Tiers

Three workspace tiers with distinct spatial personalities, defined as the
SOT in `registry.json`:

| Tier              | Spatial structure       | Accent  | Hotkeys                |
|-------------------|-------------------------|---------|------------------------|
| FINANCIAL_LEDGER  | Monolithic split-pane   | emerald | `I` `R` `B`            |
| ACADEMIC_MATRIX   | Dense fluid grid        | azure   | `S` `C` `P`            |
| OPERATOR_SHELL    | Collapsible tree        | indigo  | `L` `F` `T`            |

Global hotkeys: `⌘K` (command console), `⌘/` (keyboard help), `Esc`
(close top overlay).

## Quick start (React)

```tsx
import {
  CustomKeyboardShortcutBus,
  GlobalCommandConsole,
  KeyboardHelpOverlay,
  LuxErrorBoundary,
  NetworkStatusChannel,
  PerformanceHud,
  PremiumUIOrchestratorProvider,
  PremiumWorkspaceOrchestrator,
} from "@/lib/luxWorkspace";

function App() {
  return (
    <LuxErrorBoundary>
      <PremiumUIOrchestratorProvider initialTier="FINANCIAL_LEDGER">
        <CustomKeyboardShortcutBus />
        <PremiumWorkspaceOrchestrator>
          {/* your tier-aware content */}
        </PremiumWorkspaceOrchestrator>
        <GlobalCommandConsole />
        <KeyboardHelpOverlay />
        <NetworkStatusChannel />
        <PerformanceHud enabled={import.meta.env.DEV} />
      </PremiumUIOrchestratorProvider>
    </LuxErrorBoundary>
  );
}
```

## Django mount

The mount script (`src/apps/luxWorkspace/mount.tsx`) scans for
`[data-rmc-lux-workspace]` nodes and hydrates them.  The template
`templates/lux_workspace/demo.html` wires the data attrs:

- `data-initial-tier` — `FINANCIAL_LEDGER | ACADEMIC_MATRIX | OPERATOR_SHELL`
- `data-students` — JSON array of student seed objects
- `data-simulate-async-ms` — ms to keep `SkeletalShell` on screen for demo
- `data-show-perf-hud="1"` — show the dev-only FPS HUD

Localized labels are injected via a `<script type="application/json"
data-rmc-lux-i18n>` tag rendered by `apps.portal.lux_workspace_i18n`.

## Hooks

| Hook                       | Purpose                                                       |
|----------------------------|---------------------------------------------------------------|
| `useWorkspaceKernel()`     | Active tier, overlay stack, action dispatch, console toggle   |
| `useFocusTrap({active,ref})` | Keyboard-trap focus within a modal / sheet                   |
| `usePerformanceMonitor()`  | rAF FPS + long-task tracking; powers `PerformanceHud`         |

## Persistence

`sheetDraftPersistence` provides `saveSheetDraft / loadSheetDraft /
clearSheetDraft` backed by IndexedDB (falls back to localStorage when
IDB is absent — Safari private mode, jsdom, etc.). Used by
`PremiumStudentActionCard` to auto-save in-flight notes; survives
tab close + network loss.

## Drift defense

`validateLuxRegistry()` runs at mount-time and:

- Asserts the spring curve matches the mandate (`cubic-bezier(0.16, 1, 0.3, 1)`)
- Asserts `min_touch_target_px >= 48` (WCAG 2.5.5 + Apple HIG)
- Asserts each tier has all 7 theme keys + a unique `css_var_token`
- Asserts no two tiers share `base_background` / `accent_border_glow` /
  `css_var_token` (visual-uniformity ban)
- Asserts each tier hotkey is `[a-z0-9?/]` and each action is SCREAMING_SNAKE
- Returns `{ ok, errors[], warnings[] }`

If `ok === false`, mounting halts and errors print to the console.

Mirror check in Python at `scripts/verify_lux_workspace_ui.py` —
runs in CI to catch the same drift before deploy.

## Performance

All animations use `transform` + `opacity` only — no layout-triggering
properties.  Honors `prefers-reduced-motion` (strips transitions
+ keeps hover strips visible).  Touch targets enforce
`>= var(--lux-min-touch-target, 48px)` on `pointer: coarse`.

## Building

```bash
npm run test:lux       # vitest, 8+ suites
npm run build:lux      # vite IIFE bundle -> static/js/dist/lux-workspace.mount.js
npm run verify:lux     # build + test + python verifier
python scripts/smoke_lux_workspace_demo.py   # wire-up smoke
```

## File map

```
src/lib/luxWorkspace/
├── registry.json                       # SOT — TS imports + Python reads
├── types.ts                            # typed registry accessors
├── registrySchema.ts                   # validateLuxRegistry() drift gate
├── WorkspaceKernel.tsx                 # context + provider
├── CustomKeyboardShortcutBus.tsx       # window keydown listener
├── PremiumInteractiveContainer.tsx     # expected-clickability wrapper
├── PremiumStudentActionCard.tsx        # spec demo card + glass sheet
├── PremiumWorkspaceOrchestrator.tsx    # rail + main canvas
├── GlobalCommandConsole.tsx            # Cmd+K palette
├── KeyboardHelpOverlay.tsx             # Cmd+/ shortcut cheat sheet
├── SkeletalShell.tsx                   # layout-shift mitigation
├── LuxErrorBoundary.tsx                # crash isolation + retry
├── NetworkStatusChannel.tsx            # offline/reconnecting banner
├── usePerformanceMonitor.ts            # rAF FPS + long-task probe
├── PerformanceHud.tsx                  # dev-only FPS HUD chip
├── useFocusTrap.ts                     # a11y focus trap utility
├── sheetDraftPersistence.ts            # IDB + localStorage fallback
├── index.ts                            # barrel
└── __tests__/*.test.tsx                # vitest coverage

apps/portal/
├── lux_workspace_i18n.py               # gettext_lazy labels + payload helper
└── views_lux_workspace.py              # /portal/lux-workspace/ demo view

templates/lux_workspace/demo.html       # Django mount surface
static/css/lux-workspace.css            # BEM rmc-lux-* visual layer
vite.lux.config.ts                      # isolated IIFE bundle config
scripts/verify_lux_workspace_ui.py      # CI drift gate (Python)
scripts/smoke_lux_workspace_demo.py     # no-DB wire-up smoke
```
