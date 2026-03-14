# Gilead residue and platform-neutral defaults

**Purpose:** Document remaining historical "Gilead" references and platform-neutral usage. New code and env/docs use neutral naming; migrations and seeded default tenant slug remain for backward compatibility.

## Command rename

- **Command:** `ensure_default_tenant_admin` — ensures a tenant admin for `--slug` or first active tenant. Use `DEFAULT_TENANT_SLUG` to target a tenant (e.g. `gilead-school` for existing DBs). Use `--use-admin-user` to link the platform admin user as tenant admin.
- **Removed:** `ensure_gilead_admin` — legacy alias removed (NEXT_50 step 6 subtractive cleanup). Use `ensure_default_tenant_admin` with the same args (e.g. `--use-admin-user`, `--slug`).

## Migrations (do not edit)

Historical migrations keep existing names so applied history stays valid:

- `schools/0012_seed_default_gilead_school` — seeds one school with slug `gilead-school` if none exist.
- `schools/0013_link_default_admin_to_gilead` — links default admin to that school.
- `customers/0003_ensure_gilead_tenant_domain` — ensures Domain for `gilead-school.runmycampus.com`.
- `siteconfig` migrations that set watermark/footer to "Gilead …" — data can be overridden in admin or via later data migrations.

New installs get one default tenant with slug `gilead-school`; set `DEFAULT_TENANT_SLUG=gilead-school` (or another slug) when running `ensure_default_tenant_admin` / `seed_render_users`.

## Env and docs

- **.env.example:** Database name example is platform-neutral (e.g. `school_platform_db`).
- **Runbooks:** Prefer "default tenant", "first tenant", or "RunMyCampus platform"; use "Gilead" only when referring to the seeded default tenant slug/name for existing deployments.

## Tests

- Tests that use `q=gilead` or slug `gilead-school` exercise redirect/search for the **seeded default** tenant; acceptable. Optional: add tests with a neutral slug (e.g. `default-school`) if a future seed uses it.

## Classification (plan remediation #8)

| Category | Description | Action |
|----------|-------------|--------|
| **Historical** | Migrations, seed data filenames (e.g. `0012_seed_default_gilead_school`) | Leave as-is; do not edit applied migrations. |
| **Comment-only** | Comments or docstrings mentioning "Gilead" as example | Safe; optionally reword to "default tenant" where it improves clarity. |
| **Config-risk** | Env or config that hardcodes tenant slug/name for production | Use `DEFAULT_TENANT_SLUG` / platform-neutral defaults; document in runbooks. |
| **Code-risk** | Code paths that assume slug `gilead-school` or name "Gilead" for behavior | Refactor to use config or first-tenant resolution; no hardcoded slug in app logic. |
| **Branding** | User-facing labels, watermarks, footers saying "Gilead" | Override via SiteSettings/admin or tenant branding; remove from default templates. |

**Current status:** Command rename and deprecated alias are in place; migrations are historical; env/docs use platform-neutral wording. Remaining references are mostly historical (migrations), comment-only, or config (DEFAULT_TENANT_SLUG). No user-facing branding in default flows beyond seeded tenant name/slug that admins can change.

## References

- `apps/accounts/management/commands/ensure_default_tenant_admin.py`
- `apps/accounts/management/commands/seed_render_users.py` (calls `ensure_default_tenant_admin`)
