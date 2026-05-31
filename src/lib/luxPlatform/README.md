# lux-platform

Sibling to `luxWorkspace` — the shared luxury layer that every operator +
tenant + future-tenant surface inherits from. Solves three platform-wide
ailments at once:

1. **Long pages with no end in sight** — `SectionTOC` + `ScrollProgressBar`
   give every long surface a sticky on-this-page nav with progress.
2. **Every dashboard KPI looks the same** — `KpiCard` + 6 distinct viz
   primitives (Sparkline, Donut, Gauge, BarStack, HeatStrip, DeltaChip)
   make varied visualizations one prop away.
3. **Boring 4-up rectangles everywhere** — `BentoGrid`, `SplitPane`,
   `RhythmStack`, `TileBoard` give every page a way to break the
   uniform grid into something with intentional weight + rhythm.

## Components

### Long-page hardening

```tsx
import { SectionTOC, ScrollProgressBar } from "@/lib/luxPlatform";

export default function SettingsPage() {
  return (
    <>
      <ScrollProgressBar />
      <div className="rmc-lux-split rmc-lux-split--narrow">
        <SectionTOC autoDiscover />
        <main>
          <section id="general" data-rmc-toc>...</section>
          <section id="security" data-rmc-toc>...</section>
          <section id="billing" data-rmc-toc>...</section>
        </main>
      </div>
    </>
  );
}
```

`SectionTOC` auto-discovers any `<section id="…" data-rmc-toc>` in the
DOM, builds the nav, observes scroll position via `IntersectionObserver`,
highlights the active section, and shows scroll progress as a vertical
fill bar.  Or pass explicit `sections={[{id, label, depth}]}` to skip
auto-discovery.

`ScrollProgressBar` is a 2px gradient bar that pins to the top of the
viewport and fills as you scroll — useful for long marketing pages or
operator wizards.

### Varied KPI visualizations

```tsx
import {
  BarStack, DeltaChip, Donut, Gauge, HeatStrip, KpiCard, Sparkline,
} from "@/lib/luxPlatform";

<KpiCard
  label="MRR"
  value="$48.2k"
  delta={<DeltaChip pct={12.4} />}
  viz={<Sparkline values={[40, 42, 45, 41, 48]} tone="good" />}
  hint="Tracking 14% above plan."
  href="/finance/recurring/"
/>

<KpiCard
  label="Attendance today"
  value="92%"
  viz={<Donut value={92} tone="good" />}
/>

<KpiCard
  label="SLA"
  value="38m"
  viz={<Gauge value={38} max={60} tone="warn" />}
/>

<KpiCard
  label="Subjects by pass rate"
  viz={<BarStack bars={[
    { label: "Math", value: 78, tone: "warn" },
    { label: "Eng",  value: 91, tone: "good" },
    { label: "Sci",  value: 85, tone: "good" },
  ]} />}
/>

<KpiCard
  label="Attendance heat (14d)"
  viz={<HeatStrip cells={[6, 8, 7, 9, 5, 4, 8, 9, 8, 6, 7, 9, 8, 9]} tone="good" />}
/>
```

Every primitive accepts the same `tone: "neutral" | "good" | "warn" |
"danger"` so a dashboard can mix five different viz shapes and the
palette still reads as one design system.

### Layout balance

```tsx
import { BentoGrid, BentoTile, SplitPane, RhythmStack, TileBoard } from "@/lib/luxPlatform";

<BentoGrid>
  <BentoTile col={4} row={2} hero accent="emerald">{/* big hero */}</BentoTile>
  <BentoTile col={2}>{/* side */}</BentoTile>
  <BentoTile col={2}>{/* side */}</BentoTile>
  <BentoTile col={3} accent="azure">{/* half */}</BentoTile>
  <BentoTile col={3} accent="indigo">{/* half */}</BentoTile>
</BentoGrid>

<SplitPane
  leftWidth="narrow"
  stickyLeft
  left={<SectionTOC autoDiscover />}
  right={<MainContent />}
/>

<RhythmStack>
  <AnchorSection />     {/* row 0 — anchor density */}
  <DetailPanel />       {/* row 1 — detail density */}
  <BreathRow />         {/* row 2 — breath, dashed border */}
  <AnchorSection />     {/* row 3 — anchor again */}
</RhythmStack>

<TileBoard cols={3}>
  {features.map(f => <KpiCard key={f.id} {...f} />)}
</TileBoard>
```

