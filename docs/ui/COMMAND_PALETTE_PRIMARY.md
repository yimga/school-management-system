# Command palette and search — primary navigation (9.5/10)

**Rule:** Command palette and global search are **primary** workflow navigation. Sidebar is for orientation and fallback; power users and operators go to search first.

## Implementation

- **Trigger:** `Ctrl+K` (Windows/Linux) or `Cmd+K` (Mac) from authenticated backend and portal.
- **Surfaces:** `templates/components/global_search.html` (included via dashboard header); `static/js/command-palette.js`; backend dashboard passes `command_palette` from `apps/dashboard/context.py`.
- **Primary UX:** Backend dashboard role-home shows the command center button first with badge **"Primary"** and hint **Ctrl+K** (`templates/accounts/backend_dashboard.html`); button has `aria-label="Open command palette (primary navigation)"`. Sidebar remains for orientation; search-first is explicit.
- **Behavior:** Entity search (students, invoices, etc.), quick actions, shortcuts. Permission-aware and tenant-safe.

## 9.5/10 standard

- Command palette is discoverable (hint in header: "Search… Ctrl+K").
- One primary path to "go to" and "do" is via the palette, not only sidebar.
- Page archetypes (Role Home, Setup Studio, Decision Console, Workbench, Catalog) expose primary CTA and support "one click from palette" where applicable.

## References

- `templates/components/global_search.html`
- `apps/dashboard/context.py` (`command_palette`)
- `docs/ui/PAGE_ARCHETYPES.md`
