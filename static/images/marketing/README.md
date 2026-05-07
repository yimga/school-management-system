# Marketing homepage assets

Default placeholder SVGs are included so no section 404s. Replace with final art when ready.

## Included placeholders (no code change required to run)

- **Hero:** `hero-global-os-composite.svg` – default product composite (leadership, admin, teacher, parent mobile, finance, student, analytics). `hero-placeholder.svg` remains for legacy references only.
- **Admissions pipeline:** `platform-admissions-pipeline.svg` – enrollment stages mockup for `/platform/admissions/`.
- **Fees & payments:** `platform-fees-payments-dashboard.svg` – finance workspace mockup for `/platform/fees-payments/`.
- **Parent portal:** `platform-parent-mobile-portal.svg` – mobile-first parent UI for `/platform/parent-portal/`.
- **Teacher portal:** `platform-teacher-workspace.svg` – classroom workspace for `/platform/teacher-portal/`.
- **Module screenshots:** `module-admissions.svg`, `module-academics.svg`, `module-finance.svg`, `module-communication.svg`, `module-compliance.svg` – wired in `core_modules` context.
- **Product viz:** `viz-student360.svg`, `viz-teacher.svg`, `viz-admin.svg` – wired in `product_visualization_slides`.
- **Global map:** `global-map.svg` – used when `MARKETING_GLOBAL_MAP_IMAGE_URL` is unset.
- **Illustrations:** `illustration-workflow.svg`, `illustration-globe.svg`, `illustration-students.svg` – used when the corresponding `MARKETING_ILLUSTRATION_*_URL` is unset.
- **Customer logos:** `logo-placeholder.svg` – used for each `customer_logos` entry when you don’t set a custom `logo_url`/`image_url`.
- **Video testimonial thumb:** `testimonial-thumb.svg` – used for the default video testimonial card when `MARKETING_VIDEO_TESTIMONIALS` is unset.

## Asset governance table

| Asset | Used by | Purpose | Alt/source guidance | Status |
| --- | --- | --- | --- | --- |
| `hero-global-os-composite.svg` | Homepage and product pages | Product operating-system composite | Use descriptive product-composite alt text | Active |
| `platform-admissions-pipeline.svg` | `/platform/admissions/` | Admissions workflow proof | Alt should name inquiry through enrollment stages | Active |
| `platform-fees-payments-dashboard.svg` | `/platform/fees-payments/` | Finance dashboard mockup | Alt should name invoices, receipts, arrears, balances | Active |
| `platform-parent-mobile-portal.svg` | `/platform/parent-portal/` | Parent mobile visibility mockup | Alt should name child profile, attendance, fees, report cards | Active |
| `platform-teacher-workspace.svg` | `/platform/teacher-portal/` | Teacher classroom workspace | Alt should name class list, attendance, marks, assignments | Active |
| `viz-admin.svg` | `/platform/analytics/` and product visuals | Leadership analytics visual | Use dashboard/analytics alt text | Active |
| `platform-diagram-marketing.svg` | `/platform/security/` and platform pages | Governance/platform diagram | Use governance/security alt text | Active |
| `setup-studio-flow.svg` | `/platform/offline-first/` and setup storytelling | Offline/setup flow proof | Use setup/workflow alt text | Active |

## Optional settings (replace placeholders)

- **Hero:** Set `MARKETING_HERO_IMAGE_URL` (and optionally `MARKETING_HERO_VIDEO_URL`, `MARKETING_HERO_VIDEO_POSTER_URL`). For responsive hero image set `MARKETING_HERO_IMAGE_SRCSET` and `MARKETING_HERO_IMAGE_SIZES`.
- **Product demo / migration:** `MARKETING_PRODUCT_DEMO_IMAGE_URL`, `MARKETING_MIGRATION_STUDIO_IMAGE_URL`.
- **Global map / illustrations:** `MARKETING_GLOBAL_MAP_IMAGE_URL`, `MARKETING_ILLUSTRATION_WORKFLOW_URL`, `MARKETING_ILLUSTRATION_GLOBE_URL`, `MARKETING_ILLUSTRATION_STUDENTS_URL`.
- **Video testimonials:** Set `MARKETING_VIDEO_TESTIMONIALS` to a list of `{url, title, thumbnail_url}` for real videos.
- **Customer logos:** For each school in `customer_logos`, set `logo_url` or `image_url` to your asset (or keep the default placeholder).

## Trust logos

The landing uses `trust_logos` (name + image_url). Replace placeholder entries in context with real logo URLs, or add files here and reference via `{% static 'images/marketing/partner-logo.png' %}`.
