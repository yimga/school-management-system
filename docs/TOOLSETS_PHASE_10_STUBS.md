# Toolsets Phase 10 — Stubs & execution order (10.4–10.8)

**Purpose:** Placeholder and execution notes for Path-to-10 toolsets. Implement in phases per product priority.

---

## 10.4 Document Library

- **Lifecycle states:** Define `DRAFT`, `PUBLISHED`, `ARCHIVED` (and optional `RETRACTED`) in portal/documents or a shared constants module; apply to document or folder models where applicable.
- **Retention rules:** Configurable retention (e.g. JSON or model) per document type or folder; background task or command to enforce.
- **Document packs:** Packageable bundle of templates/samples (similar to ReportPack); optional model `DocumentPack` with slug, name, file refs.
- **Search/indexing:** Integrate with existing search (e.g. metadata_catalog, AI index) for document content; index on publish.

**Reference:** `apps/portal/views_documents.py`, document library manage view; `PHASE_10_BACKLOG.md` §10.4.

---

## 10.5 Design Studio

- **Split document vs experience design:** Document design = report cards, PDFs, layouts; experience design = theme, portal shells, branding. Clarify ownership (siteconfig vs portal vs studio_os).
- **Layout metadata and layout builder:** Store layout as JSON (sections, blocks); optional UI to compose layout (Phase 10 or later).

**Reference:** Studio OS Experience mode; theme_colors; report card styles.

---

## 10.6 Live Previews

- **Central preview service:** Single entry point (e.g. `get_preview_url(mode, context)`) that delegates to `preview_from_form` (theme), report embed, workflow preview, Setup Studio role preview. Already partially in place; consolidate in one module and document.
- **Side-by-side before/after:** UI option to show current vs preview in split view (optional).
- **Preview by role/device/tenant:** Extend preview session to support role and device; tenant = school in multi-tenant.

**Reference:** `apps/siteconfig/views.py` `preview_from_form`; `docs/PREVIEW_SYSTEM.md`; `templates/components/live_preview_button.html`.

---

## 10.7 Workflows

- **Simulation with impact counts:** `run_workflow_simulation(definition_code, payload, school)` stub in `apps/orchestration/runners.py`; extend to return step list and impact count from dry-run.
- **Workflow marketplace cards:** Display workflow packs in marketplace with status (installed, available); link to Studio Automation.
- **Versioning and replay:** Store workflow definition version on run; optional replay from audit.

**Reference:** `apps/orchestration/runners.py` `run_workflow_simulation`; workflow hub; Studio OS Automation.

---

## 10.8 AI & API

- **API contracts and contract tests:** OpenAPI or similar for public API; automated tests that assert request/response shape and error codes.
- **AI action audit trail:** Log AI gateway calls (model, tokens, user, school) in existing AIGatewayMetric or dedicated audit table; expose in control-plane or support dashboard.

**Reference:** `apps/api/`, `services/ai_gateway.py`, `apps/siteconfig/models_ai.py` AIGatewayMetric.

---

## Implementation order (suggested)

1. **10.6** — Central preview service (document and wire existing preview entry points).
2. **10.4** — Document lifecycle states (constants + optional migration).
3. **10.7** — Workflow simulation impact count (extend stub).
4. **10.8** — AI audit (ensure AIGatewayMetric is written and visible).
5. **10.5** — Design Studio split (ownership doc + layout JSON schema).

---

**Backlog:** `docs/PHASE_10_BACKLOG.md`, `docs/PHASE_10_NEXT_STEPS.md`.
