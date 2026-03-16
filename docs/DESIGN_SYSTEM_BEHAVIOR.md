# Design system — behavior (not just components)

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.5.7 and §8.0; [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md) §10.5.7. Studio OS and all new UI must follow these behavior standards.

**Policy:** Standards for behavior as well as components. No new or materially changed page/dashboard/workflow/control is accepted unless it aligns with this doc and declares the seven decision-architecture answers (§1.8 / §8.0). **Optionals in this doc** (e.g. "optional right rail") mean "may include where applicable"; all checklist and decision-architecture requirements are **non-negotiable** per RUNMYCAMPUS §11.1.

---

## 1. Page and dashboard archetypes

Use only these standard archetypes (see RUNMYCAMPUS §8.0.3; §8.0.4):

| Archetype | Purpose | Structure |
|-----------|---------|-----------|
| **Role Home** | Primary landing for a role (e.g. backend_dashboard, parent_dashboard). | One primary question; one next-best-action area; 3–6 key metrics or cards; one trend/activity area. No junkyard. |
| **Studio Workspace** | In-shell work mode (Experience, Automation, Output, Launch, Control). | Left rail (modes); content area; optional right utility rail or contextual drawer; sticky action bar where needed. |
| **Decision Console** | Single-purpose decision surface (e.g. console domains hub, feature control). | Clear question; list or table; primary action; drill-down to detail. |
| **Operational Workbench** | Day-to-day tasks and queues (e.g. workflow center, document library manage). | Queue or list; filters; primary action; bulk actions via "More" or action bar. |
| **Catalog/Marketplace** | Browse and install (e.g. app catalog, blueprint marketplace). | Cards or list; filters; Install/Apply/Preview/Rollback; detail on drill. |
| **Record Detail** | Single entity view (e.g. student, invoice, report). | Header (title, breadcrumb); key fields; contextual actions; related list or tabs. |
| **Setup Flow** | Guided setup (e.g. link_child_wizard, onboarding). | Steps; progress; next/back; summary before submit. |

Declare archetype in template or registry (e.g. `data-page-archetype="role-home"`). See [DASHBOARD_TAXONOMY_AND_REGISTRY.md](DASHBOARD_TAXONOMY_AND_REGISTRY.md).

---

## 2. Drawers

- **Side drawer:** Slide from right (or left) for contextual detail or form; overlay or push content; close on escape or outside click; preserve scroll position of underlying page.
- **Use when:** Detail view without leaving list; filters; settings panel; audit/history.
- **Do not:** Stack more than one drawer; use full-page navigations for primary flows.

---

## 3. Wizards and multi-step flows

- **Steps:** Clearly numbered or progress indicator; "Next" / "Back"; "Submit" or "Finish" on last step.
- **State:** Current step highlighted; completed steps indicated; optional summary before submit.
- **Validation:** Inline on blur or on Next; block advance on error with clear message; do not lose entered data on back.

---

## 4. Modals

- **Use for:** Confirmations (delete, overwrite); small forms (e.g. quick add); critical warnings.
- **Behavior:** Focus trap; close on Escape; optional overlay click to close; one primary CTA; secondary "Cancel" or "Back".
- **Do not:** Use for long forms (use full page or drawer); stack modals; use for primary navigation.

---

## 5. Filter panels

- **Placement:** Left rail or collapsible panel; sticky with scrollable content.
- **Behavior:** Apply on change or "Apply" button; clear all; URL or state reflects active filters where appropriate.
- **Labels:** Clear labels; optional counts per filter value.

---

## 6. Preview panels

- **Use for:** Theme/report/document preview before publish; diff views.
- **Behavior:** Side-by-side or toggle (edit | preview); optional device/viewport switcher; no navigation away without confirm if dirty.

---

## 7. Publish flows

- **Steps:** Build/edit → Preview → Publish (and optional Rollback). Clear "Publish" / "Rollback" actions in Studio OS.
- **Confidence:** Show impact summary or diff where available; confirm before publish; success/error feedback.

---

## 8. Error and loading states

- **Loading:** Skeleton screens or spinners for content; no "Loading..." text alone. Preserve layout (no collapse).
- **Error:** Inline error message near field or action; page-level error with retry or fallback action; use platform_runtime.structured_logging (log_view_exception, log_exception_with_context) for server-side logging.
- **Empty state:** Icon + short message + primary action (e.g. "No students yet — Add first student"); never blank.

---

## 9. Action bars

- **Primary CTA:** One per context (e.g. "Save", "Publish", "Add student"); prominent.
- **Secondary actions:** "More" (vertical dots) or secondary buttons; avoid button gardens.
- **Sticky:** Sticky action bar at bottom or top for long forms or workbenches when appropriate (§8.0.1).

---

## 10. Command palette

- **Trigger:** Cmd+K / Ctrl+K or equivalent; first-class search/command layer.
- **Behavior:** Jump by intent (e.g. "Change school branding", "Configure grade reports", "Go to district analytics"); role-aware; keyboard navigable; escape to close.

---

## 11. Keyboard support

- **Minimum:** Tab order logical; Enter submits primary action; Escape closes modal/drawer/palette.
- **Optional:** Shortcuts for frequent actions (e.g. G then H for home); document in help or settings.

---

## 12. Accessibility minimums

- **Focus:** Visible focus indicator; no focus trap except in modal/drawer/palette (then trap until close).
- **Labels:** All form controls labeled; icons have aria-label or sr-only text where needed.
- **Skip link:** "Skip to main content" (or equivalent) on shell; see PHASE_H_UX_VERIFICATION.md.
- **Contrast and target size:** Meet WCAG 2.1 AA where applicable; touch targets ≥ 44px where possible.

---

## 13. Motion rules

- **Transitions:** Short (e.g. 150–250 ms) for state changes; prefer ease-out or ease-in-out.
- **Avoid:** Autoplay animation that cannot be paused; motion that is essential only for decoration should respect prefers-reduced-motion.

---

## 14. Alignment with §8.0 and Studio OS

- **One shell:** All authenticated surfaces in one AppShell/StudioShell (§8.0.1).
- **One design system:** Tokens (color, spacing, radius, typography) from THEME_CANONICAL_TOKENS or design_tokens; no ad hoc per-page styling (§8.0.5).
- **Responsive:** Flexbox/Grid; fluid containers; no fixed width/height in pixels for layout; typography via clamp() or media queries (§8.0.6).
- **Decision architecture:** Every important page/dashboard/workflow/control declares the seven answers (§1.8 / §8.0); see OPERATING_DISCIPLINE_LAYERS.md.

**Completion gate (§10.5.7):** Design-system-behavior doc exists; §8.0 and Studio OS aligned to it; new UI must follow it. **Status:** This doc defines behavior standards; alignment is enforced via Phase I and §8.0 acceptance criteria.
