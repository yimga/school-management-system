# Improvements Runbook — Uninterrupted Execution

**Purpose:** Execute all listed improvements in order with **no interpretation and no approval gates**. Each step is a concrete action plus verification. Run from top to bottom; do not skip. When context or time limits apply, update the session state at the end of the last completed step and resume from the next step.

**Authority:** This runbook extends [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md) and [RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md](RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md). All steps are code or config changes; no new plan docs. Verification is by script, test, or explicit check only.

**Ultra high-end without compromise:** Every change must be **ultra high-end** — no shortcuts or placeholder quality. SOT §8.0 and §8.0.11 define the bar; apply it to all implementations in this runbook.

**Session state:** `docs/IMPROVEMENTS_RUNBOOK_SESSION_STATE.md` — at end of run (or when pausing), set `Last completed step:` and `Next step:` so the next run continues without redoing work.

---

## 1. Enforcement and gates

### Step 1.1 — Wire §10.5 layers into pre-deploy gate

- **Action:** In `scripts/pre_deploy_gate.sh`, after the line that runs `python scripts/verify_operating_discipline_docs.py`, add:
  - `echo "[pre_deploy_gate] §10.5 operating-discipline layers (doc + code)"`
  - `python scripts/verify_section10_5_layers.py`
- **Verify:** Run `bash scripts/pre_deploy_gate.sh` (or `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh`); gate must pass. Then run `python scripts/verify_section10_5_layers.py` alone; exit code must be 0.

### Step 1.2 — Lint: marketing nav overflow (no horizontal scroll)

- **Action:** Add a script `scripts/lint_marketing_nav_no_overflow.py` that:
  - Reads `apps/schools/marketing_views.py` and finds `_marketing_navbar_primary()` (or the list of primary nav items).
  - Checks that the number of items is either ≤ 7, or that the template/context uses a "More" (or similar) pattern so that at most 7 items are rendered as top-level links (e.g. by checking for `marketing_navbar_has_more` or a dropdown for overflow).
  - Exit 0 if OK; exit 1 with a short message if the nav would overflow (e.g. more than 7 top-level items without overflow handling).
- **Wire:** Add to `scripts/pre_deploy_gate.sh`: `echo "[pre_deploy_gate] Marketing nav no overflow"` and `python scripts/lint_marketing_nav_no_overflow.py`.
- **Verify:** Run `python scripts/lint_marketing_nav_no_overflow.py`; exit 0. Then run the full gate; it must pass.

---

## 2. Scroll-storytelling and marketing

### Step 2.1 — Chapter indicator (subtle) on landing

- **Action:** In `templates/schools/marketing_landing.html`, add a chapter indicator (e.g. a row of dots or short labels for Hero, Why switch, Platform, … Final CTA) that:
  - Is inside the same scroll-story container (e.g. fixed or sticky below the progress bar).
  - Uses `data-chapter` on sections (already present where applicable); add JS that on scroll updates the active chapter (e.g. adds a class to the current dot/label).
  - Respects `prefers-reduced-motion` (no animation or instant update only).
- **Files:** Add minimal CSS in `static/css/marketing-home-scroll.css` for the indicator (e.g. `.mkt-chapter-indicator`, `.mkt-chapter-dot`, `.mkt-chapter-dot.active`). Add JS in `static/marketing/js/marketing-landing-scroll.js` (or a small inline block in the landing template) to observe scroll position and set the active chapter.
- **Verify:** Load the marketing landing; scroll through sections; the chapter indicator must highlight the current section. With `prefers-reduced-motion: reduce`, indicator still updates without animation.

### Step 2.2 — Hero “wakes up on scroll”

- **Action:** In the marketing landing hero section, add a light scroll-driven effect on the hero visual (e.g. opacity or scale change as the user scrolls past the hero), so the hero feels responsive to scroll. Implement in JS (e.g. in `marketing-landing-scroll.js`): on scroll, compute a 0–1 factor from scroll position relative to hero height and apply a CSS variable or class (e.g. `--hero-reveal` or `.hero-scrolled`) to the hero visual container. Use `transform` and/or `opacity` only; respect `prefers-reduced-motion` (no transform/opacity change when reduced).
- **Verify:** Load landing; scroll down from hero; hero visual must change subtly (e.g. slight fade or scale). With reduced motion, no such change.

