# Stage 8 — Configuration & Metadata Settings Engine Body Audit

**Pack:** `2026-05-20-orchestrator-v5`
**Prerequisites:** `00-global-execution-rules.md`, `00-platform-wide-clause.md`, `00-moderator-addendum.md`

---

## ROLE

You are the RunMyCampus Core Configuration & Metadata Settings Engine UX Engineer.

## MISSION

Audit the platform-wide Django dashboard bodies and redesign the **Core Configuration & Metadata Settings Engine body**. Inspect the **Day-to-Day Operations Workspace body** only to identify the specific body-level surfaces that need improvement. Map every fix for the engine body and document the operations body gaps for future platform-wide correction.

---

## FOCUS

- Primary focus: `Core Configuration & Metadata Settings Engine body`
- Secondary audit: `Day-to-Day Operations Workspace body` only for surfaces that need improvement
- Do not redesign sidebars, headers, or footers
- Treat the work as platform-wide across tenant and operator surfaces
- Ensure the prompt is thorough and body-surface centric

---

## TASKS

1. Find every existing configuration engine page and body surface in the Django app.
2. Audit each configuration body surface for:
   - runtime metadata field builder experience
   - grading and formula matrix presentation
   - PPP invoicing and local pricing matrix clarity
   - school-year branching and lifecycle control
   - body-surface consistency, simplicity, and full-width usage
3. Audit the Day-to-Day Operations Workspace body only to identify weak or broken body surfaces.
4. Map the exact fixes needed for the configuration engine body, including missing or overloaded body panels.
5. Render browser-ready HTML mockups for the configuration engine body.
6. Provide before/after comparisons for the body surfaces.
7. Wait for approval before implementation.

---

## DESIGN PRINCIPLES

- keep the engine body clean, simple, and creative
- use space intelligently and fully
- avoid rigid form page layouts inside the body
- no hidden content, no blur, no blocking overlays
- body surfaces must feel like a programmable control panel, not a static page
- make the configuration body platform-grade for tenant and operator contexts

---

## PROMPT

> Audit the Django dashboard bodies and redesign the page bodies with a platform-wide focus on the **Core Configuration & Metadata Settings Engine body**. Do not change sidebars, headers, or footers. Focus entirely on the body content and inner-shell surfaces.
>
> Start by finding every configuration engine page body and identifying the body-level surfaces that power runtime metadata, tenant settings, grading formulas, PPP invoicing, and school-year lifecycle control. Then audit the Day-to-Day Operations Workspace body only to identify body surfaces that need improvement.
>
> The primary goal is to map a fix for the configuration engine body and render browser-ready HTML mockups of those body surfaces. Provide before/after comparisons and wait for approval before changing production templates.
>
> The redesign must:
> - start with a thorough body-level audit
> - identify broken or weak configuration body surfaces
> - identify operation body surfaces that require improvement
> - plan the fix for the configuration engine body
> - render HTML mockups for the configuration body
> - provide before/after comparisons
> - wait for approval
>
> Build the configuration engine body as a world-class page canvas with:
> - runtime EAV metadata field building
> - a polymorphic grading / evaluation formula matrix
> - a localized PPP invoicing & fee matrix
> - school-year branching & lifecycle control
>
> Keep the body design:
> - consistent
> - innovative
> - imaginative
> - simple
> - full-width
> - engine-focused

---

## DEPLOYMENT

Use this prompt in Cursor or Claude as the audit and planning instruction for the platform-wide Django configuration engine body refactor.

> NOTE: Paste the full contents of this file directly into the agent prompt window. Do not shorten or paraphrase the instructions. This prompt is built for an exact body-level audit and configuration-engine redesign run.

---

## HANDOFF AND EXECUTION LOOP

This prompt must be run as a continuous audit-and-fix loop until the agent confirms that every body surface was inspected and corrected, especially within the Core Configuration & Metadata Settings Engine body.

1. Start with a fresh inspection of all configuration engine body templates and components. Do not stop until every page body surface related to configuration and metadata has been identified.
2. Document every gap found in the configuration engine body, including missing panels, overloaded sections, rigid form layouts, hidden content, and non-full-width designs.
3. For each gap, propose a specific body-surface fix and update the HTML/CSS/templating as needed.
4. Render browser-ready HTML mockups of the corrected configuration engine body surfaces.
5. Validate the mockups against the current platform pages and confirm before/after body-surface changes.
6. Audit the Day-to-Day Operations Workspace body only to identify the exact body surfaces that require improvement; do not redesign it unless a clear fix is required to support the configuration engine audit.
7. Repeat the audit until the final report confirms:
   - every configuration engine body surface was inspected
   - every body surface gap was mapped
   - every critical configuration engine body fix is either implemented or explicitly documented with a remediation plan
   - the body design is full-width, simple, clean, creative, and engine-focused

> Handoff instruction: this is a living audit loop. After each pass, review the remaining gaps, update the prompt artifact with findings, and continue until the configuration engine body is fully certified.

---

## EXECUTION CHECKLIST

- [ ] Inventory every configuration engine page body and component
- [ ] Identify and document every gap in the configuration engine body surfaces
- [ ] Implement body-surface fixes for runtime EAV metadata, formula matrix, PPP invoicing, and year branching
- [ ] Render browser-ready configuration engine body mockups
- [ ] Compare before/after body surfaces and include visible validation notes
- [ ] Inspect the Day-to-Day Operations Workspace body only for supporting surface gaps
- [ ] Confirm the final engine body design is full-width, clean, simple, creative, and platform-grade
- [ ] Do not advance to implementation until approval is explicit
