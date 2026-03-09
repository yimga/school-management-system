# Marketing homepage assets

Default placeholder SVGs are included so no section 404s. Replace with final art when ready.

## Included placeholders (no code change required to run)

- **Hero:** `hero-placeholder.svg` – used when `MARKETING_HERO_IMAGE_URL` is unset.
- **Module screenshots:** `module-admissions.svg`, `module-academics.svg`, `module-finance.svg`, `module-communication.svg`, `module-compliance.svg` – wired in `core_modules` context.
- **Product viz:** `viz-student360.svg`, `viz-teacher.svg`, `viz-admin.svg` – wired in `product_visualization_slides`.
- **Global map:** `global-map.svg` – used when `MARKETING_GLOBAL_MAP_IMAGE_URL` is unset.
- **Illustrations:** `illustration-workflow.svg`, `illustration-globe.svg`, `illustration-students.svg` – used when the corresponding `MARKETING_ILLUSTRATION_*_URL` is unset.
- **Customer logos:** `logo-placeholder.svg` – used for each `customer_logos` entry when you don’t set a custom `logo_url`/`image_url`.
- **Video testimonial thumb:** `testimonial-thumb.svg` – used for the default video testimonial card when `MARKETING_VIDEO_TESTIMONIALS` is unset.

## Optional settings (replace placeholders)

- **Hero:** Set `MARKETING_HERO_IMAGE_URL` (and optionally `MARKETING_HERO_VIDEO_URL`, `MARKETING_HERO_VIDEO_POSTER_URL`). For responsive hero image set `MARKETING_HERO_IMAGE_SRCSET` and `MARKETING_HERO_IMAGE_SIZES`.
- **Product demo / migration:** `MARKETING_PRODUCT_DEMO_IMAGE_URL`, `MARKETING_MIGRATION_STUDIO_IMAGE_URL`.
- **Global map / illustrations:** `MARKETING_GLOBAL_MAP_IMAGE_URL`, `MARKETING_ILLUSTRATION_WORKFLOW_URL`, `MARKETING_ILLUSTRATION_GLOBE_URL`, `MARKETING_ILLUSTRATION_STUDENTS_URL`.
- **Video testimonials:** Set `MARKETING_VIDEO_TESTIMONIALS` to a list of `{url, title, thumbnail_url}` for real videos.
- **Customer logos:** For each school in `customer_logos`, set `logo_url` or `image_url` to your asset (or keep the default placeholder).

## Trust logos

The landing uses `trust_logos` (name + image_url). Replace placeholder entries in context with real logo URLs, or add files here and reference via `{% static 'images/marketing/partner-logo.png' %}`.
