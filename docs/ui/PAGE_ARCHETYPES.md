# Page archetypes and contribution checklist

All Tier 1/2 pages should conform to one of five **page archetypes** and pass the **5-question test**. This keeps the product outcome-first, role-native, and visually consistent.

---

## Five archetypes

### 1. Role Home

**Purpose:** Primary landing for a role (e.g. Backend dashboard, Admin index, Control plane).

**Layout:** Single dominant insight zone, one primary action band, 3–6 KPIs, one urgent queue, one recommended block. Optional sidebar for navigation/secondary actions.

**Examples:** `backend_dashboard.html`, admin index, super dashboard.

**Contract:** `dashboard_intent`, `primary_ctas`, `overview_cards` or equivalent, `recommended_next_steps`, `command_palette` or "More actions".

---

### 2. Setup Studio

**Purpose:** Guided setup/onboarding with progress and a clear next step.

**Layout:** Progress rail (left), current step or step list (center), tips or live preview (right). Top: setup health score and recommended next action.

**Examples:** `guided_onboarding.html` (Setup Studio).

**Contract:** `steps`, `setup_health_score`, `recommended_next`, outcome-labeled steps, "Do it" / "Done" per step.

---

### 3. Decision Console

**Purpose:** Choose an option (e.g. blueprint, app, plan) with preview and impact before committing.

**Layout:** Category filters, search, recommendation rail, card listing, **preview panel** before install/apply, install flow with compatibility/impact summary.

**Examples:** App catalog, Blueprint marketplace.

**Contract:** Outcome-first labels ("Get parent portal" not "Install app X"), preview action, apply/install with impact summary.

---

### 4. Operational Workbench

**Purpose:** Work through a queue of items (migrations, policies, approvals) with filter, list, and detail.

**Layout:** Top status bar, filter/search, work queue, detail panel, action drawer. One primary action per screen.

**Examples:** Migration wizard, policy config, approval queues.

**Contract:** See [OPERATIONAL_WORKBENCH.md](OPERATIONAL_WORKBENCH.md).

---

### 5. Catalog / Marketplace

**Purpose:** Browse and install/add items (apps, blueprints, integrations).

**Layout:** Same as Decision Console; may emphasize categories, search, and "Compare" where applicable.

**Contract:** Search/filter, card listing, preview, compatibility/impact, single primary CTA per item.

---

## 5-question test

Before shipping a new or heavily changed page, confirm:

1. **What problem does this page solve?** — One sentence; visible in hero or title.
2. **What matters most right now?** — One dominant insight or primary CTA band.
3. **What is the primary next action?** — One obvious button or link (e.g. "Do it", "Install", "Apply").
4. **What can I do in one click?** — Key actions are 1–2 clicks from this page.
5. **What should I not have to click for?** — No hunting; critical info and next step are visible.

---

## Contribution checklist

When adding or refactoring a page:

- [ ] Page maps to one of the five archetypes above.
- [ ] It passes the 5-question test.
- [ ] Outcome-first language (user goals, not module names).
- [ ] Primary CTA is obvious; secondary actions grouped or in "More".
- [ ] Uses shared design tokens / `platform-high-end.css` where applicable (cards, CTAs, empty states).
- [ ] No new page without conforming to an archetype and this checklist (document in PR).

---

## Reference

- UX plan: `docs/` (UX Workflow and High-End UI Transformation).
- Workbench pattern: [OPERATIONAL_WORKBENCH.md](OPERATIONAL_WORKBENCH.md).
- Dashboard context and action registry: `apps/dashboard/context.py`, `apps/dashboard/action_registry.py`.
