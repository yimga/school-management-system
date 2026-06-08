# Marketing Redesign — Direction, Competitive Positioning & Design System

**Status:** direction validated by owner via `marketing_redesign_preview.html` (workspace root / `C:\Users\yimga\RunMyCampus-Previews\`). Build is section-by-section, **HTML-validated before each is wired** into `templates/marketing/`.

This doc is the source-of-truth for the marketing overhaul. It captures (1) the competitive positioning to draw copy from, (2) the design system we are adopting, and (3) the **guardrails** — including parts of the owner-supplied research we deliberately do NOT apply, with the engineering reason.

---

## 1. Competitive positioning (messaging source — reconcile against honesty gates)

Owner-supplied audit of PowerSchool, Toddle, Brightwheel, Arbor. Use as **messaging angles**, not literal claims — every public claim must reconcile against `apps/schools/public_product_promise_matrix.py` and `apps/schools/feature_gap_register.py` (the platform already gates marketing overshoot), and keep the existing "ILLUSTRATIVE / honest-ranges" labelling.

| Domain | Competitor standard | RunMyCampus angle | Marketing hook |
|---|---|---|---|
| Customization | Hardcoded relational fields; weeks of dev for changes | Meta-data-driven runtime (JSONField config manifests) | "Change forms & report-card matrices on a canvas — zero backend code" |
| Data residency | Single-cloud + `filter(tenant_id=x)` patching | PostgreSQL RLS + region routing | "Isolation enforced at the database engine, per region" |
| Offline | Constant-cloud dependency; lockout on outage | Typed CRDT/event-log sync with protected-record review | "Runs offline; deterministically reconciles supported operations and flags protected-record conflicts" |
| Data entry | Manual checkbox clerking | Ambient capture (QR sweeps, passive RFID) | "Scan a classroom in 3 seconds — gradebook self-populates" |
| Layout | Cluttered desktop rows; RTL breaks | Personality-driven, region-aware, progressive disclosure | "Premium, space-contained, RTL-native" |

**Honesty guardrail:** claims like "physically impossible leaks / 0% downtime / 50% workload slash" are positioning, not guarantees. Keep them as *illustrative ranges* with the existing badges. Marketing must not overshoot what `feature_gap_register` can prove.

---

## 2. Design system we ARE adopting (validated in the preview)

- **Personality per surface (the core fix).** No two sections share a look. Five validated personas:
  - **Sovereign** (hero) — deep navy `#0b1020`, animated data-grid, gradient headline, serif display.
  - **Fluid Classroom** (`academics.html`) — light `#f6f8fc`, soft indigo, rounded cards, colored avatars.
  - **Clinical Ledger** (`enterprise_ledger.html`) — clinical white/grey, emerald accents, animated split bars.
  - **Rugged Terminal** (`edge_mesh.html`) — near-black `#070b14`, neon-green mono console.
  - **Simulations Hub** — amber accent, card grid linking every live sim.
- **Working, client-side simulations.** Every demo runs 100% in-browser (no backend round-trip) so it can NEVER say "could not reach validation service." Validated sims: deployment matrix (region→currency/terms/RTL/price), polymorphic gradebook (IB/AP/National rescale), split-ledger router, network-drop simulator. These supersede the broken `marketing_setup_simulator.html` / `marketing_migration_simulator.html` round-trip behaviour.
- **Region-aware** via the REAL geo system `apps/schools/marketing_geo_context.py` (+ `marketing_media_matrix.py`) — NOT the fictional `apps/glocal_kernel` from the pasted prompt.
- **8px geometric rhythm**, SVG/code-generated data-viz, scroll-reveal + count-up motion, progressive-disclosure detail drawers.
- **Imagery pipeline:** premium CSS/SVG + gradient-mesh by default (I can't generate photos); optional free-stock (Unsplash/Pexels search terms per section) or AI-gen (prompts supplied) layered in.

---

## 3. GUARDRAILS — research we deliberately do NOT apply (with reasons)

The owner-supplied "RUNMYCAMPUS-DOMINANCE" prompt contains patterns that would **re-introduce the exact bugs** diagnosed on the current marketing page. We keep the good and reject these:

1. **NO forced `100dvh`/`100lvh` on content + marketing pages.** Locking every shell to one viewport height + `overflow:hidden` is what clips sections into blank navy boxes and hides overflow on the live page today. Marketing is long-form storytelling — it must flow and scroll naturally. (Also a WCAG 1.4.10 reflow / zoom failure.)
2. **NO `white-space:nowrap; text-overflow:ellipsis; overflow:hidden` ("edos-text-shield") on headings or prose.** This is literally why the current page shows truncated/half-cut and doubled headings ("Finance cockpit" twice, "Network drop simulator" overlapping). Clipping belongs only on genuinely tabular single-line cells, with a tooltip — never on titles, CTAs, or paragraphs. RTL safety comes from logical properties + flexible layout, not from clipping.
3. **NO blind platform-wide sweep across all ~44 app template dirs.** The prompt's "forbidden to stop until every file is 100%" mandate conflicts with the owner's own "validate with HTML before continuing" rule and with `CLAUDE.md` scope discipline. Scope = the **marketing surface**, section by section, each HTML-validated. Control-plane/portal already got their own targeted waves.
4. **48px master-header / 5-column-everywhere** are fine as *marketing-section* aesthetics but are NOT globally mandated across portal/admin (those have working, separately-owned chrome).

**Net:** adopt personality + region-aware + 8px rhythm + SVG viz + progressive disclosure + working sims. Reject viewport-lock + text-clipping + unbounded global refactor.

---

## 4. Regional competitor intel → per-section proof points (2026-06-05 paste, PART 1)

The owner's continent-by-continent audit is genuinely useful as **per-section messaging + sim fuel** (PART 3 of the same paste is the harmful prompt — already guard-railed in §3; `apps/glocal_kernel` is still fictional). Reconcile every claim against `feature_gap_register` / `public_product_promise_matrix` and keep the illustrative badges.

| Region | Competitors | Their gap | Our 10X angle → which section proves it |
|---|---|---|---|
| **North America** (US/CA) | PowerSchool, Infinite Campus, Skyward, Frontline | Legacy relational, months to deploy, internet-only, no native multi-currency | State-reporting bridges (CALPADS/EdFacts), drag-drop spreadsheet migration → **Sovereign** wizard + **Migration** sim |
| **LATAM** | Totvs, Colegium, Syscol | Factura Electrónica bolted-on; card-only locks out unbanked/cash | Dynamic fiscal adapter (SAT/SEFAZ stamps in the receipt) + APM hub (Pix/CoDi/OXXO) → **Clinical Ledger** ✅ (now shows NF-e/SEFAZ + CFDI/SAT + Pix/Boleto/SPEI/CoDi/OXXO rails) |
| **EU/UK** | SIMS (ESS), Arbor, Bromcom, Compass, Untis | SIMS legacy exodus; single-curriculum interfaces | GDPR cryptographic key-shredding + polymorphic grading (A-Levels **and** IB on one dashboard) → **Fluid Classroom** gradebook morph + **Governance** auditor |
| **Sub-Saharan / N. Africa** | Edves, SAFSMS, paper | Cloud dies during load-shedding; data plans too costly | Zero-data P2P mesh (Bluetooth/Wi-Fi Direct) + USSD split-wallet (M-Pesa/MTN) → **Rugged Terminal** (network-drop sim + USSD + QR/RFID) |
| **APAC / South Asia** | Fedena, Toddle, gov platforms | Translation plugins break layout; RTL/script overlap | Flexbox-isomorphic zero-hardcoded-width layout (already our `marketing_geo_context` direction/RTL) + dual-identity (school + hagwon/coaching) → **Sovereign** RTL mirror + **Fluid** profile cards |

**Fold-in rule:** each section's copy + sim should name the regional competitor pain it kills, but only at the strength `feature_gap_register` supports. The Clinical Ledger already encodes the fintech half of this table (10 tax authorities + region APM rails, all client-side).

---

## 5. Build status (section-by-section, each HTML-validated live)

| # | Section | Persona | File(s) | Working client-side sim | Status |
|---|---|---|---|---|---|
| 1 | Hero | Sovereign | `_sovereign_kernel.html` · `mkt-hero-sovereign.css` · `mkt-sandbox-wizard.js` | Region→currency/terms/RTL deployment matrix | ✅ shipped + live-validated |
| 2 | Finance | Clinical Ledger | `_clinical_ledger.html` · `mkt-clinical-ledger.css` · `mkt-split-ledger.js` | Region-aware 80/10/10 split-payment router + animated e-invoice tax stamp (10 authorities) | ✅ shipped + live-validated US+UAE/RTL |
| 3 | Edge / Offline | Rugged Terminal | `_rugged_engine.html` · `mkt-rugged-terminal.css` · `mkt-network-state.js` | Network-drop → USSD/QR/RFID collapse + local sync-queue that holds offline and drains on reconnect | ✅ shipped + live-validated (fiber→blackout→reconnect) |
| 4 | Academics | Fluid Classroom | `_fluid_classroom.html` · `mkt-fluid-classroom.css` · `mkt-gradebook-morph.js` | Polymorphic gradebook — one record re-expressed across US/IB/Cambridge/competency, zero layout shift | ✅ shipped + live-validated (US/IB/competency) |
| 5 | Simulations Hub | Amber index | `_simulations_hub.html` · `mkt-simulations-hub.css` | Directory: anchors the 4 in-page sims + links the dedicated labs (zero-ui/pricing/enterprise/edge-mesh) | ✅ shipped + live-validated (8 cards, all hrefs resolve) |

All five are wired into `homepage.html` (`/storefront/`) and validated live via runserver + Playwright on the `runmycampus.com` host. SW bumped per section (latest `sms-v4.02.25-marketing-simulations-hub`). All gates green each section: `manage.py check` 0 · off-token 0 · theme-locked 0 · render-safety 0 · undefined-css no new mkt leaks · inline-style no new findings.

Layout note (owner, 2026-06-05): sections are full-bleed surfaces with a wide centred content container (Apple-tier — prose is not stretched edge-to-edge); the `min-height:100svh` rhythm is kept for consistent scroll cadence, content vertically centred, never clipped.

**Scanner lesson durably learned this wave:** `off-token` / `undefined-css` require the `/* off-token-allow: … */` marker to sit **inside** the rule braces on the declaration line — a marker placed after the closing `}` is outside the rule body the scanner inspects and is NOT honoured. Multi-line `background:` declarations must keep the marker on the property line, not a value-continuation line.

---

## 6. Imagery pipeline (owner: "our images are not good")

The root cause of the "poor images" complaint was reliance on weak/broken stock + a missing regional `<video>` (the blank navy box). The redesign replaces that with **premium, generated, theme-aware visuals** as the default — nothing to 404, nothing off-brand, every "image" is a live, interactive proof:

- **Default (shipped):** CSS/SVG + `color-mix` gradient-mesh, animated data-grids, the terminal console, the split-ledger bar, the gradebook pills, count-up stats. Token-driven so they stay on-brand and theme-correct, and they double as the working sims. Zero external image dependencies → zero broken images.
- **Optional layer A — free stock:** per-section Unsplash/Pexels search terms (e.g. Sovereign: "modern campus aerial dusk"; Clinical: "clean fintech dashboard macro"; Rugged: "rural school solar classroom"; Fluid: "diverse students collaborating bright"). Drop into a `geo`-aware `<picture>` with `loading="lazy"` behind the generated visual.
- **Optional layer B — AI-generated:** prompts supplied per section for a 16:9 hero plate; must be run through the existing marketing-overshoot honesty gates before use.

Generated-first is the recommended default (it's what the owner approved in the preview) — stock/AI are additive, never load-bearing.

---

## 7. Full viewport-lock sweep (2026-06-05) — dedicated standalone pages rescued

After the homepage, the owner asked to "aggressively address everything left." The homepage CSS neutralization did **not** cover the dedicated `/experience/<slug>/` pages — they had their own active locks:
- `marketing-personality-pages.css` → `.mkt-personality-page__viewport` had `min/max-height:100dvh; overflow:hidden`.
- `marketing-acquisition-engine.css` → `.mkt-personality-page__stack` had `scroll-snap-type:y mandatory; overflow-y:auto; max-height:100dvh`.

Both clipped every dedicated page (academics / enterprise-ledger / edge-mesh / zero-ui / pricing / compliance) into a one-screen box. **Fixed to responsive flow** (`min-height:100svh; overflow:visible` / `display:block`), then stripped **35 dead harmful-class tokens** (`mkt-ve-section--viewport-lock`, `mkt-edos-text-shield`, `data-(mkt|rmc)-scroll-policy="viewport-lock"`) across 14 templates. The split-ledger JS gained `initCompact()` back-compat so the shared old compact-slider partial still animates.

**Live-validated all six** (`/experience/<slug>/`): every page reports `max-height:none` + `overflow:visible` (lock gone), document height 3154–4275px (flows over multiple screens, not clipped), headlines unclipped, each page's own sim clicks through, **zero JS errors**. The seven dedicated-page partials each already carried a working client-side sim (speed-duel, edge-map, enterprise-constellation, entitlement-calculator, governance display, viewport-trinity, zero-ui playground) — they only needed unlocking, not rebuilding.

**Result: zero viewport-lock / text-shield / scroll-policy tokens remain in any marketing template.** SW `sms-v4.02.26-marketing-viewport-lock-sweep`. All gates green.

---

## 8. Expanded "Cloud-Dependency-Collapse" paste (2026-06-07) — guard-railed

The owner pasted an **expanded** version of the dominance research: PART 1 (regional competitor audit — already folded into §4), PART 2 (a 6-phase institutional lifecycle manifest — genuinely useful; converted into `docs/GLOCAL_SOVEREIGNTY_PLAN.md`), PART 3 (new Django code), and PART 4 (the "scan-all-files-until-100%" prompt — already rejected in §3.3).

**PART 3 is harmful and must NOT be merged.** Full reasons + the real subsystem for each are in `docs/GLOCAL_SOVEREIGNTY_PLAN.md` §1. Summary of what to reject:

1. **`apps/glocal_kernel/models.py`** — invented app; does not exist. Tenant config = `School` + the `RuntimeDefaults→SiteSettings` cascade; localization = `apps/siteconfig/country_localization_service.py`.
2. **`CongruentTenantMeshMiddleware`** — a DB-per-tenant router with dynamic connection injection + JWT-claim RLS. Contradicts the live architecture (shared DB + `School` + `app.current_school_id` RLS in `apps/schools/middleware.py` / migration `0002_enable_rls_postgresql.py`). Would break every existing query, migration and the RLS gate.
3. **Hardcoded DB credentials/host** (`'PASSWORD': 'SECURE_ENV_DECRYPTED_PASSWORD'`, `pgbouncer` host) — violates the no-hardcoding directive; config is env-driven `DATABASE_URL`.
4. **`merge_offline_crdt_stream`** — not a CRDT; wall-clock string-compare last-write-wins → silent data loss under clock skew. Real offline sync = `apps/sync_engine` + `apps/api/mobile_api.OfflineSyncQueue` + `apps/api/offline_encryption.py`.
5. **`portal_base.html` rewrite** (`100dvh` grid lock, `overflow:hidden`, `.edos-text-shield`, `user-scalable=no`) — the exact clipping/blank-box pattern already removed (§3, §7); also WCAG 1.4.4 + 1.4.10 failures.
6. **Inline-`<script>` "layout sentinel"** mutating `element.style.*` at runtime — bypasses the token system (trips `scan_inline_style_off_token` baseline 0 + CSP nonce gate) and "fixes" overflow by clipping (the very bug it claims to detect).

**The thesis is right and already largely built** — the platform already ships a mature offline-first stack (service worker, IndexedDB, `sync_engine`, `OfflineSyncQueue`, LAN-hub sync, offline encryption + auth vault). The lifecycle gaps are sequenced as bounded waves in `docs/GLOCAL_SOVEREIGNTY_PLAN.md` §5; per-feature promises tracked in `apps/schools/feature_gap_register.py` (lifecycle rows added 2026-06-07, all `planned`/`in_progress`).
