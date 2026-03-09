# Manager (manager.runmycampus.com) — Fewer clicks, faster, easier

This doc audits the manager experience and lists changes (done and suggested) so operators spend less time clicking and more time doing.

---

## Done (this pass)

| Change | Where | Effect |
|--------|--------|--------|
| **Hero chips are links** | Super dashboard hero | "Open incidents N" and "Attention tenants N" go straight to incident console / command center (1 click instead of scroll + find button). |
| **Queue card headers are links** | Super dashboard queue board | Click "Pending approvals", "Platform incidents", "Billing exceptions", or "Support and provisioning" header → one click to the right console. No need to scroll to "Open …" at bottom. |
| **Queue panel stats are links** | Super dashboard Queue board panel | "Pending approvals N", "Support backlog 48h+ N", "Provisioning breaches N" in the panel header link to command center. |
| **Shortcuts button in navbar** | Control plane base | "? Shortcuts" in header opens keyboard help so users discover **g d** (dashboard), **g c** (command center), **Ctrl+K** (search), etc. |
| **Chip/link hover** | manager-control-plane.css | `a.cp-chip` and `a.cp-queue-card-header` have hover so it’s obvious they’re clickable. |

---

## Already in place (keep using)

- **Landing**: manager.runmycampus.com → redirect to `/super/` (or login). One step.
- **Navbar**: Brand → dashboard; Search (Ctrl+K) → tenants/incidents/billing; Config Engine → admin; User menu → profile, preferences, logout.
- **Hero actions**: Provision tenant (primary), Queues, Billing, Migration, Marketplace, Incidents, Export PDF — all one click.
- **Section nav**: "Action queue", "Fleet health", etc. jump in-page; no new load.
- **Next-best-actions**: When present, single link per action.
- **Sidebar**: Pinned items, then grouped nav (Dashboard, Command Center, Tenants, …). One click per destination.
- **Search (Ctrl+K)**: Results link directly to tenant, incident, or static page; pick result = one click after typing.

---

## Suggested next (prioritized)

### High impact, low effort

| Idea | What | Where |
|------|------|--------|
| **Admin index: one-click config** | On manager, platform admin index already has Quick config chips (Site settings, Feature Control, Theme, Region, Integrations). Consider making them the first block so operators don’t scroll. | `index_superadmin.html` |
| **Command center deep link** | Optional: command center URL with `?tab=approvals` or `#approvals` so dashboard links can open the right tab. | `super_command_center.html` + view |
| **Billing from hero** | Already have "Billing" in hero; keep. Optional: make north-star stat (revenue) clickable → billing dashboard. | `super_dashboard.html` |

### Medium effort

| Idea | What | Where |
|------|------|--------|
| **Approval from list** | In "Pending approvals" list, "Approve" already does one-click approve. "Edit" goes to admin. Optional: add "View in Command Center" for context. | Super dashboard queue card |
| **Search result keyboard nav** | Let users arrow through Ctrl+K results and Enter to open (already a dropdown). | control_plane_base.html search JS |
| **Deep link to tab** | Command center could support `?tab=approvals` or `#approvals` so dashboard links open the right tab. | `super_command_center.html` + view |

### Lower priority

| Idea | What | Where |
|------|------|--------|
| **Dashboard overview cards** | Make overview cards (from `overview_cards`) clickable where it makes sense (e.g. "Tenants" → tenant health). | Super dashboard + context |
| **Breadcrumb as nav** | Breadcrumbs already exist; ensure they’re used for quick back (e.g. Command Center → Dashboard). | Already in place |
| **Pinned default** | Consider pinning "Command Center" and "Billing" by default for new users so they’re always at top of sidebar. | control_plane_nav.py or preferences |

---

## Click-count snapshot (after changes)

| Task | Before | After |
|------|--------|--------|
| Open incident console | 1 (hero "Incidents" button) or scroll + "Open incident console" | 1 (hero "Open incidents N" chip or queue card header) |
| Open command center | 1 (hero "Queues") | 1 (hero "Queues" or "Attention tenants N" chip or any queue card header) |
| Open billing | 1 (hero "Billing") | 1 (hero "Billing" or "Billing exceptions" card header) |
| Provision tenant | 1 (primary button) | 1 |
| Go to Configuration Engine | 1 (navbar or sidebar) | 1 |
| Discover shortcuts | Unknown | 1 (click "? Shortcuts" in navbar) |

---

## References

- Control plane nav: `apps/schools/control_plane_nav.py`
- Manager URLs: `config/manager_urls.py`
- Super dashboard: `templates/schools/super_dashboard.html`
- Control plane base (navbar, shortcuts): `templates/control_plane_base.html`
- Admin index (manager): `templates/admin/index_superadmin.html`
