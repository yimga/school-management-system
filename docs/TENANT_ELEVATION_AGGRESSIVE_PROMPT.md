# Tenant Elevation — Aggressive Continuous-Fix Prompt

> Hand this whole file to a Claude Code session. It is self-contained. Fill in the
> **DECISIONS** block at the top with the owner's chosen options, then say "execute".
> The mission is to make the **tenant surface (all tenants, not one test tenant)** look
> and feel like the three design HTMLs — immaculate, dense, professional — and to keep
> auditing and fixing until a fresh audit finds nothing left.

---

## DECISIONS (owner fills these in)

- **Header:** `1A` (single calm 56px bar) — _or 1B / 1C_
- **Welcome/void:** `2A` (fill void with readiness tiles) — _or 2B / 2C_
- **Density:** `3C` (auto-fill bento + tightened tokens) — _or 3A / 3B_
- **Bugs:** fix all three (sidebar duplicates, sidebar→reload, copilot RBAC) verify-first.

> Default if owner just says "go": **1A · 2A · 3C** + all three bugs.

---

## NON-NEGOTIABLE OPERATING RULES

1. **VERIFY-FIRST — every finding is a hypothesis until you read the live code.**
   In the originating audit, two sub-agents produced confident-but-WRONG root causes
   (claimed the copilot JS/CSS wasn't loaded — it IS, `portal_base.html:692-693`;
   claimed `_dedupe_sidebar_items()` was never called — it IS, `portal_sidebar_items.py:1525`).
   **Never edit off a second-hand finding. Open the file, confirm the exact cause, THEN fix.**
2. **Token-only CSS.** No hex/rgb literals outside theme scopes; use the design tokens
   (`--bg #060912`, `--canvas #0e1426`, `--elevated #141c33`, `--text/--text-2/--text-3`,
   `--hairline rgba(255,255,255,.08)`, `--brand #6366f1`, `--violet #8b5cf6`,
   `--accent #10b981`, `--warn #f59e0b`, `--radius 14px`, Inter). No hardcoding — route
   configurable values through the cascade.
3. **All CI gates green** before every commit: `scan_undefined_css_classes`,
   `scan_off_token_colors`, `scan_theme_locked_token_text`, `scan_inline_style_off_token`,
   `audit_template_render_safety`, `scan_attribute_context_includes`,
   `scan_import_reference_integrity`, `scan_magic_numbers --compare`,
   `scan_role_strings --compare`, `verify_service_worker_version --check-monotonic`.
4. **Bump the service worker `CACHE_VERSION`** on every wave that ships CSS/JS (monotonic).
5. **Tenant-wide.** Work the SHARED shells/CSS (`templates/portal_base.html`,
   `templates/accounts/backend_dashboard.html`, the `backend-dashboard-v2*.css` /
   `rmc-tenant-header-100x.css` bundles) so the fix lands for EVERY tenant.
6. **Browsable HTML per judgment call.** For anything with a visual choice, write a
   self-contained before/after preview to `var/design-previews/<topic>-browsable.html`
   and pause for owner approval. Mechanical/objective fixes don't need a preview.
7. **Path-scoped commits.** A parallel session is often editing the tree (e.g.
   `table-intelligence`). Commit only the files you changed: `git commit -F - -- <paths>`.
   Never `git add -A`. No new migrations unless unavoidable (owner is migration-wary).
8. **Loop until dry.** After each wave: re-run the audit. Stop only when a fresh audit
   surfaces nothing new. Log anything intentionally deferred.

---

## DESIGN TARGET (extracted from `var/design-previews/tenant-role-dashboards-hub.html`)

- **Header:** single row, ~56px, thin 8% hairline, recessive subtitle (`--text-3`). No stacked bands.
- **Card grid:** `repeat(auto-fill, minmax(280px,1fr)); gap:14px;` card padding 18px.
- **Section rhythm:** `h2 { margin:32px 0 14px }`. Radius 14px everywhere.
- **Type scale:** weights 750 / 650 / 600; text opacity ladder 100% / 66% / 50%.
- **Micro-interactions:** card hover `border-color:rgba(99,102,241,.45); transform:translateY(-2px); transition:.15s`. Segmented-control active = indigo→violet gradient + colored shadow.
- **Copilot rail flex math (critical):** `.thread { flex:1 1 auto; min-height:0; overflow-y:auto }` so the composer is never clipped.

