# AI Center + master-prompt gap closeout — 2026-05-16 (v2.85)

**FAQ:** [AI_SURFACES_FAQ.md](AI_SURFACES_FAQ.md) — AI Center vs gateway console vs API Center.

Closes 4 of the 5 "genuinely not done" items from the v2.83 status report,
plus the new platform-wide bug the user surfaced (broken / scattered AI
assistant cards). Shipped end-to-end in one wave.

## 1. AI Center — single canonical AI surface

**Bug**: Per-page `ai_guided_assistant_card.html` includes scattered 5 templates
with chat boxes that didn't appear to work for the user (likely because the
target endpoint is `@login_required` and some role/host combos got redirected
to login, causing fetch → HTML response → JSON parse failure with no visible
explanation in the card).

**Fix**: Replace the per-page chat cards with a single canonical surface at
`/siteconfig/ai-center/` (`siteconfig:ai_center`). The card component is now a
compact CTA that deep-links to the AI Center pre-focused on the right
assistant (`?focus=<assistant_key>`).

**What landed**

- `apps/siteconfig/views_ai_center.py` — view that reads from the assistants
  registry, resolves each row's API URL + entry points, marks usability per
  user, and chooses a default focused assistant.
- `templates/siteconfig/ai_center.html` — single canonical chat shell. Left
  rail lists every assistant; right panel hosts the chat form, hints, and
  links to surfaces where that assistant is contextually useful.
- `static/js/_pages/siteconfig__ai_center.js` — picker swaps `data-ai-url`
  + `data-studio-mode` on the chat form and fires a re-bind event.
- `static/js/rmc_ai_guided_assistant.js` — now listens for
  `document.dispatchEvent('rmc:ai-guided-rebind')` so the AI Center picker can
  swap assistants without a page reload.
- `apps/siteconfig/ai_assistants.py` — extended registry with `hint` +
  `api_url_name` + (optional) `studio_mode` per row. Added 2 missing rows
  (`observability_assistant`, `billing_usage_explain`) that were API-only.
  NEW `get_assistant(slug)` lookup.
- `templates/components/ai_guided_assistant_card.html` — rewritten as a
  compact CTA. Backwards-compatible: old `api_url` / `field_id` / `studio_mode`
  kwargs are accepted and ignored.
- 7 templates updated to pass `assistant_key=` instead of `api_url=` /
  `field_id=` (super_dashboard ×3, billing_dashboard, governance_console,
  super_migration_cloud, super_trust_center, district_lms_interop ×2,
  studio_os/shell, studio_os partials).
- `apps/portal/views_configure.py` — added "AI Center" as the first entry in
  the Configure → AI category.
- `apps/schools/control_plane_nav.py` — added "AI Center" entry to the
  Command Center group on the manager sidebar.
- `templates/components/rmc_command_palette.html` — added "AI Center" to ⌘K.
- 5 tests in `apps/siteconfig/tests/test_ai_center.py` cover registry
  invariants, view render, `?focus=` preselection, anonymous redirect, and
  ⌘K payload presence.

**Verified**: every assistant in the registry has both `api_url_name` and
`hint`; the URL resolves on all three urlconfs (root, tenant, manager);
template render-safety + undefined-CSS-class + inline-style-off-token all
remain at 0 findings.

## 2. API Center browser proof

Closes the "API Center not browser-certified" risk in the section O register.

- `tests/playwright/tests/api-center-operator-proof.spec.ts` (4 stages,
  ~7 assertions). Reuses the existing `RMC_STAGING_*` secret triple; skips
  cleanly without staging creds. Stages: dashboard renders, toggle refuses
  empty reason, developer-platform stubs return non-5xx, audit feed renders
  (or shows the empty-state hint).

## 3. Render parity scaffold

Closes "render parity partial — needs deployed SHA + live route comparison."

- `scripts/check_render_parity.py` reads `docs/generated/route_surface_audit.json`,
  HEADs a sample (default 60) of GET routes against `RMC_DEPLOYED_BASE_URL`,
  classifies as ok/404/5xx/connect-fail. Exits 1 only on 5xx (regression);
  404 is informational (un-deployed branch).
- `.github/workflows/render-parity.yml` — manual trigger, skips cleanly
  without `RMC_DEPLOYED_BASE_URL`. Optional `RMC_DEPLOYED_AUTH_COOKIE`.

## 4. Feature Gap Register SOT

Closes `end_to_end_feature_gap_register` from section N. The SOT is the spec.

- `apps/schools/feature_gap_register.py` — `FeatureRow` dataclass + 26-feature
  register. Each row pins a status (`shipped` | `in_progress` | `planned`)
  and at least one proof source (route / model / mgmt command / CI gate).
