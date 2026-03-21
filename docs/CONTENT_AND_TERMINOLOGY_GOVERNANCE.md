# Content and terminology governance

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.5.6; [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md) §10.5.6. Phase I operating discipline — one glossary, one naming registry, one terminology standard by institution type/region, one UX writing guide, one CTA hierarchy, one alert/warning language model, one empty-state/help-state system.

**Completion gate:** At least glossary and UX writing guide in place; naming/terminology and empty-state system scoped and started.

---

## 1. Product glossary

Core terms used consistently across the platform (UI, docs, and support). Use these in copy; avoid synonyms that blur meaning.

| Term | Definition | Use in |
|------|------------|--------|
| **School** | A tenant institution (K–12, higher ed, training org) with its own data, users, and configuration. | Portal, backend, Studio OS, control plane |
| **Tenant** | A school or other customer instance in the multi-tenant platform. | Control plane, ops, API |
| **Portal** | The role-based web app for parents, teachers, students, and staff (dashboard, workflow, documents, etc.). | Nav, help, onboarding |
| **Backend** | The staff/admin web app (role-home, workflow center, finance, people, etc.). | Nav, help |
| **Studio OS** | The unified shell and five work modes: Experience, Automation, Output, Launch, Control. | Nav, rail, help |
| **Role home** | The primary landing page for a role (e.g. parent dashboard, backend dashboard). | Dashboards, nav |
| **Workflow** | A defined sequence of steps (e.g. approval, automation, report run). | Automation Studio, workflow center |
| **Pack** | A packageable unit: blueprint, workflow, dashboard, policy, report, document, or theme. | Marketplace, Studio OS, control |
| **Blueprint** | A pack that defines structure (e.g. school setup, fee structure). | Launch Studio, marketplace |
| **Runtime** | The platform layer that resolves tenant behavior (settings, feature flags, entitlements). | Control, docs (internal) |
| **Guardian** | A parent or legal guardian linked to one or more students. | Portal, people |
| **Signature request** | A request for a guardian to sign a form or document electronically. | Portal, document library |
| **Document library** | School-managed documents (lifecycle, retention, signature). | Output Studio, portal |
| **Control plane** | Manager/super surfaces for domains, feature control, and system config. | Nav, console |
| **Knowledge Base** | In-product help and articles (KB). | Portal, backend, help link |

**Maintenance:** Add terms when new product areas ship. Keep definitions to one sentence. Technical glossary (metadata, lineage, catalog) lives in [metadata_catalog_scope.md](metadata_catalog_scope.md) and metadata app (GlossaryTerm, seed_business_glossary) where applicable.

---

## 2. UX writing guide

### 2.1 Tone and voice

- **Clear and direct:** Short sentences; active voice; one idea per sentence where possible.
- **Role-appropriate:** Parent/student copy is simple and reassuring; staff/admin can use precise terms (e.g. "suspense queue", "rollback").
- **Global-first:** Avoid region-specific idioms; use "school" not "institution" unless context requires it; currency and date formats follow tenant/region.
- **No blame:** Error and empty states explain what happened and what to do next; avoid "you failed" or "error on your side."

### 2.2 Primary CTA hierarchy

- **Primary action:** One per context (e.g. "Save", "Publish", "Add student"). One prominent button (solid primary style).
- **Secondary actions:** "Cancel", "Back", "See all" — outline or text style; do not compete with primary.
- **Tertiary / overflow:** "More" (vertical dots) or links for less common actions; no button gardens (see [DESIGN_SYSTEM_BEHAVIOR.md](DESIGN_SYSTEM_BEHAVIOR.md)).

### 2.3 Buttons and links

- **Buttons:** Use for actions (Submit, Save, Create request). Label with a verb: "Save changes", "Request signature".
- **Links:** Use for navigation. Can be inline ("Back to dashboard") or in nav. Do not use "Click here"; use the destination name or action.

### 2.4 Alerts and warnings

- **Success:** Short confirmation (e.g. "Request sent."). Dismissible or auto-dismiss after a few seconds.
- **Warning:** Explain what might go wrong and what the user can do (e.g. "This will affect all students in the term. Review before publishing.").
- **Error:** State what went wrong and the next step (e.g. "Could not save. Check required fields and try again.").
- **Info:** Neutral tip or context (e.g. "Signatures are sent by email; parents can also sign from the portal.").

Avoid generic "An error occurred." Prefer: "We couldn't save your changes. Please check the form and try again."

### 2.5 Empty states

