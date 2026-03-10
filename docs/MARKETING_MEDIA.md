# Marketing media: diagrams, video, and data visualizations

This document describes where diagrams, videos, and data visualizations appear on the RunMyCampus marketing site and how to update them.

## Required visual set

Per [RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md](RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md), the following are **required** (no optional or backlog): hero visual/video, product mockups (admin, teacher, parent, student), platform architecture diagram, migration cloud diagram, marketplace visuals, School-in-a-Box / onboarding wizard mockup, global education network visual, hero motion loop, and Batch 2/3 motion assets (migration explainer, onboarding journey, workflow simulation, global network). All four strategic diagrams (Platform Visual Architecture, Ecosystem Map, School-in-a-Box Launch Flow, Data Intelligence Loop) are required with final art placed on specified pages. See the Visual Asset doc for context keys and page map.

## Diagrams

### Platform diagram (simplified marketing)

- **Asset:** `static/images/marketing/platform-diagram-marketing.svg`
- **Pages:** `/education-operating-system/`, `/platform/`
- **Context:** `MARKETING_PAGE_EXTRAS["education-operating-system"]` and `MARKETING_PAGE_EXTRAS["platform"]` include `diagram_path: "images/marketing/platform-diagram-marketing.svg"`.
- **Template:** `templates/schools/marketing_page.html` renders an `<img>` when `page_extras.diagram_path` is set.
- **How to update:** Edit the SVG file, or replace it and keep the same path. To use a different diagram on a page, set `diagram_path` in the corresponding entry in `MARKETING_PAGE_EXTRAS` in `apps/schools/marketing_views.py`.

### Source

The diagram is derived from the “simplified marketing version” in `RunMyCampus_Platform_Visual_Architecture.md` (six pillars: Education OS, Control Plane, Marketplace, Tenant Runtime, Migration Cloud, Analytics & Integrations). To regenerate or redesign, use the architecture doc as the spec; the SVG can be produced by hand, with a diagram tool (Figma, draw.io), or from a code-based generator (e.g. Mermaid, D3).

---

## Video

### Hero / platform overview video

- **Where:** Homepage (`templates/schools/marketing_landing.html`). The hero block shows a video when `hero_video_url` is set.
- **Settings (Django):**
  - `MARKETING_HERO_VIDEO_URL`: full URL to the video file (e.g. MP4 on CDN or static).
  - `MARKETING_HERO_VIDEO_POSTER_URL`: poster image URL; if unset, the view falls back to a dashboard image URL.
- **Context:** Set in `_marketing_context()` in `apps/schools/marketing_views.py`; passed to the landing template as `hero_video_url` and `hero_video_poster_url`.
- **How to update:** Set the above settings in your environment or `config/settings.py`. For externally hosted videos (e.g. Loom, Synthesia), paste the direct video URL into `MARKETING_HERO_VIDEO_URL`. The site shows the video when the URL is present; if absent, the hero can show a placeholder or image instead.

### Other video slots (required)

Segment-level or page-level video URLs (migration explainer, control plane demo, onboarding journey, workflow simulation, global network motion) are **required** as part of Batch 2/3 in the Visual Asset pack. Add `video_url` (and optionally `video_poster_url`, `video_heading`, `video_caption`) in `MARKETING_PAGE_EXTRAS` or in `config/marketing_content/*.json` for the relevant page slugs. The template `templates/schools/marketing_page.html` renders a "See it in action" video section when `page_extras.video_url` is set. Document each slot in the Visual Asset doc and in [MARKETING_VISUAL_VERIFICATION.md](MARKETING_VISUAL_VERIFICATION.md).

---

## Data visualizations

### Platform analytics page

- **Page:** `/platform/analytics/`
- **Asset:** `static/images/marketing/viz-admin.svg` (sample admin dashboard).
- **Context:** `MARKETING_PAGE_EXTRAS["platform-analytics"]` includes `data_viz_path` and `data_viz_caption` when set.
- **Template:** `templates/schools/marketing_page.html` renders a “See what matters” section when `page_extras.data_viz_path` is set.
- **How to update:** Change `data_viz_path` and `data_viz_caption` in `MARKETING_PAGE_EXTRAS["platform-analytics"]`, or add `data_viz_path` / `data_viz_caption` to other page extras to show a visualization on that page.

### Live charts

Live charts (e.g. Chart.js with data from a read-only API or static JSON) are **required** if in scope for platform analytics; otherwise treat as out of scope until a formal platform decision with date and owner. If implemented: add a block in the relevant template that loads Chart.js and passes data from the view (e.g. `page_extras.chart_data`); document the data shape and endpoint here. Per [PLAN_POLICY.md](PLAN_POLICY.md), no indefinite "optional" — either required (with target) or out of scope (with date).

---

## Summary table

| Type      | Page(s)                    | Config / asset location                                                                 | How to update                          |
|-----------|----------------------------|-------------------------------------------------------------------------------------------|----------------------------------------|
| Diagram   | Education OS, Platform hub | `MARKETING_PAGE_EXTRAS` + `static/images/marketing/platform-diagram-marketing.svg`       | Edit SVG or change `diagram_path`       |
| Video     | Homepage hero              | `MARKETING_HERO_VIDEO_URL`, `MARKETING_HERO_VIDEO_POSTER_URL` in settings                | Set URLs in settings                    |
| Video     | Any marketing subpage      | `page_extras.video_url` (and `video_poster_url`, `video_heading`, `video_caption`) in `MARKETING_PAGE_EXTRAS` or JSON | Add keys to page entry; template renders when `video_url` set |
| Data viz  | Platform analytics         | `MARKETING_PAGE_EXTRAS["platform-analytics"]` + `static/images/marketing/viz-admin.svg`   | Change `data_viz_path` / caption or SVG |
