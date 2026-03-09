# Marketing media: diagrams, video, and data visualizations

This document describes where diagrams, videos, and data visualizations appear on the RunMyCampus marketing site and how to update them.

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
  - `MARKETING_HERO_VIDEO_POSTER_URL`: optional poster image URL. If unset, the view may fall back to a dashboard image URL.
- **Context:** Set in `_marketing_context()` in `apps/schools/marketing_views.py`; passed to the landing template as `hero_video_url` and `hero_video_poster_url`.
- **How to update:** Set the above settings in your environment or `config/settings.py`. For externally hosted videos (e.g. Loom, Synthesia), paste the direct video URL into `MARKETING_HERO_VIDEO_URL`. The site shows the video when the URL is present; if absent, the hero can show a placeholder or image instead.

### Other video slots (future)

Segment-level or page-level video URLs (e.g. migration walkthrough, control plane demo) can be added as `video_url` (or similar) in `MARKETING_PAGE_EXTRAS` or in `config/marketing_content/*.json`, and the templates extended to render them. The same pattern applies: store a URL in config/settings and reference it in the template.

---

## Data visualizations

### Platform analytics page

- **Page:** `/platform/analytics/`
- **Asset:** `static/images/marketing/viz-admin.svg` (sample admin dashboard).
- **Context:** `MARKETING_PAGE_EXTRAS["platform-analytics"]` includes `data_viz_path` and optional `data_viz_caption`.
- **Template:** `templates/schools/marketing_page.html` renders a “See what matters” section when `page_extras.data_viz_path` is set.
- **How to update:** Change `data_viz_path` and `data_viz_caption` in `MARKETING_PAGE_EXTRAS["platform-analytics"]`, or add `data_viz_path` / `data_viz_caption` to other page extras to show a visualization on that page.

### Live charts (optional)

To add live charts (e.g. Chart.js with data from a read-only API or static JSON), add a block in the relevant template that loads Chart.js and passes data from the view (e.g. `page_extras.chart_data`). Document the data shape and endpoint here when implemented.

---

## Summary table

| Type      | Page(s)                    | Config / asset location                                                                 | How to update                          |
|-----------|----------------------------|-------------------------------------------------------------------------------------------|----------------------------------------|
| Diagram   | Education OS, Platform hub | `MARKETING_PAGE_EXTRAS` + `static/images/marketing/platform-diagram-marketing.svg`       | Edit SVG or change `diagram_path`       |
| Video     | Homepage hero              | `MARKETING_HERO_VIDEO_URL`, `MARKETING_HERO_VIDEO_POSTER_URL` in settings                | Set URLs in settings                    |
| Data viz  | Platform analytics         | `MARKETING_PAGE_EXTRAS["platform-analytics"]` + `static/images/marketing/viz-admin.svg`   | Change `data_viz_path` / caption or SVG |
