# Tenant-first layout balance audit and rollout prompt

Use this prompt only after an HTML approval artifact has been accepted. Audit first; never begin with bulk CSS changes.

## Objective

Audit every tenant surface and then every operator surface for visual imbalance, unused horizontal space, left-heavy composition, repetitive card rows, orphan controls, and excessive floating UI. Preserve local-first and offline behavior, permissions, tenant isolation, accessibility, localization, and existing workflows.

The result must feel creative, calm, balanced, simple, and operationally dense without becoming crowded. “Full width” does not mean stretching prose or tables beyond readable limits. It means the available canvas has an intentional composition at every supported viewport.

This is a **professional cleanup and alignment program, not a redesign or rebuild**. Preserve the page's information architecture, surfaces, labels, buttons, links, statuses, tabs, forms, workflows, and user capabilities unless a separately approved change explicitly authorizes removal or restructuring. Improve the existing page by resizing, aligning, wrapping, spanning, grouping, spacing, and polishing what is already there.

## Mandatory execution order

1. Inventory before editing.
2. Measure and classify every page.
3. Group pages by shared template, component, CSS primitive, and page archetype.
4. Produce representative HTML approval prototypes for each affected archetype.
5. Stop for explicit visual approval.
6. Implement shared primitives first, then surgical page exceptions.
7. Test desktop, laptop, tablet, phone, keyboard, screen reader, light theme, dark theme, localization expansion, offline mode, empty state, sparse data, and dense data.
8. Re-audit the complete inventory using the same measurements.
9. Fix all remaining applicable failures.
10. Re-run tests and publish before/after evidence plus an exception ledger.

## Audit scope

Start with tenant pages: role homes, setup and onboarding, finance, fees and payments, payroll, HR, students, guardians, teachers, attendance, grading, timetables, communications, reports, analytics, configuration, workflows, approvals, documents, help, profile, and tenant Django-admin surfaces. Then audit operator/control-plane, Studio, super-admin, and public authenticated utility surfaces.

For every rendered route and meaningful state, record:

- route, role, permission set, tenant, archetype, template, shared includes, and CSS bundles;
- viewport at 1920×1080, 1536×864, 1366×768, 1024×768, 768×1024, 390×844, and 320×568;
- main-canvas width and occupied-content width above the fold;
- left and right unused-space ratio, excluding intentional shell rails;
- visual center of mass and whether the page is left-heavy, right-heavy, or balanced;
- number of visible surfaces, nested surfaces, buttons, icon-only actions, fixed/sticky/floating controls, and duplicated actions;
- grids with an incomplete final row, fixed column counts, narrow intrinsic cards, arbitrary max-widths, or content that stops before the canvas edge;
- buttons sitting alone in their own row/surface, button gardens, detached filters, duplicate tabs, and actions separated from the content they affect;
- cards containing only a title and button that could become a row, split action, menu item, inline card footer, toolbar action, or contextual command;
- empty surfaces, empty right columns, excessive vertical gaps, oversized hero regions, and nested borders that add no information hierarchy;
- whether KPI groups compare cleanly, have equal visual weight, and use available width without stretching values unnaturally;
- data table readability, form line length, text line length, chart aspect ratio, and scan path;
- focus order, 44px touch targets, labels, contrast, zoom at 200%, reduced motion, and RTL readiness;
- offline behavior and whether any layout interaction requires a network response to reveal essential controls.

## Quantitative failure rules

Flag a page for human review when any rule applies:

- occupied main-canvas width is below 78% on desktop without a documented reading-width reason;
- left/right unused-space differs by more than 12% of the canvas;
- a major grid leaves more than one card-width empty while cards remain narrower than 360px;
- an incomplete grid row is left aligned when balanced spanning, centering, or a deliberate asymmetric companion panel would be clearer;
- a standalone action consumes a separate vertical band of 48px or more;
- more than one global floating action cluster is visible, or a fixed control duplicates navigation/action available in the shell;
- more than seven peer actions are simultaneously exposed without grouping or prioritization;
- three or more visually equal surfaces are nested inside another undifferentiated surface;
- the same action appears twice within one viewport;
- a KPI/card group uses less than 70% of its parent width while the parent has no meaningful secondary content;
- a desktop composition simply stacks full-width bands when two related bands can form a useful 2:1, 3:2, or bento relationship;
- mobile produces horizontal scrolling, clipped controls, reordered meaning, or floating controls covering content.

Thresholds find candidates; they do not authorize blindly stretching content. Reading surfaces may remain narrow when centered and paired with useful context, navigation, status, or intentional negative space.

## Required remediation hierarchy

Apply the smallest reusable solution in this order:

1. Use `auto-fit` / `minmax()` or named responsive grid templates instead of fixed desktop column counts.
2. Let the last item span a meaningful remainder, center the last row, or pair it with related context; never leave an accidental void.
3. Integrate actions into the header, card footer, row, filter bar, or overflow menu of the object they affect.
4. Replace button gardens with one primary action, up to two contextual secondary actions, and a labeled overflow menu.
5. Consolidate floating utilities into one edge dock owned by the shell; allow at most one context-sensitive page action.
6. Remove decorative wrapper surfaces and redundant borders before adding new cards.
7. Use asymmetric bento layouts only when hierarchy is real: urgent work or the next action gets more area than passive KPIs.
8. Preserve readable measure for prose and forms; balance the remaining canvas with related summaries, progress, help, or preview rather than stretching text.
9. Use empty space deliberately around a focal point, never as an accidental remainder caused by width caps or fixed grids.
10. Prefer shared archetype/component changes; document every page-specific exception.

## Prohibited shortcuts

- Do not solve balance with `text-align:center` everywhere.
- Do not stretch every card to equal height when content hierarchy differs.
- Do not add decorative cards merely to fill space.
- Do not hide essential actions in an unlabeled icon.
- Do not move page actions into a global floating dock when they are contextual.
- Do not remove whitespace needed for comprehension.
- Do not alter routes, permissions, tenant boundaries, offline queues, form semantics, or business behavior for visual convenience.
- Do not rebuild a page, invent a replacement dashboard, remove a button, hide an existing action in overflow, merge distinct workflows, rename labels, or change information architecture under the authority of this cleanup prompt.
- Do not infer that a visually duplicated control is functionally redundant. Verify its destination, permission context, state, and responsive role before proposing consolidation; retain it until separately approved.
- Do not claim tenant-wide completion from a sample of routes.

## Evidence and acceptance gate

Deliver a machine-readable inventory and a human-readable report with each route marked `pass`, `fixed`, `intentional exception`, or `blocked`. For every shared change provide before/after screenshots at desktop and mobile, computed measurements, affected route count, keyboard/a11y results, visual-regression results, and offline results.

Completion requires:

- 100% of discovered in-scope routes classified;
- zero unexplained high-severity failures;
- zero duplicate global floating clusters;
- zero orphan-action bands unless documented as intentional;
- no regression in permissions, tenant isolation, local-first/offline flows, themes, localization, accessibility, or mobile behavior;
- a second independent scan after remediation with the same route/state matrix;
- all documented exceptions named, justified, and approved.
