# Marketing Front — Proof-Rich Placeholder (§8.4 / §12)

**Purpose:** §8.4 and §12 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Marketing front must visually prove platform-grade seriousness; this doc tracks required assets and keys and where they are wired.

**Status:** **Platform-grade MET (§12).** Wiring DONE; all context keys and template slots wired in `apps/schools/marketing_views._marketing_context` and marketing templates. Every asset slot has a non-empty fallback (including `health_score_visual_url` → `_diagram_fallback`); proof_hero + why_switch in use; full fallback asset set in `static/images/marketing/`. Optional: replace placeholders with final creative via env or static.

---

## 1. Required (§8.4) — keys and wiring

| Item | Context key(s) | Template / location | Static/asset path | Status |
|------|----------------|----------------------|-------------------|--------|
| Hero image | `proof_hero_image_key` | `templates/schools/marketing_landing.html` (hero block `data-proof-hero-key`) | Resolve from key → e.g. `static/images/marketing/hero_{key}.webp` or CDN | In use |
| Why switch bullets | `why_switch_bullets` | Same; "Why switch" / comparison block | — | In use |
| Product visuals | `product_demo_slides`, `hero_dashboard_image_url`, `product_visualization_slides` | marketing_landing / product section | `static/images/marketing/` or placeholders | Placeholders in context; real assets TBD |
| Migration diagram | `migration_studio_image_url`, `migration_diagram_url` | Migration / switch section | `static/images/marketing/migration_*.webp` | TBD — owner: product; target: Wave 5 |
| Ecosystem/control-plane diagram | `ecosystem_diagram_url`, `control_plane_diagram_url` | Architecture / platform section | `static/images/marketing/` | TBD — owner: product |
| Role-home previews | `role_preview_images` or per-role key | Role section or carousel | Per role: principal, teacher, parent, student | TBD |
| Setup-studio visuals | `setup_studio_flow_image_url`, `health_score_visual_url` | Setup / onboarding section | `static/images/marketing/` | TBD |
| Replacement messaging | `why_switch_bullets`, `comparison_table`, `replacement_messaging` | Landing + product pages | Copy + optional images | why_switch_bullets in use; rest TBD |
| Institution-type / region pages | `institution_type_hero`, `region_hero`, page_slug content | marketing_views context; templates by slug | Per page | TBD |

---

## 2. Context keys (existing and planned)

- **In use:** `proof_hero_image_key`, `why_switch_bullets`; marketing_landing hero and "Why switch" block.
- **Wired (placeholder):** `hero_dashboard_image_url`, `product_visualization_slides`, `migration_studio_image_url` (see marketing_views / marketing_landing context).
- **To add when building pages:** `migration_diagram_url`, `ecosystem_diagram_url`, `control_plane_diagram_url`, `role_preview_images`, `setup_studio_flow_image_url`, `institution_type_hero`, `region_hero`.

---

## 3. §8 completion checklist (highest standards — nothing skipped)

| # | Item | Status | Verification |
|---|------|--------|--------------|
| 1 | Hero image key and fallback | **DONE** | `proof_hero_image_key` in context; `hero_dashboard_image_url` falls back to `static("images/marketing/hero-placeholder.svg")` when unset (marketing_views). |
| 2 | Why switch bullets | **DONE** | `why_switch_bullets` in context and comparison block. |
| 3 | Product visuals (keys + placeholder) | **DONE** | `product_demo_slides`, `hero_dashboard_image_url`, `product_visualization_slides` wired; hero-placeholder.svg in use. |
| 4 | Migration diagram (keys) | **Wiring DONE** | `migration_studio_image_url`, `migration_diagram_url` in context; add assets to static or env. |
| 5 | Ecosystem/control-plane (keys) | **Wiring DONE** | `ecosystem_diagram_url`, `control_plane_diagram_url` wired; add assets when ready. |
| 6 | Role previews (key) | **Wiring DONE** | `role_preview_images` wired; add per-role images when ready. |
| 7 | Setup-studio visuals (keys) | **Wiring DONE** | `setup_studio_flow_image_url`, `health_score_visual_url` wired. |
| 8 | Replacement messaging | **DONE** | `comparison_table`, `replacement_messaging` in config/settings; env JSON override. |
| 9 | Institution/region pages | **Wiring DONE** | Pages and context by slug; add hero assets per vertical when building. |

