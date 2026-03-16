# RunMyCampus Scroll-Storytelling Marketing Directive

**Mission:** Transform the RunMyCampus marketing front from a static SaaS brochure into a **premium scroll-storytelling product experience**: the page reveals the product narrative as the user scrolls. This is a structural rewrite of the marketing experience, not a decorative animation pass.

**Source of truth:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §8.0 (UI/UX Unification). Implementation checklist: [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md). This directive extends both with the scroll-narrative behavior.

---

## 1. Core principle

The marketing site must behave like an **interactive guided demo**.

As the user scrolls:
- Sections reveal progressively (fade + rise, stagger where appropriate).
- Product visuals change with narrative context (pinned frame updates per chapter).
- Diagrams and platform layers appear in sequence.
- Role experiences and migration/trust stories become visible through motion.

The page must feel **alive, guided, and high-conviction** — not a long white brochure.

---

## 2. Narrative structure (chapters)

| Chapter | Name | Purpose | Existing section IDs (map to) |
|--------|------|---------|---------------------------------|
| 1 | Hero | Bold headline, product frame, ambient motion, strong CTA pair | `#hero` |
| 2 | Why schools switch | Legacy pain points in sequence; narrative + visual proof | `#platform-pillars`, why-switch content |
| 3 | Platform architecture | Pinned visual: Education OS, Control Plane, Studio OS, Marketplace, Migration Cloud, AI, Security | `#one-platform`, `#setup-studio-flow`, `#from-single-to-enterprise` |
| 4 | Launch in minutes | Onboarding as guided sequence: create school → brand → blueprint → packs → preview → launch | `#launch-in-minutes`, `#get-started` |
| 5 | Studio OS | Reveal modes: Experience, Automation, Outputs, Launch, Control; preview frame changes | `#product-visualization`, product pillars |
| 6 | Marketplace & packs | App tiles, blueprint/workflow/dashboard/policy/theme packs; install flow | `#ecosystem` |
| 7 | Migration Cloud | Source import → mapping → validation → parity → staged rollout → cutover | `#migration` |
| 8 | Role experiences | Principal, teacher, parent, student, finance, district admin; one headline + use case + UI state per role | `#for-your-role` |
| 9 | Security & trust | MFA, RBAC, audit trails, break-glass, regional compliance, tenant isolation | `#security-compliance`, `#global-compliance` |
| 10 | Final CTA | Clean, high-trust, product-forward conversion | `#final-cta` |

---

## 3. Motion system

**Motion must only:** (1) direct attention, (2) explain sequence, (3) reinforce hierarchy, (4) make the product feel alive.

**Use:**
- Fade + upward reveal
- Pinned sections (sticky product frame on desktop)
- Scrubbed scroll-based transforms
- Masked reveals
- Card stagger (small delay per item)
- Diagram path drawing (where applicable)
- Counter/number transitions
- Subtle parallax
- Section-to-section morphing

**Avoid:**
- Decorative motion with no purpose
- Giant spin/fly/zoom gimmicks
- Animations on every single element
- Scroll fatigue or carnival-grade effects

**Performance:** All scroll effects must be performant, responsive, progressive-enhancement friendly, non-blocking, and graceful on low-power/mobile. Respect `prefers-reduced-motion`.

---

## 4. Desktop layout pattern

For major chapters use:
- **Sticky/pinned product frame** on one side (e.g. right).
- **Narrative copy** on the other side (e.g. left).
- Visual updates as the user scrolls through subpoints.

Mandatory for: Platform architecture, Studio OS, Migration Cloud, Role experiences, Security & trust.

---

## 5. Mobile layout pattern

- No heavy pinning that breaks usability.
- Stacked reveal cards; lighter transforms.
- Maintain narrative order.
- Keep animation subtle and performant.

---

## 6. What must be removed or reduced

- Square chip/button clutter
- Weak placeholder card grids
- Long empty white stretches
- Repetitive low-value CTA blocks
- Under-seeded diagrams with no narrative
- Sections with text but no visual proof
- Thin brochure-like layout rhythm

---

## 7. What must be added

- One strong product hero visual (already in hero; enhance with “wakes up on scroll”).
- Pinned product frame for key chapters (desktop).
- Animated system diagrams (layers reveal in sequence).
- Role-home and control-plane visuals that update with chapter.
- Migration flow and package-install visuals.
- Scroll progress / chapter indicator (subtle).
- Stronger scroll rhythm and chapter transitions.

---

## 8. Visual alignment rule

Marketing must use the **same premium design language** as the product:
- Same color logic, typography family, spacing discipline.
- Same card/depth language and motion tone.
- Same brand seriousness.

Marketing and product must feel like one family.

---

## 9. Acceptance criteria

The scroll-storytelling rewrite is not complete until:
- The page feels like an interactive product story, not a static brochure.
- Sections reveal progressively with purpose.
- Pinned visual storytelling is used in major chapters (desktop).
- Platform architecture, Studio OS, Migration, roles, and trust are visually explained as the user scrolls.
- The site feels premium, calm, and modern.
- Chip clutter and empty white weakness are gone or heavily reduced.

---

## 10. Technical references

| Item | Location |
|------|----------|
| Landing template | `templates/schools/marketing_landing.html` |
| Marketing CSS | `static/css/marketing-home.css` |
| Scroll-storytelling CSS | `static/css/marketing-home-scroll.css` (reveal, progress, pinned layout) |
| Scroll-storytelling JS | `static/marketing/js/marketing-landing-scroll.js` (Intersection Observer, progress bar) |
| Context / content | `apps/schools/marketing_views.py`; [MARKETING_FRONT_PLACEHOLDER.md](MARKETING_FRONT_PLACEHOLDER.md) |
