# Marketing AI-Media Generation Pipeline (2026-05-14)

A pipeline and brief library for producing the marketing surface's hero videos,
illustration sequences, and product walkthroughs. Claude Code cannot invoke
Runway, Sora, Veo, or Midjourney — but it *can* (and now does) carry the
canonical briefs, prompts, storyboard structure, and integration scaffolding
so a creative director (or an external partner) can render the assets and
drop them into `static/marketing/img/` and `static/marketing/video/`.

The cream + editorial + Source Serif 4 marketing aesthetic is the visual
direction (per `feedback_marketing_differentiation.md` memory entry; a
standalone marketing-editorial-direction doc is not yet on disk — the
memory entry is the SOT until one is written). The asset library below
follows that.

---

## 1. Asset matrix (what we need)

Each row is one tracked asset, one filename, and one brief.

### 1.1 Hero films (above-the-fold video)

| Slot | Filename target | Duration | Aspect | Source pipeline |
|---|---|---|---|---|
| `/` (home) | `static/marketing/video/hero-home.mp4` | 8s loop | 16:9 + 1:1 mobile | Sora / Veo / Runway Gen-3 |
| `/platform` | `static/marketing/video/hero-platform.mp4` | 10s loop | 16:9 | Sora / Veo |
| `/migration-cloud` | `static/marketing/video/hero-migration.mp4` | 6s loop | 16:9 + 9:16 mobile | Runway Gen-3 |
| `/north-star` | `static/marketing/video/hero-northstar.mp4` | 12s loop | 16:9 | Sora |

### 1.2 Product walkthroughs (3-5 minute explainer videos)

| Slot | Filename target | Duration | Source pipeline |
|---|---|---|---|
| Platform overview | `static/marketing/video/walkthrough-platform.mp4` | 4 min | Synthesia or filmed + Descript |
| Migration Cloud demo | `static/marketing/video/walkthrough-migration.mp4` | 3 min | Loom or Descript |
| Onboarding 0-to-launch | `static/marketing/video/walkthrough-onboarding.mp4` | 5 min | Filmed |

### 1.3 Illustrations (replace placeholder SVGs)

The current `static/images/marketing/` directory ships placeholder SVGs. Real
versions to render:

| Asset | Filename | Style |
|---|---|---|
| Hero global OS composite | `hero-global-os.png` (replaces SVG) | Cinematic, editorial, cream + terracotta + ink |
| Health-score visual | `health-score-render.png` | Editorial chart, no Bootstrap aesthetic |
| Control plane diagram | `control-plane-diagram.png` | Marker on cream, hand-drawn-feel |
| Global map | `global-map-render.png` | Sober, line-art continents, brand pins |
| Workflow illustration | `illustration-workflow-render.png` | Multi-figure narrative, light shadows |
| Student panel | `illustration-students-render.png` | Diverse, age-appropriate |
| Ecosystem diagram | `ecosystem-diagram-render.png` | Editorial wheel, partner logos masked |

### 1.4 Audio (optional, walkthrough soundbeds)

| Slot | Source | Notes |
|---|---|---|
| Walkthrough music bed | Suno / Soundraw | Editorial, restrained, no club-house |
| VO | ElevenLabs / Murf | Consistent voice across 8 walkthroughs |

---

## 2. Generation briefs (drop into the chosen tool verbatim)

### 2.1 Sora / Veo — `hero-home.mp4`

**Prompt (English):**

> Editorial film shot, 8 seconds, looping seamlessly. A modern educator's
> desk on a cream linen surface, late-afternoon light. A laptop opens to a
> dashboard that resembles a serious enterprise SaaS — restrained typography,
> indigo and emerald accents, no Bootstrap aesthetic. The camera does a slow
> 3-degree dolly forward. A second screen shows a school's logo (no real
> brand). A faint chart line animates upward. A teacher's hand reaches for a
> coffee cup. Cinema look — Source Serif 4 lower-third title appears that
> reads "Education Operating System." Color palette: cream `#FAF7F2`,
> terracotta `#C2410C`, ink `#1B1A19`, paper-white `#FFFFFF`. No people's
> faces visible, no logos other than a generic mark. Style references:
> Linear product film, Vercel "Frontend Cloud" launch trailer, Stripe Apps
> announce film. No flashy transitions, no kinetic typography. Calm.

