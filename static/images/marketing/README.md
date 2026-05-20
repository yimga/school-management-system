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
| `home-unified-school-journey.svg` | Homepage `_home_os_story.html` | Learner journey diagram | Illustrative — not customer data | Active |
| `home-six-operating-surfaces.svg` | Homepage `_home_os_story.html` | Six operating surfaces grid | Illustrative product composite | Active |
| `platform-sis-record-spine.svg` | `/platform/student-information-system/` | Student record spine | Illustrative learner profile | Active |
| `platform-attendance-daily-register.svg` | `/platform/attendance/` | Daily register | Illustrative roll / late patterns | Active |
| `platform-grading-publishing-studio.svg` | `/platform/grading-report-cards/` | Academic publishing | Illustrative gradebook / reports | Active |
| `platform-communications-orchestration.svg` | `/platform/communications/` | Message orchestration | Illustrative delivery stats | Active |
| `platform-workflows-automation-timeline.svg` | `/platform/workflows/` | Automation timeline | Illustrative approvals | Active |
| `platform-offline-sync-console.svg` | `/platform/offline-first/` | Edge sync console | Illustrative queue / sync | Active |
| `platform-student-self-service.svg` | `/platform/student-portal/` | Student hub | Illustrative mobile surface | Active |
| `solution-private-growth-engine.svg` | `/solutions/private-schools/` | Private school flywheel | Illustrative — no fake logos | Active |
| `solution-international-global-model.svg` | `/solutions/international-schools/` | Global operating model | Illustrative currencies / calendars | Active |
| `solution-k12-lifecycle.svg` | `/solutions/k12-schools/` | K–12 lifecycle | Illustrative journey | Active |
| `solution-multi-campus-command-center.svg` | `/solutions/multi-campus/` | Network command center | Illustrative campus rollups | Active |
| `solution-faith-community-hub.svg` | `/solutions/faith-based-schools/` | Community operations | Illustrative family comms | Active |
| `solution-growing-network-playbook.svg` | `/solutions/growing-school-networks/` | Launch playbook | Illustrative readiness | Active |

Regenerate category assets: `python scripts/generate_marketing_category_assets.py`

## Optional settings (replace placeholders)

- **Hero:** Set `MARKETING_HERO_IMAGE_URL` (and optionally `MARKETING_HERO_VIDEO_URL`, `MARKETING_HERO_VIDEO_POSTER_URL`). For responsive hero image set `MARKETING_HERO_IMAGE_SRCSET` and `MARKETING_HERO_IMAGE_SIZES`.
- **Product demo / migration:** `MARKETING_PRODUCT_DEMO_IMAGE_URL`, `MARKETING_MIGRATION_STUDIO_IMAGE_URL`.
- **Global map / illustrations:** `MARKETING_GLOBAL_MAP_IMAGE_URL`, `MARKETING_ILLUSTRATION_WORKFLOW_URL`, `MARKETING_ILLUSTRATION_GLOBE_URL`, `MARKETING_ILLUSTRATION_STUDENTS_URL`.
- **Video testimonials:** Set `MARKETING_VIDEO_TESTIMONIALS` to a list of `{url, title, thumbnail_url}` for real videos.
- **Customer logos:** For each school in `customer_logos`, set `logo_url` or `image_url` to your asset (or keep the default placeholder).

## Trust logos

The landing uses `trust_logos` (name + image_url). Replace placeholder entries in context with real logo URLs, or add files here and reference via `{% static 'images/marketing/partner-logo.png' %}`.
