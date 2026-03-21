# N7 — Progressive disclosure & one primary action (§0.4.4)

**Bar:** Each important surface exposes **one** obvious primary action; secondary actions are grouped or deferred to drawers, palette, or “More”.

## Product rules

1. **Primary CTA:** One filled button (e.g. `btn-primary`) per viewport “task block” — save, submit, continue.  
2. **Secondary:** `btn-outline-*` or link-style; no more than **3** visible secondaries without collapse.  
3. **Studio / control plane:** Use `studio_os/components/page_header.html` + `data-page-archetype` per CONTROL_PLANE doc.  
4. **Tables:** Row actions → dropdown or icon menu if >2 actions per row.

## Implementation checklist (for new pages)

- [ ] Identify the **main outcome** of the page in one sentence.  
- [ ] Map that outcome to **one** `btn-primary` (or equivalent).  
- [ ] Move configuration / danger zone below the fold or into tabs.  
- [ ] Command palette (`Ctrl+K`) lists heavy flows so deep nav is optional.

## Evidence in repo

- Role-home + contextual actions: `apps/dashboard/role_home_engine.py`, `action_registry.py`.  
- Phase H / page archetypes: `RUNMYCAMPUS` §8.0.3, §6.14.
- **Ops POS (Wave 4):** `templates/schoolops/ops_pos.html` — one **`btn-primary`** (“Save line”); hub back-link is secondary; history is read-only table.
- **Compliance erasure:** `templates/compliance/erasure_request.html` — single primary submit for the GDPR Art. 17 request form.

**SOT:** N7 remains **partial** until a full template audit; this doc is the **definition of done** for new work.
