# Marketing Visual Verification

Every asset from [RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md](RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md) must have a verification path. No row may remain "TBD" without an owner and target date. Per [PLAN_POLICY.md](PLAN_POLICY.md), all items are required.

**Wiring status:** All verification paths (context keys + template blocks) are wired in `apps/schools/marketing_views._marketing_context` and marketing templates. "Verified in" uses settings or static fallbacks when the asset file does not yet exist. Replace TBD with actual asset path when assets are created.

**Legend:** Verified in = file path under `static/images/marketing/` or CDN URL, or template block + context key. When not yet implemented, use TBD with owner and target (e.g. "TBD — owner: product/marketing; target: Wave 5").

---

## Batch 1

| Asset name | Batch/Diagram | Verified in | Page/section |
|------------|---------------|-------------|--------------|
| Hero platform visual | Batch 1 | `hero_dashboard_image_url` in `_marketing_context`; `MARKETING_HERO_IMAGE_URL`; `marketing_landing.html` #hero `<img>`; fallback: runmycampus-logo or hero-placeholder | `#hero` |
| Admin dashboard mockup | Batch 1 | `product_visualization_slides[0].image_static` e.g. `images/marketing/viz-admin.svg`; `marketing_landing.html` #product-visualization | `#product-visualization` |
| Teacher dashboard mockup | Batch 1 | `product_visualization_slides[].image_static` viz-teacher.svg | `#product-visualization` |
| Parent mobile portal mockup | Batch 1 | `product_visualization_slides[].image_static` | `#product-visualization` |
| Student portal mockup | Batch 1 | `product_visualization_slides[].image_static` viz-student360.svg | `#product-visualization` |
| Platform architecture diagram | Batch 1 | `platform_architecture_diagram_url`; `marketing_landing.html` #one-platform; `MARKETING_PAGE_EXTRAS` diagram_path; asset: `static/images/marketing/platform-diagram-marketing.svg` | Homepage, platform page |
| Migration Cloud diagram | Batch 1 | `migration_studio_image_url` (never empty: MARKETING_MIGRATION_STUDIO_IMAGE_URL or migration_cloud_diagram_url or fallback); `marketing_landing.html` #migration | `#migration` |
| Marketplace storefront mockup | Batch 1 | `MARKETING_PAGE_EXTRAS["app-marketplace"]` diagram_path; `ecosystem_apps`; `marketing_landing.html` #ecosystem | Marketplace page, `#ecosystem` |
| School setup wizard mockup | Batch 1 | `school_in_a_box_flow_image_url`; `marketing_landing.html` #launch-in-minutes; CTA to `onboard_wizard` | Onboarding, homepage "Launch in minutes" |
| Global education network visual | Batch 1 | `global_map_image_url`, `illustration_globe_url` in `_marketing_context`; `marketing_landing.html` #global-infrastructure | `#global-infrastructure` |
| Hero motion loop (8–12 s) | Batch 1 | `hero_video_url`, `hero_video_poster_url`; `MARKETING_HERO_VIDEO_URL`; `marketing_landing.html` #hero `<video>` when URL set | `#hero` |

---

## Batch 2

