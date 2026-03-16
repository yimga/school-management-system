# Marketplace Listing Metadata (III.22–III.25)

**Purpose:** Single reference for app/pack listing metadata: description, categories, preview/screenshot, trust markers, and scope/permissions. See PATH_TO_100 §6.10, SOT §6.10.

---

## Current state

- **Richer listing metadata (III.22):** Listing models and APIs support description, categories, region/plan compatibility (e.g. metadata JSON, compatibility checks in packages). Marketplace services merge metadata (description, categories) into listing payloads.
- **Previews/screenshots (III.23):** Use listing `metadata` JSON to store `screenshot_url`, `preview_image_url`, or `preview_url`. No dedicated ImageField on listing model required; UI can read `listing.metadata.get("screenshot_url")` and render. When adding new listings, set metadata accordingly; catalog UI can display when present.
- **Trust markers (III.24):** Use `metadata` for `verified`, `security_review`, or `trust_badges` (list). Catalog template can show badges when `metadata.get("verified")` or `metadata.get("trust_badges")`; implement when product prioritizes.
- **Scope/permission visibility (III.25):** Pack/app install flow and listing detail can show required permissions or scopes from pack definition or `metadata.required_permissions`. Document in install flow; show in listing when available.

## Implementation notes

- **Metadata JSON:** Existing listing and pack models use `metadata` (or equivalent) for extensible fields. Prefer extending metadata over new columns for screenshot/trust/scope until product locks schema.
- **UI:** Marketplace catalog and detail views should read from metadata for screenshot, trust badges, and required permissions when rendering; add keys to seed data or admin when needed.

---

*SOT ref: §6.10 III.22–III.25; NA_REGISTER: previews/trust/scope N/A product 2026-03-12; richer metadata DONE.*
