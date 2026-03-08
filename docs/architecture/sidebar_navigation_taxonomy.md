# Sidebar and navigation taxonomy

Governed grouping model for platform navigation. Sidebars and nav should be driven by runtime, role, entitlements, and installed apps—not hardcoded per template. This doc defines the grouping model and which groups apply to each plane.

## Sidebar grouping model

Stable groups used across the platform:

| Group | Description | Control plane | Admin | Tenant |
|-------|-------------|---------------|-------|--------|
| **Work** | Primary tasks, queues, today view | Overview, Queues | — | Dashboard, Today |
| **Records** | List/detail CRUD, entities | Tenants, Schools | Model lists | Students, Teachers, Classes |
| **Operations** | Day-to-day ops, maintenance | Migration, Sync repair | Maintenance | Attendance, Marks, Timetable |
| **Communications** | Messages, announcements, notifications | — | — | Messages, Announcements |
| **Insights** | Reports, analytics, dashboards | Usage, Pulse | — | Reports, Analytics |
| **Governance** | Policies, compliance, approval | Blueprints, Marketplace, Compliance | — | Settings, Permissions |
| **Settings** | Config, preferences, admin | Platform Settings | Site config | School config, Profile |
| **Extensions** | Installed apps, integrations | App catalog, Providers | — | Installed apps |

Role-specific sidebars (Teacher, Parent, Finance, etc.) show a **slice** of these groups and items relevant to that role; the data source (nav registry / siteconfig) filters by role and entitlement.

## Control plane sidebar (target structure)

Grouped, dense, operational nav:

- **Overview** (Work)
- **Tenants** (Records): tenant list, create school, tenant health
- **Blueprints** (Governance)
- **Policies** (Governance)
- **Workflows** (Governance)
- **Dashboards** (Governance)
- **Marketplace** (Governance): governance, blueprints, app catalog
- **Migration Cloud** (Operations)
- **Providers** (Extensions)
- **Observability** (Insights): pulse, incidents
- **Billing** (Governance)
- **Compliance** (Governance)
- **Platform Settings** (Settings)

Supports: collapse/expand, section pinning, power search, counts/status badges, incident highlights.

## Admin backoffice sidebar

Object/task-oriented internal nav (Unfold app list + custom links):

- Content/config groups
- Records/tools (per app)
- Maintenance areas
- Support utilities
- Data/admin utilities

## Tenant sidebar

Runtime-driven module visibility and grouping:

- Core operations (dashboard, today)
- People / academics (students, teachers, classes, evals)
- Finance (invoices, payments, reconciliation)
- Communication (messages, announcements)
- Reports (transcripts, report cards, analytics)
- Settings / config (school, profile, feature control)
- Installed apps / extensions

Role shells filter this list so Teacher sees class/attendance/grade/task tools; Parent sees child/progress/fees/messages; etc.

## Sidebar behavior rules

Sidebars must support:

- Nested groups
- Section collapse
- Favorites/pins (optional)
- Recent items (optional)
- Context-sensitive secondary panels where needed
- Compact icon mode
- Clear active states
- Keyboard navigation
- Mobile sheet/drawer mode
- Low-bandwidth simplified mode (optional)

## Data source

Sidebar/nav items are generated from (not hardcoded per template):

- **Runtime:** `request.tenant_runtime` (entitlements.modules, flags, policy); tenant identity from request.school / request.tenant_ctx; user from request.user
- **Role:** ADMIN, TEACHER, PARENT, etc. (effective portal role)
- **Blueprint/policy constraints**
- **Entitlements** (runtime.entitlements)
- **Installed apps** (runtime.marketplace.installed_apps)
- **Pack assignments** (workflow/dashboard packs)

**Implementation:** Control plane → `apps.schools.control_plane_nav.build_control_plane_nav(request)`; tenant → `apps.siteconfig.portal_sidebar_items.build_portal_sidebar_items(request, site)`. Templates render from context (`CONTROL_PLANE_NAV`, `PORTAL_SIDEBAR_ITEMS`).

**Adding control plane nav items:** Edit `apps.schools.control_plane_nav.build_control_plane_nav`. Add a new dict to the appropriate `add_group(label, items)` call with keys `label`, `url_name` (e.g. `super:name` or a view name from manager urlconf), and optional `icon` (Bootstrap Icon class, e.g. `bi-speedometer2`). Items whose URL fails to resolve are omitted. The sidebar template renders from `CONTROL_PLANE_NAV` injected by the siteconfig context processor when `CONTROL_PLANE_SHELL` is true.

## Role-to-nav mapping (tenant)

The **tenant** sidebar is built by `apps.siteconfig.portal_sidebar_items.build_portal_sidebar_items(request, site)` and exposed to templates via the context processor as `PORTAL_SIDEBAR_ITEMS` (and pinned items). Visibility is **role-based**:

- **Teacher:** Home, Account, Communication, My Workflow, Learning Management, Human Resources, Settings (Portal Stats). No Admin Panel, People, Finance, or Analytics.
- **Parent:** Home, Account, Communication, My Workflow, Children & Learning, Performance Tracking, Portal Tools (Community, Video, Content & Documents).
- **Staff / Admin:** Full set including Support, Content & Documents, People & Access, Academic Management, Financial Management, Analytics & Reports, Admin Panel (Dashboard Layout, Feature Control, Backend Console, Workflow Center, Customizer, Site Settings, Region Configuration, Django Admin).

Each role sees a curated slice of the taxonomy groups (Work, Records, Operations, Communications, Insights, Governance, Settings, Extensions). To add or reorder items, extend `portal_sidebar_items.py` and respect the existing section order and permission checks.

## Admin theme and sidebar

Admin (Unfold) uses the **Admin theme** from `surface-themes.css` when `body.admin-ops-surface` or `html[data-surface="admin"]` is applied. The Unfold sidebar is app-based; grouping aligns with the taxonomy (Content/config, Records/tools, Maintenance, Support, Data/admin) where custom links are added. For list/detail and table interactions, use the shared table system (`table-system.css`, `.table-family`, density classes).