- **Pattern:** Icon + short title + one-sentence explanation + primary action when there is a clear next step (see [EMBEDDED_HELP_AND_EMPTY_STATES.md](EMBEDDED_HELP_AND_EMPTY_STATES.md)).
- **Title:** "No [X] yet" or "No [X] found" (e.g. "No invoices yet", "No pending signatures").
- **Message:** Why it’s empty and what will make data appear, or what the user can do next.
- **Action:** When there is a clear next step, provide a direct link (e.g. "Add your first student", "Generate fees"). Use `templates/components/dashboard_empty_state.html` for consistency.

### 2.6 Help and learn more

- **Global help:** Header/sidebar link to Knowledge Base (`kb:kb_home`). Topic-specific links: `?topic=invoices`, etc.
- **Inline help:** Form help text and tooltips for complex fields; avoid long paragraphs in the main flow.

### 2.7 Inclusive terminology and imagery (N23)

- **North-star N23:** Use diverse, respectful language and imagery; avoid idioms and defaults that exclude regions or family structures.
- **Implementation checklist:** [N23_INCLUSIVE_TERMINOLOGY_AND_IMAGERY.md](N23_INCLUSIVE_TERMINOLOGY_AND_IMAGERY.md) (governance + engineering patterns; sitewide copy audit is incremental).

---

## 3. Naming registry and terminology (scoped)

**Goal:** One naming registry and one terminology standard by institution type/region so the same concept is not named differently across surfaces.

**Scope (started):**

- **Naming registry:** A doc or data file that maps **concept** → **preferred label** (and optional region/institution-type overrides). Example: "fee" → "Fee" (default), "Tuition" (some regions), "School fees" (portal parent-facing). Maintain in this doc or in `docs/terminology_naming_registry.md` (to be created when overrides grow).
- **Institution type:** K–12, higher ed, training center — each may have preferred terms (e.g. "Student" vs "Trainee", "Term" vs "Semester"). Document in a table: concept, default label, K–12, higher ed, training.
- **Region:** Date, number, and currency formats are driven by RegionConfig/School.default_region. Terminology overrides (e.g. "Form" vs "Document") can be added per region when productized.

**Status:** Scoped; implementation is incremental (add registry file when first set of overrides is needed). Product glossary above is the initial preferred-label source.

---

## 4. CTA hierarchy (reference)

- **Primary:** One per page/context; verb phrase; solid primary button.
- **Secondary:** Cancel, Back, See all; outline or text.
- **Tertiary:** More menu or links; no button clutter.

See §2.2 and [DESIGN_SYSTEM_BEHAVIOR.md](DESIGN_SYSTEM_BEHAVIOR.md) action bars.

---

## 5. Alert/warning language model (reference)

- Success: confirmation, short.
- Warning: what might go wrong + what to do.
- Error: what went wrong + next step; no blame.
- Info: neutral tip or context.

See §2.4.

---

## 6. Empty-state and help-state system (scoped)

**Existing:**

- **Empty state:** [EMBEDDED_HELP_AND_EMPTY_STATES.md](EMBEDDED_HELP_AND_EMPTY_STATES.md) defines the pattern and `templates/components/dashboard_empty_state.html`. Use for any list or dashboard that can be empty.
- **Help:** Global Help → Knowledge Base; optional topic links. Sidebar "Knowledge Base" / "Help" link.

**Scoped for expansion:**

- **Help-state:** When a feature is disabled or not yet set up, show a short message + link to setup or help (e.g. "Document library is not enabled. Ask your admin or see Help.").
- **Onboarding hints:** First-run or role-specific hints (beacons, short tips) without blocking; document in a separate runbook when productized.

**Status:** Empty-state system in place; help-state and onboarding hints scoped for future work.

---

## 7. Completion gate checklist

| Item | Status |
|------|--------|
| Product glossary | **Done** — §1 above; core terms defined. |
| UX writing guide | **Done** — §2 (tone, CTA hierarchy, buttons/links, alerts, empty states, help). |
| Naming registry | **Scoped** — §3; preferred labels in glossary; registry file when overrides grow. |
| Terminology by institution type/region | **Scoped** — §3; table and RegionConfig referenced; incremental. |
| CTA hierarchy | **Done** — §2.2, §4; aligned with DESIGN_SYSTEM_BEHAVIOR. |
| Alert/warning language model | **Done** — §2.4, §5. |
| Empty-state/help-state system | **Done** — §6; EMBEDDED_HELP_AND_EMPTY_STATES + component; help-state scoped. |

**Gate met:** Glossary and UX writing guide in place; naming/terminology and empty-state system scoped and started.
