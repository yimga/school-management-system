# SiteSettings / get_solo usage inventory

**Goal:** No direct `SiteSettings` / `get_solo` in tenant-facing flows; route behavior through runtime resolvers.

**Status:** To be populated. Classify each usage as:

- **Allowed global default** — platform-wide, not tenant-specific.
- **Forbidden runtime bypass** — must use runtime resolver instead.
- **To-be-decomposed** — move to registry, blueprint, policy, entitlement, or branding metadata.

Run: `grep -r "get_solo\|SiteSettings" --include="*.py" apps/ config/` and fill a table: file, function, purpose, classification.