`BentoGrid` is a 6-col responsive grid that collapses to 2-col on
narrow viewports.  `SplitPane` is monolithic two-column with optional
sticky-left.  `RhythmStack` alternates row density anchor → detail →
breath → anchor → detail → breath — so long pages get visual rhythm
instead of one infinite uniform stream.  `TileBoard` is the simple
balanced n-up cluster for when you just want 3 cards in a row.

## Django / vanilla integration

Every component renders BEM classes (`rmc-lux-*`) that pure Django
templates can use directly without React.  Drop the existing CSS
class on any `<section>`, `<aside>`, or `<div>` and it inherits the
visual language.

```html
{# Pure Django: no JS needed #}
<div class="rmc-lux-bento">
  <article class="rmc-lux-bento__tile rmc-lux-bento__tile--col-4 rmc-lux-bento__tile--row-2 is-hero">
    Hero content
  </article>
  <article class="rmc-lux-bento__tile rmc-lux-bento__tile--col-2 rmc-lux-bento__tile--emerald">
    Side tile w/ emerald accent
  </article>
</div>

<div class="rmc-lux-rhythm">
  <div class="rmc-lux-rhythm__row rmc-lux-rhythm__row--anchor">{# anchor #}</div>
  <div class="rmc-lux-rhythm__row rmc-lux-rhythm__row--detail">{# detail #}</div>
  <div class="rmc-lux-rhythm__row rmc-lux-rhythm__row--breath">{# breath #}</div>
</div>
```

Include the CSS once in your base template:

```html
<link rel="stylesheet" href="{% static 'css/lux-platform.css' %}">
```

CSS variables inherit from `lux-workspace.css` — install that too if
you want the full token system.

## Tokens

The visual layer reuses the lux-workspace token vocabulary so the two
packages share one design system:

| Token                   | Purpose                                       |
|-------------------------|-----------------------------------------------|
| `--lux-tier-accent`     | Per-tier accent color (set by workspace)     |
| `--lux-canvas-elev`     | Surface elevation 1 (cards, tiles)            |
| `--lux-canvas-deep`     | Surface elevation 0 (page background)         |
| `--lux-border-thin`     | Subtle hairlines                              |
| `--lux-spring-curve`    | `cubic-bezier(0.16, 1, 0.3, 1)` from mandate |
| `--lux-radius`          | Card / tile corner radius                     |
| `--lux-accent-*-soft`   | Translucent accent backgrounds (good/warn/danger/azure/emerald/indigo/amber/rose) |

## Drift gate

`scripts/verify_platform_ux_invariants.py` scans every template under
`templates/` and flags:

- Long pages without on-this-page nav (`SectionTOC` would fix)
- Modals missing `role="dialog"` or `role="alertdialog"`
- Modals missing `aria-modal="true"`
- Divs / spans used as buttons (keyboard inaccessible)
- KPI uniformity (when ≥6 KPI cards share identical class signatures)
- Missing skip-to-main-content links
- Very-small fixed-size tap targets

Run it pre-commit:

```bash
python scripts/verify_platform_ux_invariants.py --strict --severity error
```

Markdown findings report goes to stdout, exit code is 1 if `--strict`
and ERROR-class findings exist.

## File map

```
src/lib/luxPlatform/
├── SectionTOC.tsx           # sticky on-this-page TOC + scroll progress
├── KpiVariety.tsx           # Sparkline / Donut / Gauge / BarStack / HeatStrip / DeltaChip / KpiCard
├── BentoGrid.tsx            # BentoGrid / BentoTile / SplitPane / RhythmStack / TileBoard
├── index.ts                 # barrel
├── README.md                # this file
└── __tests__/luxPlatform.test.tsx   # vitest coverage

static/css/lux-platform.css                   # BEM rmc-lux-* visual layer
scripts/verify_platform_ux_invariants.py      # drift gate
```