**Negative prompt:** Bootstrap UI, neon, Y2K, futuristic chrome, glitchy
text, real human faces, real corporate logos.

**Aspect ratio:** 16:9 primary, 1:1 crop for mobile (`hero-home-square.mp4`).

**Output naming:** `static/marketing/video/hero-home.mp4` (16:9) +
`static/marketing/video/hero-home-square.mp4` (1:1).

### 2.2 Sora / Veo — `hero-platform.mp4`

**Prompt:**

> 10-second editorial loop. A glass desk in a modern administrative office.
> Multiple monitors visible from a slight overhead angle. Each monitor
> displays a different part of the same SaaS platform — admissions wizard,
> attendance grid, finance dashboard, communications inbox, AI assistant
> panel. The screens animate softly in sync, suggesting a single operating
> system. Camera does a slow lateral truck right. Cream + indigo + emerald
> brand palette in the screen content. Editorial restraint, no kinetic ads
> aesthetic. Source Serif 4 for any text. Style references: Linear's
> "What's new" page film, Vercel Conf 2024 keynote walk-in loop, Apple's
> Vision Pro intro film.

**Aspect:** 16:9.

### 2.3 Runway Gen-3 — `hero-migration.mp4`

**Prompt:**

> 6-second editorial loop. A workshop bench — papers, a worn ledger, a
> floppy disk, a modern laptop. The papers and floppy fade to soft cream
> dust; data points stream out, line-art style, into the laptop screen.
> The laptop shows a clean platform import wizard with a progress bar
> reaching 100%. Color palette cream + indigo + a single emerald accent.
> Tactile, hand-shot, no CGI sheen. Style: Apple "Macintosh introduction"
> documentary, Field Notes brand films.

**Aspect:** 16:9 + 9:16 mobile cut (`hero-migration-vertical.mp4`).

### 2.4 Sora — `hero-northstar.mp4`

**Prompt:**

> 12-second editorial loop. Night sky transitioning to dawn over an empty
> globe. A single bright star above the horizon. The horizon slowly fills
> with line-drawn schoolhouses across multiple continents — Africa, South
> America, Europe, Asia, North America, Oceania. Each schoolhouse lights up
> in cream-warm light. Camera ascends slowly. The single star above
> becomes a stylized "R" mark — the platform identity. No corporate logos
> in the schoolhouse renders. Style references: National Geographic
> opening titles, IBM's "Smarter Planet" film, Apple's "Welcome Home" 2018
> film.

**Aspect:** 16:9.

### 2.5 Midjourney v6 — illustrations

**`hero-global-os.png`:**

> /imagine A cream linen editorial composition: a stylized world globe at
> the center, line art with pin markers across continents. Around the
> globe: floating panes representing dashboard cards (attendance, grades,
> finance, communications) — editorial serif headings, calm geometric
> charts. Color palette: cream `#FAF7F2`, terracotta `#C2410C`, ink
> `#1B1A19`, paper-white. Style references: Tom Sachs collage, The New
> York Times editorial illustration, Wes Anderson framing. --ar 16:9 --v 6
> --style raw --stylize 50

**`health-score-render.png`:**

> /imagine Editorial line-art chart: a single ascending trend line on
> cream paper, faint dotted gridlines, a hand-drawn annotation arrow
> reading "47 → 72" in restrained handwriting. Margin notes in Source
> Serif 4. Color: terracotta line on cream. Style: Field Notes, McSweeney's
> editorial. --ar 4:3 --v 6 --style raw

**`global-map-render.png`:**