### Step 2.3 — Pinned product frame on landing for key chapters

- **Action:** For at least two key chapters on the landing (e.g. “Platform architecture” and “Studio OS” or “Migration”), use the same pinned right-hand product frame pattern as on the product page: copy left, sticky visual right on desktop. Reuse classes from `static/css/marketing-home-scroll.css` (e.g. `.mkt-chapter-pinned`, `.mkt-chapter-copy`, `.mkt-chapter-visual`). Ensure the landing sections that map to directive chapters 3, 5, or 7 have the two-column sticky layout on `min-width: 992px`.
- **Verify:** Load landing on desktop (≥992px); scroll to platform/Studio/Migration sections; one column must stay sticky while the other scrolls. On mobile, layout stacks (no heavy pinning).

---

## 3. Control plane and super

### Step 3.1 — Single constant for “visible nav count” (marketing)

- **Action:** Introduce one source of truth for how many marketing nav items are shown before “More”:
  - In `apps/schools/marketing_views.py`, define a module-level constant, e.g. `MARKETING_NAVBAR_VISIBLE_COUNT = 7`. In `_marketing_context`, set `marketing_navbar_has_more` to `len(nav_primary) > MARKETING_NAVBAR_VISIBLE_COUNT`. When building the list for the template, pass the same constant (e.g. as `marketing_navbar_visible_count`) in the context so the template can loop `{% for item in marketing_navbar_primary %}` with `forloop.counter <= marketing_navbar_visible_count` for the main row and `forloop.counter > marketing_navbar_visible_count` for the More dropdown.
  - In `templates/marketing/marketing_header.html`, replace the hardcoded `7` with `marketing_navbar_visible_count` (or the constant value from context).
- **Verify:** Change `MARKETING_NAVBAR_VISIBLE_COUNT` to 6; run the app and load a marketing page; only 6 items in the main row and the rest in More. Revert to 7 and confirm.

### Step 3.2 — Ctrl+K focuses control-plane search

- **Action:** In the control plane base template or the script that runs on manager pages, add a global keydown listener for Ctrl+K (or Cmd+K on Mac): when fired, prevent default and focus the control-plane search input (`#cpSearchInput`). Attach in `templates/control_plane_base.html` (inline script or a small `static/js/control-plane-shortcuts.js` that is loaded on control-plane pages) so that on manager host, Ctrl+K focuses search.
- **Verify:** Open a /super/ page; press Ctrl+K (or Cmd+K); the search input must receive focus.

---

## 4. Performance and resilience

### Step 4.1 — Progressive enhancement: sections visible without JS

- **Action:** Ensure that when JS is disabled or fails, marketing landing and product scroll sections are still visible (no content hidden). Add a fallback: in the template, add a `<noscript>` block that applies a class or style to reveal all `.mkt-reveal` and `.mkt-reveal-stagger` (e.g. add a `<style>.marketing-home .mkt-reveal, .marketing-home .mkt-reveal-stagger > * { opacity: 1; transform: none; } .mkt-product-story .mkt-reveal, .mkt-product-story .mkt-reveal-stagger > * { opacity: 1; transform: none; }</style>` inside `<noscript>` on the landing and product templates). Alternatively, in the scroll CSS file, set a default state so that if the JS never adds `in-view`, the sections are still visible (e.g. reduce the initial opacity only when a `data-scroll-story` and `js-enabled` class is present, and add `js-enabled` from JS).
- **Verify:** Load landing with JS disabled (or block the scroll script); all sections must be readable and not stuck at opacity 0.

### Step 4.2 — Lazy-load and dimensions for marketing media

- **Action:** Audit `templates/schools/marketing_landing.html` and `templates/schools/marketing_product_page.html` (and any included partials) for images and iframes. Ensure every image below the fold has `loading="lazy"` and explicit `width` and `height` (or CSS aspect-ratio) so layout doesn’t jump. Add missing attributes where absent.
- **Verify:** Run a quick grep for `<img` in those templates; each must have `loading="lazy"` (or `loading="eager"` for above-the-fold hero only) and width/height. Optionally run a lint script that checks for `<img` without width/height in marketing templates; fix any reported.