- `config/manager_urls.py::manager_feature_gap_register` — operator surface
  at `/feature-gap-register/` that resolves every row's proof and flags
  broken ones in red.
- `templates/schools/manager_feature_gap_register.html` — grouped by
  capability domain (identity, billing, governance, ai, integrations,
  studio_os, observability). Page archetype: operator-report.
- `apps/schools/tests/test_feature_gap_register.py` — 7 tests including:
  unique slugs, valid statuses, every shipped row has a proof, every shipped
  route proof resolves on at least one urlconf, every shipped model proof
  loads via `apps.get_model()`, pillar features present.
- Manager sidebar: added "Feature gap register" entry below "Public-to-Product
  matrix" in the same group.

**Verified**: every shipped feature resolves its proof.

## Batch 1249 — offline-first vs Ollama UX (2026-05-16)

**Problem:** Users could confuse tenant offline-first (attendance/grades queue) with AI working offline, or miss when Ollama is down vs the browser being offline.

**Fix:** AI Center polls `/api/ai/health/` (same contract as copilot); shows browser-offline hint and disables Ask; guided assistant explains offline vs server AI before fetch. Nested `<main>` removed (portal_base landmark). Operator still connects Ollama on the app host (Lane 2).

## Batch 1247 — guided assistant reliability (2026-05-16)

**Problem:** Rules-only mode returned plain strings from `invoke()` while guided `/api/ai/*` views expected a `guided` dict → `success: true` with empty `summary`.

**Fix:** `services/ai_guided_fallback.py` + `_rules_invoke_result()` in `services/ai_gateway.py`; RAG snippets in gateway metadata; `rmc_ai_guided_assistant.js` and `rmc_ai_json_api_card.js` human-readable output; gateway console provider health strip.

**Verify:** `apps.portal.tests.test_guided_assistant_rules_fallback`, `apps.portal.tests.test_ai_guided_fallback_unit`, `apps.siteconfig.tests.test_ai_center` (includes rules-mode POST).

## Still genuinely not done (not in this wave)

| Item | Why |
|------|-----|
| `emotional_ux_confidence_audit` | Needs user-testing or design-review session — not codifiable as a scanner. |
| `feedback_loop_live_usage` | Telemetry harness is wired; needs real-user data to flow. Out of code-scope this wave. |
| Studio OS per-mode premium polish on Launch / Experience / Automation | The per-mode polish budget is per-wave (Control done v2.64.1, Output done v2.70). Tracked separately. |
| External PSP/SOC2/pilots | Out of code scope (Lane 2). |

## Files changed

```
NEW  apps/siteconfig/views_ai_center.py
NEW  templates/siteconfig/ai_center.html
NEW  static/js/_pages/siteconfig__ai_center.js
NEW  apps/siteconfig/tests/test_ai_center.py
NEW  apps/schools/feature_gap_register.py
NEW  apps/schools/tests/test_feature_gap_register.py
NEW  templates/schools/manager_feature_gap_register.html
NEW  scripts/check_render_parity.py
NEW  .github/workflows/render-parity.yml
NEW  tests/playwright/tests/api-center-operator-proof.spec.ts
NEW  docs/AI_CENTER_AND_GAP_CLOSURE_2026_05_16.md   (this file)

MOD  apps/siteconfig/ai_assistants.py               (+11 rows extended, +2 new)
MOD  apps/siteconfig/urls.py                        (+1 route)
MOD  apps/portal/views_configure.py                 (+1 AI Center entry)
MOD  apps/schools/control_plane_nav.py              (+2 nav entries)
MOD  config/manager_urls.py                         (+feature-gap view + URL)
MOD  templates/components/ai_guided_assistant_card.html   (rewritten as CTA)
MOD  templates/components/rmc_command_palette.html  (+AI Center entry)
MOD  static/js/rmc_ai_guided_assistant.js           (+rebind event listener)
MOD  templates/schools/super_dashboard.html         (3 includes simplified)
MOD  templates/schools/billing_dashboard.html       (1 include simplified)
MOD  templates/schools/super_migration_cloud.html   (1 include simplified)
MOD  templates/schools/super_trust_center.html      (1 include simplified)
MOD  templates/marketplace/governance_console.html  (1 include simplified)
MOD  templates/accounts/district_lms_interop.html   (2 includes simplified)
MOD  templates/studio_os/shell.html                 (1 include simplified)
MOD  templates/studio_os/partials/shell_main_content.html  (1 include simplified)
```

## CI gates after this wave

All 11 architectural gates green. No baseline bumps:

- `audit_template_render_safety` — 0
- `scan_inline_style_off_token` — 0
- `scan_undefined_css_classes` — 0
- `audit_role_permission_matrix --max-candidate-anonymous 66` — unchanged

`sms-v2.85.0`