> /imagine An ink-line world map on cream paper, hand-drawn feel, no
> textures, no shading. Small pin markers across schools in 6 continents,
> each pin a soft indigo dot. Margin label "RunMyCampus tenants worldwide"
> in Source Serif 4. Style: National Geographic, Field Notes. --ar 16:9 --v 6

**Illustration set rules:**

- All renders pass through one color-pass to match the cream palette exactly.
- No human faces with identifiable features.
- No real corporate logos.
- All deliverables under 350 KB after compression (mozjpeg + svgo).

---

## 3. Pipeline scaffolding (committed to the repo)

### 3.1 Asset manifest

A manifest declares the canonical filename, source brief, status, and contributor
for each asset. Lives at `static/marketing/_manifest.json`:

```json
{
  "version": "2026-05-14",
  "assets": [
    {
      "slot": "hero_home",
      "kind": "video",
      "expected_path": "static/marketing/video/hero-home.mp4",
      "expected_aspect": "16:9",
      "expected_duration_s": 8,
      "status": "PLACEHOLDER",
      "brief_ref": "docs/AI_MEDIA_GENERATION_PIPELINE_2026_05_14.md#21-sora--veo--hero-homemp4"
    },
    {
      "slot": "hero_global_os",
      "kind": "image",
      "expected_path": "static/marketing/img/hero-global-os.png",
      "status": "PLACEHOLDER_SVG",
      "brief_ref": "docs/AI_MEDIA_GENERATION_PIPELINE_2026_05_14.md#25-midjourney-v6--illustrations"
    }
  ]
}
```

### 3.2 Template includes

Marketing templates already load `{% static 'marketing/img/...' %}`. When the
real asset replaces the placeholder, the template doesn't change. To make the
swap explicit, add an opt-in `{% include 'partials/marketing_media.html' %}`
that falls back from `.mp4` → `.svg` placeholder so a missing video doesn't
break the page.

### 3.3 CI check

Add a Python check that walks `_manifest.json` and warns if any `status: SHIPPED`
file is missing from disk, or if a `status: PLACEHOLDER` file is still in
production at release time:

```bash
python scripts/check_marketing_assets.py
```

(Script shipped in wave NS-1; smoke output: 14 placeholders, 0 missing, 0 captionless.)

### 3.4 Approval workflow

1. Creative director picks a vendor (Sora / Veo / Runway) per asset.
2. Renders the asset using the brief in this doc.
3. Drops the output into `static/marketing/{img,video}/` matching the manifest path.
4. Updates `_manifest.json` `status` to `SHIPPED` + `contributor` + `rendered_at`.
5. PR includes a 30s diff video (asset diff) for review.

---

## 4. Open creative-director decisions

These belong to a human, not to Claude Code:

- Vendor selection per slot (Sora vs Veo vs Runway — pricing + queue time + brand fit).
- Music licensing (Suno commercial license vs custom score).
- Voice actor selection for VO (or full ElevenLabs route + which voice).
- Final color-match pass against the editorial palette.
- Accessibility captions for every video (mandatory; auto-caption via Descript first pass, human review second).

---

## 5. Acceptance criteria for "marketing AI media is shipped"

- [ ] Every asset in `_manifest.json` has `status: SHIPPED` and the file exists.
- [ ] Every video has a `.vtt` caption sidecar in `static/marketing/captions/`.
- [ ] Lighthouse performance score on `/`, `/platform`, `/migration-cloud`,
      `/north-star` remains ≥90 (verify after each video swap).
- [ ] CSP allows the chosen video source (CDN host, if any).
- [ ] CI manifest check passes.
- [ ] All originals (uncompressed) archived in `_originals/` or external storage
      (not committed; Git LFS or S3) — keep repo size bounded.

---

This pipeline is intentionally non-blocking: the platform ships with editorial
SVG placeholders today; the real assets land asynchronously as the creative
director runs the briefs. No code change required to swap.
