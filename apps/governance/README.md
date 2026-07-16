# apps/governance

> The optional Organization overlay *above* the school: legal owners, group
> membership, org-scoped roles, cross-school employment, and multi-role context
> profiles.

**Tenancy:** SHARED (public schema; the overlay spans schools by definition, so it cannot live inside one tenant's schema)
**Scale:** 6 models · 6 migrations · 6 test modules · ~4.3k LOC

## What this app owns

Most school-management systems assume the school is the top of the world.
Governance exists because it often is not: a diocese, a ministry, a multi-academy
trust, a proprietor chain, or a franchise network sits above a set of schools and
wants some policies inherited and others left alone.

This app owns that overlay — and the single most important thing to understand
about it is that **the overlay is optional, and School remains the tenant
boundary**. The first line of `models.py` says so outright. `Organization` is
described as the "legal owner above optional group membership. Schools may omit
this entirely." A standalone school never touches this app, has a null
`organization`, and resolves every policy locally. Governance never becomes a
required layer in the hierarchy, and adding an Organization must never change
where a school's data lives.

The second decision is **fail-local inheritance**. A group member declares, per
policy domain, whether it inherits from the org. Every ambiguity in that
resolution — standalone school, unknown domain, missing entry, garbage string —
resolves to `local`. Inheritance is opt-in at every step. A misconfiguration can
therefore cost a group its centralization, but it can never silently hand one
school's policy control to an organization it did not explicitly join.

## Key models

All 6 models, in dependency order:

| Model | Table | Purpose |
| --- | --- | --- |
| `Organization` | `governance_organization` | The legal owner above optional group membership; UUID PK, unique slug, `legal_owner_type` ∈ proprietor / corporation / diocese / ministry / ngo / franchise. Schools may omit this entirely |
| `GovernanceNode` | `governance_governancenode` | Optional self-parented tree under an Organization (diocese office, LGA, MAT central) |
| `OrgMembership` | `governance_orgmembership` | User membership at *organization* scope — deliberately distinct from `SchoolMembership`. Roles: owner / group_admin / inspector / superintendent |
| `SchoolContextProfile` | `governance_schoolcontextprofile` | Multi-role context for one user at one school (Phase 3C): lets one login switch teacher/student/parent personas without separate accounts. Adds `context_key` granularity on top of `SchoolMembership` |
| `Employment` | `governance_employment` | Org-level employer record — the teacher-transfer foundation. The employer is the *org*, not the school |
| `SchoolAssignment` | `governance_schoolassignment` | Deploys an `Employment` to a member school with an `allocation_fraction` (a teacher can be 0.4 at one school, 0.6 at another) |

## Surfaces

This app has **no `urls.py`** and **no Celery tasks**. It is a model layer plus
resolver library consumed by `apps.schools`, the operator console, and signup.

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `services` | `resolve_governance_operating_mode()`, `inherit_domain()`, `school_in_group_mode()` — the inheritance resolver |
| Module | `operating_modes` | `GovernanceOperatingMode`: standalone / group_member / group_member_sovereign |
| Module | `org_role_registry` | Canonical org role strings for use outside the model layer |
| Module | `context_profiles` | Session-bound active-profile helpers (`ACTIVE_PROFILE_SESSION_KEY`) |
| Module | `fast_switch` | Shared-terminal / kiosk profile switch without full re-login; ~100ms session-write budget |
| Module | `archetypes` | Catalog of four global governance patterns; suggests structure at signup, never enforces it |
| Module | `country_matrix_service` | Read-only, `lru_cache`d access to the country governance matrix shards in `docs/generated/` |
| Module | `academic_pack_bridge` | Maps matrix rows to localization packs and grading presets |
| Module | `mat_groups_sync` | Derives the operator MAT group registry from live Organization membership |
| Command | `backfill_organizations_from_hierarchy` | One-off backfill of Organizations from the legacy hierarchy |

## Before you change this

- **School is the tenant boundary; Organization is not.** `models.py` opens with
  "Organization overlay models (public schema). School remains the tenant
  boundary." Org rows group schools, they do not contain them. Never route data
  access, schema selection, or isolation through an Organization — an org-scoped
  query that forgets to re-scope to School is a cross-tenant leak.
- **Standalone is the default and must stay first-class.**
  `resolve_governance_operating_mode()` returns `standalone` for a null school,
  an unset mode, and an unrecognized mode string. `inherit_domain()` returns
  `local` unconditionally for standalone schools *before* it even looks at the
  inherit map. A school with no Organization is a fully supported configuration,
  not a half-set-up one.
- **Inheritance fails local, in four separate ways.** `inherit_domain()` returns
  `local` for: a blank domain, a standalone school, a domain that is both absent
  from the map and not in `KNOWN_INHERIT_DOMAINS`, and any disposition string
  outside `{inherit, local, hybrid}`. This is the app's security posture, not
  defensive clutter. If you add a resolution branch, it defaults to `local` too.
- **`governance_inherit` lives in `School.settings` JSON, not in a column.** The
  key is `GOVERNANCE_INHERIT_SETTINGS_KEY`, and the documented domains are
  `curriculum`, `fees`, `hr`, `branding`, `emis`, `integrations`
  (`KNOWN_INHERIT_DOMAINS`). Adding a domain means updating that frozenset —
  otherwise a value written into the JSON resolves to `local` and is silently
  ignored. The property-invariant tests pin exactly this domain list.
- **Applying an inherit map is idempotent by contract** — the property test states
  "applying twice equals applying once" and asserts it. Any rewrite of the apply
  path must preserve that.
- **`OrgMembership` is not `SchoolMembership`.** Its docstring calls out the
  distinction explicitly. Org roles (owner / group_admin / inspector /
  superintendent) come from `org_role_registry`; school roles come from the
  accounts role registry. They are different namespaces — do not cross-check one
  against the other, and prefer `OrgMembership.Role` in application code, importing
  the `org_role_registry` constants only where a stable string is needed outside
  the model layer.
- **`mat_groups_sync` preserves legacy JSON.** It builds the MAT registry from
  live `School` rows in group mode, but entries in `cockpit_payload["mat_groups"]`
  that are not yet backed by an Organization are deliberately kept, not dropped.
  Do not "clean up" that merge — it is the migration path.
- The country governance matrix is **read-only generated data** loaded from
  `docs/generated/country_governance_matrix/` and `lru_cache`d per ISO code. Edit
  the generator, not the shards; and remember the cache is process-lifetime, so a
  shard change needs a restart to take effect.