---

## 5. Accessibility and UX

### Step 5.1 — Skip link target focusable

- **Action:** In `templates/schools/marketing_landing.html`, the skip link targets `#hero`. Ensure the element with `id="hero"` has `tabindex="-1"` so that when the user activates “Skip to main content”, focus moves there (and the element can receive focus). Add `tabindex="-1"` to the `<section id="hero" ...>` if not already present.
- **Verify:** Load landing; use keyboard to focus the skip link and activate it; focus must move to the hero section (no focus trap or invisible focus).

### Step 5.2 — More dropdown keyboard (marketing)

- **Action:** The “More” dropdown in `templates/marketing/marketing_header.html` uses Bootstrap dropdown. Ensure the toggle has `aria-expanded` and `aria-haspopup="true"` and that the dropdown menu is in the tab order and can be closed with Escape. Bootstrap 5 provides this by default; add a one-line comment in the template or a short note in the runbook that keyboard behavior is delegated to Bootstrap. If any custom JS overrides the dropdown, remove or adjust so that keyboard users can open/close and move within the menu.
- **Verify:** Tab to “More”, press Enter/Space to open; tab through dropdown items; press Escape to close. No keyboard trap.

---

## 6. Code and maintainability

### Step 6.1 — Shared scroll core (landing + product)

- **Action:** Extract shared logic from `static/marketing/js/marketing-landing-scroll.js` and `static/marketing/js/marketing-product-scroll.js` into a small shared module, e.g. `static/marketing/js/marketing-scroll-core.js`, that:
  - Accepts options: `rootSelector`, `progressWrapId`, `progressFillId`, `revealSelectors` (e.g. `.mkt-reveal, .mkt-reveal-stagger`).
  - Implements scroll progress bar update and Intersection Observer for reveal; respects `prefers-reduced-motion`.
  - Does not depend on a specific page structure beyond the selectors.
  - Landing and product scripts then call this core with their respective selectors and IDs (and optionally no progress bar for pages that don’t need it).
- **Verify:** Landing and product pages still show scroll progress and reveal-on-scroll; no duplicate code in the two page scripts. Run a quick test: load both pages and scroll; behavior unchanged.

### Step 6.2 — One constant for visible nav count (duplicate of 3.1)

- **Action:** This is satisfied by Step 3.1. If 3.1 is done, mark this as done (no separate action).
- **Verify:** Same as 3.1.

---

## 7. Order of execution and session state

Execute steps in this order:

1. **1.1** → **1.2** (gates)
2. **3.1** (nav constant) — then **6.2** is done
3. **3.2** (Ctrl+K)
4. **2.1** → **2.2** → **2.3** (scroll and marketing)
5. **4.1** → **4.2** (progressive enhancement and media)
6. **5.1** → **5.2** (a11y)
7. **6.1** (shared scroll core)

After each step (or at the end of a run), update `docs/IMPROVEMENTS_RUNBOOK_SESSION_STATE.md`:

- `Last completed step:` (e.g. 1.2)
- `Next step:` (e.g. 3.1)
- `Date (UTC):`
- Optional: `Done this session: [list]`

Resume the next run by reading that file and continuing from `Next step`.

---

## 8. Completion

When all steps are done:

- Run the full gate once: `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh`.
- Set session state: `Last completed step:` 6.1, `Next step:` “All complete”.
- Optionally add a one-line note in [RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md](RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md) §10 “Technical references” that the improvements runbook has been executed (no new sections; one line only).

---

## 9. Prompt to start a run

Use this prompt to execute the runbook without interruption:

**Prompt:**

Execute docs/IMPROVEMENTS_RUNBOOK.md from top to bottom. Do not skip steps. For each step: perform the exact action (file path and change), then run the verification. Update docs/IMPROVEMENTS_RUNBOOK_SESSION_STATE.md after each step (or at end of run) with Last completed step and Next step. No approval gates; implement every step until all are done or context limits—then save session state and resume next run from Next step.