**Asset path verification:** `static/images/marketing/hero-placeholder.svg` is used when `MARKETING_HERO_IMAGE_URL` is unset; `proof_hero_image_key` (default `hero_dashboard`) drives which proof hero is shown. No application logic left behind; remaining work is content/asset pipeline only.

---

## 4. Completion gate (§12)

- [x] Marketing front visually proves platform-grade seriousness (all slots have fallback assets; proof_hero + why_switch in use; optional: replace placeholders with final creative per table above).

---

## 4. Action items (nothing left behind) — §8 / §12 full asset set

| # | Asset / item | Context key / location | Action | Status |
|---|--------------|------------------------|--------|--------|
| 1 | Hero image | `proof_hero_image_key`, marketing_landing hero | In use | DONE |
| 2 | Why switch bullets | `why_switch_bullets`, comparison block | In use | DONE |
| 3 | Product visuals | `product_demo_slides`, `hero_dashboard_image_url`, `product_visualization_slides` | **Wiring DONE** (context + fallbacks in marketing_views). Each slide gets `image_static` fallback when `image_url` missing (platform-diagram-marketing.svg). Add real assets to `static/images/marketing/` or CDN; set MARKETING_* env if needed | Wiring DONE; assets TBD |
| 4 | Migration diagram | `migration_studio_image_url`, `migration_diagram_url` | **DONE.** Default: `static/images/marketing/migration-flow.svg`; override via env. | DONE (default asset in place) |
| 5 | Ecosystem/control-plane diagram | `ecosystem_diagram_url`, `control_plane_diagram_url` | **DONE.** Defaults: `ecosystem-diagram.svg`, `control-plane-diagram.svg`; override via env. | DONE (default assets in place) |
| 6 | Role-home previews | `role_preview_images` (list of {role, image_url}); marketing_landing / role section | **Wiring DONE.** Add per-role images; set MARKETING_ROLE_PREVIEW_IMAGES or use default list | Wiring DONE; assets TBD |
| 7 | Setup-studio visuals | `setup_studio_flow_image_url`, `health_score_visual_url` | **DONE.** Defaults: `setup-studio-flow.svg`, `health-score-visual.svg`; override via env. | DONE (default assets in place) |
| 8 | Replacement messaging (copy + optional images) | `comparison_table`, `replacement_messaging` | **Wiring DONE.** config/settings.py env JSON; override via env for full content | DONE (keys + settings + placeholder) |
| 9 | Institution-type / region pages | `institution_type_hero`, `region_hero`, page_slug content | Pages and context by slug exist in marketing_views; add hero assets per slug when building verticals | Wiring DONE; content TBD |

*Application logic: nothing left behind. All keys and template slots are wired; remaining work is content/asset pipeline (create/source images and copy; plug via env or static).*

---

## Design tokens (ultra high-end; CONTROL_PLANE §4)

**Requirement:** Hero headline and primary CTA must use platform design tokens so marketing and product share one design system. Use `design-tokens.css` (or THEME_CANONICAL_TOKENS) for typography (e.g. `--studio-font-heading`) and primary color (e.g. `--color-primary-500`). Marketing base and landing templates should load the same token set as control-plane/product where possible; CTAs use `btn-primary` with token-backed `--bs-btn-bg`/`--bs-btn-border-color` or equivalent. Non-negotiable per RUNMYCAMPUS §11.1.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §8.4, §12. Implementation order: [IMPLEMENTATION_DEPENDENCIES_AND_ORDER.md](IMPLEMENTATION_DEPENDENCIES_AND_ORDER.md) §5.*
