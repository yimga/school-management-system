# Marketing asset governance

This directory is the governed static-art surface for public marketing. Active
assets below are intentionally illustrative product diagrams and mockups; they
must not be presented as customer screenshots, customer logos, or third-party
attestations.

## Active static assets

- **Hero:** `hero-global-os-composite.svg` - product composite for leadership, admin, teacher, parent mobile, finance, student, and analytics surfaces. `hero-placeholder.svg` remains legacy-only.
- **Admissions pipeline:** `platform-admissions-pipeline.svg` - enrollment stages mockup for `/platform/admissions/`.
- **Fees & payments:** `platform-fees-payments-dashboard.svg` - finance workspace mockup for `/platform/fees-payments/`.
- **Parent portal:** `platform-parent-mobile-portal.svg` - mobile-first parent UI for `/platform/parent-portal/`.
- **Teacher portal:** `platform-teacher-workspace.svg` - classroom workspace for `/platform/teacher-portal/`.
- **Module screenshots:** `module-admissions.svg`, `module-academics.svg`, `module-finance.svg`, `module-communication.svg`, `module-compliance.svg` - wired in `core_modules` context.
- **Product viz:** `viz-student360.svg`, `viz-teacher.svg`, `viz-admin.svg` - wired in `product_visualization_slides`.
- **Global map:** `global-map.svg` - used when `MARKETING_GLOBAL_MAP_IMAGE_URL` is unset.
- **Illustrations:** `illustration-workflow.svg`, `illustration-globe.svg`, `illustration-students.svg` - used when the corresponding `MARKETING_ILLUSTRATION_*_URL` is unset.
- **Legacy fallback files:** `logo-placeholder.svg`, `testimonial-thumb.svg`, and `hero-placeholder.svg` remain for older template/config references only. Do not use them as proof.

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
| `platform-security-governance-center.svg` | Homepage category proof and `/platform/security/` | Trust/procurement governance visual | Alt should name role coverage, audit events, risk flags, and access exceptions | Active |
| `setup-studio-flow.svg` | `/platform/offline-first/` and setup storytelling | Offline/setup flow proof | Use setup/workflow alt text | Active |
| `ecosystem-diagram.svg` | Homepage category proof and marketplace pages | Marketplace/extensibility model | Alt should name approved apps, APIs, integrations, tenant controls, and rollout boundaries | Active |
| `home-unified-school-journey.svg` | Homepage `_home_os_story.html` | Learner journey diagram | Illustrative - not customer data | Active |
| `home-six-operating-surfaces.svg` | Homepage `_home_os_story.html` | Six operating surfaces grid | Illustrative product composite | Active |
| `platform-sis-record-spine.svg` | `/platform/student-information-system/` | Student record spine | Illustrative learner profile | Active |
| `platform-attendance-daily-register.svg` | `/platform/attendance/` | Daily register | Illustrative roll / late patterns | Active |
| `platform-grading-publishing-studio.svg` | `/platform/grading-report-cards/` | Academic publishing | Illustrative gradebook / reports | Active |
| `platform-communications-orchestration.svg` | `/platform/communications/` | Message orchestration | Illustrative delivery stats | Active |
| `platform-workflows-automation-timeline.svg` | `/platform/workflows/` | Automation timeline | Illustrative approvals | Active |
| `platform-offline-sync-console.svg` | `/platform/offline-first/` | Edge sync console | Illustrative queue / sync | Active |
| `platform-student-self-service.svg` | `/platform/student-portal/` | Student hub | Illustrative mobile surface | Active |
| `solution-private-growth-engine.svg` | `/solutions/private-schools/` | Private school flywheel | Illustrative - no fake logos | Active |
| `solution-international-global-model.svg` | `/solutions/international-schools/` | Global operating model | Illustrative currencies / calendars | Active |
| `solution-k12-lifecycle.svg` | `/solutions/k12-schools/` | K-12 lifecycle | Illustrative journey | Active |
| `solution-multi-campus-command-center.svg` | `/solutions/multi-campus/` | Network command center | Illustrative campus rollups | Active |
| `solution-faith-community-hub.svg` | `/solutions/faith-based-schools/` | Community operations | Illustrative family comms | Active |
| `solution-growing-network-playbook.svg` | `/solutions/growing-school-networks/` | Launch playbook | Illustrative readiness | Active |

Regenerate category assets: `python scripts/generate_marketing_category_assets.py`

## Optional settings

- **Hero:** Set `MARKETING_HERO_IMAGE_URL` and optionally `MARKETING_HERO_VIDEO_URL` and `MARKETING_HERO_VIDEO_POSTER_URL`. For responsive hero image set `MARKETING_HERO_IMAGE_SRCSET` and `MARKETING_HERO_IMAGE_SIZES`.
- **Product demo / migration:** `MARKETING_PRODUCT_DEMO_IMAGE_URL`, `MARKETING_MIGRATION_STUDIO_IMAGE_URL`.
- **Global map / illustrations:** `MARKETING_GLOBAL_MAP_IMAGE_URL`, `MARKETING_ILLUSTRATION_WORKFLOW_URL`, `MARKETING_ILLUSTRATION_GLOBE_URL`, `MARKETING_ILLUSTRATION_STUDENTS_URL`.
- **Video testimonials:** Set `MARKETING_VIDEO_TESTIMONIALS` to a list of `{url, title, thumbnail_url}` for real videos.
- **Customer logos:** Do not surface a school logo unless the approved asset URL is configured for that school.

## Trust logos

The landing uses `trust_logos` values with `name` and `image_url`. Only
configure real, approved logos or locally governed files referenced via
`{% static 'images/marketing/partner-logo.png' %}`.
