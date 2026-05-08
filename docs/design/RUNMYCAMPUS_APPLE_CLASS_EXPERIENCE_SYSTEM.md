# RunMyCampus Apple-Class Experience System

Status: **ACTIVE STANDARD**

This standard translates the product goal into enforceable UI rules: calm clarity, deference to school content, layered depth, direct manipulation, accessibility, and honest readiness.

## 1. Core Principles

- **Clarity:** every page has one purpose, one primary action, one visual summary, and plain status language.
- **Deference:** chrome recedes. School data, risks, approvals, timelines, and next actions dominate.
- **Depth:** layers communicate hierarchy through command bars, drawers, overlays, timelines, and progressive disclosure.
- **Direct manipulation:** prefer inline edit, slide-over review, quick approve/reject, filtered drill-ins, and bulk trays over page hopping.
- **Honesty:** payment, certification, Render parity, PSP, settlement, and customer-readiness claims require external proof.
- **Accessibility:** keyboard, focus, contrast, labels, reduced motion, and mobile zoom are product requirements.

## 2. Typography Scale

- Page title: 32-40px equivalent, used once per page.
- Section title: 20-24px equivalent, used for work zones.
- Card title: 16-18px equivalent, compact and scannable.
- Metadata: 13-14px equivalent, never below accessible readability.
- Letter spacing stays normal. Do not scale type with viewport width.

## 3. Spacing Scale

- Dense work surfaces use 8px internal rhythm.
- Page zones use 16-24px rhythm.
- Command strips and rails keep 12-16px gaps.
- Mobile stacks preserve tap targets of at least 44px.

## 4. Surface And Layer System

- **Base canvas:** quiet page background and content-first layout.
- **Primary work layer:** page hero, command strip, readiness/risk summary.
- **Floating layer:** glass command bar, action rail, quick profile drawer, approval drawer.
- **Context layer:** timeline, dependency graph, audit history, field mapping.
- **Modal layer:** destructive confirmation only; not for routine browsing.

## 5. Liquid Glass Rules

- Use glass only for floating command surfaces, drawers, context panels, and navigation.
- Do not place long paragraphs on highly translucent glass.
- Preserve contrast with solid fallback color and visible border.
- Never stack glass cards inside glass cards.
- Reduced motion must disable transitions and animated depth changes.

## 6. Card Hierarchy

- Product moment cards show outcome, status, and action.
- Metric cards show one number and one interpretation.
- Risk cards show severity, owner, why blocked, and next step.
- Empty states explain the state and provide a real next action.
- Advanced cards live behind details, drawers, tabs, or search.

## 7. Role Accents

- Platform operator: blue accent for command and proof.
- School admin: green accent for readiness and setup.
- Teacher: violet accent for classroom workflow.
- Family/parent: teal accent for child context and communications.
- Student: amber accent for progress and schedule.
- Buyer/procurement: slate accent for trust and evidence.

Accents support wayfinding; they do not replace status colors.

## 8. Status Language

- Use short, literal states: Ready, Needs review, External required, Blocked, Scheduled, Applied, Rollback available.
- Never imply live payment, certification, Render parity, or settlement readiness without proof.
- Every blocker includes owner and next step.

## 9. Motion And Microinteraction

- Motion communicates location, expansion, and completion.
- Use short, subtle transitions below 180ms.
- Do not animate critical risk language.
- Support `prefers-reduced-motion: reduce`.

## 10. Accessibility Requirements

- Preserve skip links.
- Use semantic headings in order.
- Provide visible focus states.
- Label icon-only controls.
- Use `aria-expanded` for drawers/disclosure.
- Use `role="meter"` for meters.
- Use captions for data tables.
- Trap focus in modal/drawer flows where JavaScript activates them.
- Keep contrast readable on glass layers.

## 11. Mobile Rules

- No horizontal overflow.
- Stack command strip, hero, risk rail, and module cards.
- Sticky primary action is allowed only when it helps the current task.
- Drawers become full-width panels.
- Forms are grouped into steps.

## 12. Low-Click Interaction Rules

- Inline edit for simple scalar fields.
- Quick profile drawer for student, tenant, invoice, app, and change request context.
- Side-panel approve/reject for governed changes.
- Click metric to open a filtered view, not a generic dashboard.
- Bulk action tray for repeated operational tasks.
- Command palette can expose secondary modules without link walls.

## 13. Page Anatomy

Above fold:

1. Hero with page purpose.
2. Command summary strip.
3. Primary action.
4. Risk/action rail.
5. Recent activity or timeline preview.

Below fold:

1. Details.
2. Secondary modules.
3. Advanced configuration.
4. Raw fallback links only when necessary.

## 14. Certification Standard

Apple-class readiness requires:

- Targeted component and route tests.
- `manage.py check`.
- Marketing smoke.
- Route, security, tenant isolation, design-system, shell, North Star, kill-test, doc-density, and SOT evidence verifiers.
- Local browser QA with desktop/mobile/console/overflow/accessibility results.
- Authenticated protected-route QA before claiming local ready.
- Render/deployed SHA proof before claiming Render ready.