---

## VERIFIED WORK ITEMS (confirmed by reading live code)

### Wave 1 — Header (decision 1)
- `templates/portal_base.html:194-202` — the LIVE-ticker band renders as a separate full
  row above the header; collapse per the chosen option.
- `static/css/rmc-tenant-header-100x.css:51` — `min-height:calc(64px*1.1)` (70.4px) → 56px.
- Below-`lg` nav band (`.tp-primary-nav-bandrow`) adds another row — fold into a menu.

### Wave 2 — Welcome void (decision 2)
- `templates/accounts/backend_dashboard.html:475-617` — the `.backend-role-home-top` block.
- `static/css/backend-dashboard-v2.css:928` — grid `minmax(0,1.6fr) minmax(260px,0.9fr)` +
  `align-items:start` → the empty right column / rounded void. Apply chosen option.

### Wave 3 — Density (decision 3)
- `static/css/backend-dashboard-v2-contract.css:245` — `.backend-v2-progress-ring-wrap
  { min-height:92px }` → content-aware.
- `static/css/backend-dashboard-v2.css:103-113` — datetime/calendar triple-spacing → single gap.
- `static/css/backend-dashboard-v2.css:90-100` — card `--dash-card-pad` 24px → add a tight
  variant for empty/side cards.
- `static/css/backend-dashboard-v2.css:133-159` — main grid `2fr/1fr` → auto-fill bento
  (decision 3A/3C). `static/css/backend-bento-asymmetric.css:27` hero `min-height:140px`.
- Tighten card gaps to 14px; add the hover-lift + gradient-segmented states globally.

### Wave 4 — Bugs (VERIFY-FIRST; sub-agent specifics were wrong)
- **Sidebar duplicates:** `_dedupe_sidebar_items()` (`apps/siteconfig/portal_sidebar_items.py:248`)
  IS called at `:1525`, yet dupes survive (Report Card Builder ×2, Import & bulk ×2,
  Dashboard Hub ×2, Institution profile ×2, District & LMS interop ×2). DIG: print the
  surviving pairs; they likely share a label but differ in `id`/`url`. FIX: strengthen the
  dedupe key (normalized label + destination) AND/OR stop emitting the same destination in
  two sections. Add a regression test asserting no duplicate `(label)` within a section.
- **Sidebar click → reload:** confirm which items render an empty `href` (a `_safe_reverse`
  returning `None`). FIX the failing reverses; make the sidebar template DROP url-less items
  instead of rendering a dead link. Add a test asserting every emitted item has a truthy url.
- **Copilot not answering:** wiring present. DIG the RBAC/entitlement gate end-to-end:
  `services/ai_copilot_rbac.py` (`build_copilot_permissions`, `guard_copilot_invoke`),
  `services/ai_permissions.py::get_ai_permission_for_user`, the master gate
  `apps/siteconfig/cockpit_context.py::_tenant_ai_copilot_rail_master_enabled`, and
  `cockpit.ai_copilot_rail.enabled`. Trace one tenant-admin send to the point it fails
  closed; fix it; surface an HONEST reason (banner/toast) instead of silent no-op.
- **Tools rail polish:** ensure `rmc-copilot-rail.css` styles the collapsed icon strip
  (token colors, hover, active-tab highlight) on the TENANT shell, not just operator.

### Wave 5 — Tenant-wide sweep
- Repeat the header/density/hover treatment across the other tenant landings
  (parent / teacher / student portals) and the finance/analytics shells. Each gets a
  before/after browsable preview if the layout changes materially.

---

## EXECUTION LOOP

```
for each chosen wave:
  1. RE-READ the cited files; confirm the cause is exactly as described.
  2. If a judgment call → write var/design-previews/<topic>-browsable.html, pause for approval.
  3. Make the smallest correct edit (token-only, no hardcoding).
  4. Run the relevant tests (RMC_SQLITE_TEST_USE_MEMORY_NAME=1) + all CI gates.
  5. Bump SW CACHE_VERSION if CSS/JS changed.
  6. Path-scoped commit + push.
  7. RE-AUDIT (re-run the 4-lens audit). Add any new findings to the work list.
repeat until a fresh audit finds nothing.
```

## DONE = a fresh 4-lens audit (design parity · space · nav · copilot/tools) returns zero new findings, all gates green, SW monotonic, and the owner has approved every browsable preview.