| Asset name | Batch/Diagram | Verified in | Page/section |
|------------|---------------|-------------|--------------|
| Control plane / district dashboard | Batch 2 | `MARKETING_PAGE_EXTRAS["platform-control-plane"]` with `diagram_path: "images/marketing/platform-diagram-marketing.svg"`; `marketing_page.html` diagram section | Platform page, ecosystem |
| Workflow builder preview | Batch 2 | `illustration_workflow_url` in `_marketing_context`; `marketing_landing.html` workflow section; platform page `diagram_path` | Platform page, workflow section |
| Dashboard pack preview | Batch 2 | `MARKETING_PAGE_EXTRAS["platform-analytics"]` / `app-marketplace` with `data_viz_path`; `product_visualization_slides` | Marketplace page |
| Blueprint pack gallery | Batch 2 | `ecosystem_apps`, marketplace page `diagram_path`; `marketing_landing.html` #ecosystem | Marketplace page |
| Policy bundle comparison visual | Batch 2 | Platform and marketplace pages use `diagram_path`; `platform_pillar_grid`, `trust_controls` | Marketplace, platform page |
| AI recommendations scene | Batch 2 | `data_intelligence_loop_image_url`, `ai_intelligence_features`; `marketing_landing.html` #ai-intelligence; `products-analytics` data_viz_path | AI page, `#ai-intelligence` |
| School website / theme studio preview | Batch 2 | Onboarding wizard step 3 (template gallery); `school_in_a_box_flow_image_url` on landing | Onboarding page, design studio |
| School-in-a-box modular assembly illustration | Batch 2 | `school_in_a_box_flow_image_url` in `_marketing_context`; `marketing_landing.html` #launch-in-minutes; fallback: `static/images/marketing/platform-diagram-marketing.svg` | Homepage "Launch in minutes," platform page |

---

## Batch 3 (motion)

| Asset name | Batch/Diagram | Verified in | Page/section |
|------------|---------------|-------------|--------------|
| Hero motion loop | Batch 3 | `MARKETING_HERO_VIDEO_URL`, `hero_video_url` in `_marketing_context`; `marketing_landing.html` #hero `<video>` when set | `#hero` |
| Migration explainer animation | Batch 3 | `page_extras.video_url` in `MARKETING_PAGE_EXTRAS` for platform-migration-cloud (or migration slug); `marketing_page.html` video section | Migration page, `#migration` |
| Onboarding journey animation | Batch 3 | Add `video_url` to page extras for onboarding/getting-started slug; `marketing_page.html` renders when `page_extras.video_url` set | Onboarding / getting-started page |
| Workflow simulation animation | Batch 3 | Add `video_url` to workflow or platform page extras; `marketing_page.html` video section | Workflow automation section |
| Global network motion graphic | Batch 3 | `hero_video_url` for hero; or add `video_url` to page with global-infrastructure content; `marketing_landing.html` #global-infrastructure | Hero or `#global-infrastructure` |

---

## Strategic diagrams

| Asset name | Batch/Diagram | Verified in | Page/section |
|------------|---------------|-------------|--------------|
| Platform Visual Architecture (Education Infrastructure Map) | Diagram | `platform_architecture_diagram_url` in `_marketing_context`; `MARKETING_PLATFORM_ARCHITECTURE_DIAGRAM_URL`; `marketing_landing.html` #one-platform; `MARKETING_PAGE_EXTRAS` `diagram_path` for education-operating-system, platform, platform-control-plane; asset: `static/images/marketing/platform-diagram-marketing.svg` | Homepage "One Platform," platform page |
| Ecosystem Map | Diagram | `ecosystem_map_image_url` in `_marketing_context`; `MARKETING_ECOSYSTEM_MAP_IMAGE_URL`; fallback `platform-diagram-marketing.svg`; can be set per page via diagram_path | Homepage, platform page |
| School-in-a-Box Launch Flow | Diagram | `school_in_a_box_flow_image_url` in `_marketing_context`; `MARKETING_SCHOOL_IN_A_BOX_FLOW_IMAGE_URL`; `marketing_landing.html` #launch-in-minutes | Homepage, onboarding, getting-started |
| Data Intelligence Loop | Diagram | `data_intelligence_loop_image_url` in `_marketing_context`; `MARKETING_DATA_INTELLIGENCE_LOOP_IMAGE_URL`; `marketing_landing.html` #ai-intelligence; `products-analytics` data_viz_path + data_viz_caption | AI page, homepage AI section |

---

## Completion rule

- When an asset is implemented, update **Verified in** with the actual path or context key.
- If an asset is not yet implemented, **Verified in** must include "TBD — owner: [role]; target: [date or Wave 5]."
- Review this checklist when executing Wave 5 and when adding new marketing visuals.
