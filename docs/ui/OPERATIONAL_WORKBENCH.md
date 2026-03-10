# Operational workbench pattern

Use this layout for migration wizards, policy/config workbenches, and any page where users work through a queue of items with filters and a primary action.

## Structure

1. **Top status bar** — One line: counts (e.g. "12 pending, 3 in progress"), environment or scope, optional "Refresh".
2. **Filter / search** — Clear controls to narrow the work queue (status, date range, school, type). Prefer a single visible search or filter row.
3. **Work queue** — List or table of items (migrations, policy rules, requests). One primary action per row (e.g. "Run", "Apply", "Review"). Secondary actions in an overflow (⋮) or "More".
4. **Detail panel** — When user selects an item, show details in a side panel or below the list. Keep the primary action obvious (e.g. "Confirm", "Approve").
5. **Action drawer** — For multi-step or destructive actions, use a slide-out or modal drawer with: summary, impact, and a single primary button (e.g. "Apply", "Rollback").

## Principles

- **One primary action per screen** — The next thing the user should do is obvious.
- **Few steps** — Minimize clicks to complete a task (filter → select → act).
- **Preview before commit** — Where changes are significant, show impact/compatibility before Apply.

## Where to use

- Migration wizard (data migration runs, status, rollback).
- Policy/config workbench (policy bundles, overrides, apply/rollback).
- Approval queues (access requests, finance requests) with list + detail + approve/reject.

## Reference

- Blueprint marketplace: catalog list + Preview + Apply + Rollback panel.
- App catalog: list + compatibility/impact panel + Install.
- **Migration Profile Registry** (`schools/super_migration_profile_registry.html`): status bar (profile/group counts, Refresh), work queue with primary action "Use in Cloud" per row; conforms to this pattern.
