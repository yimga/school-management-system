# Studio OS — Output next-realm audit (v3.54.0, 2026-05-21)

Agent 4 of 6 — owns the **OUTPUT** section.

## 1. Surface inventory

Output mode is rendered by `apps/studio_os/views.py::studio_shell` when `mode='output'`
(approx. lines 1708-1905). Three sub-views also exist:

- `studio_output_dependency_graph` (line 689) — full-page graph
- `studio_output_branding_inheritance` (line 720) — single-card explainer
- `studio_output_policy_registry` (line 750) — single-card explainer

The Output mode is a *router*: one canvas template picks one of seven panes
(`dependency`, `reports`, `documents`, `builder`, `credentials`, `branding`, `policy`)
via `?pane=`. All seven render natively today (no iframe) except the iframe fallback
inside the report-card builder, which is preserved by design.

## 2. Context vars (output_*)

The shell view sets these under `mode == 'output'`:

| Var | Purpose |
| --- | --- |
| `output_pane` | which pane is active (default `dependency`) |
| `output_left_rail` | list of 7 rail items, each `{label, url, embed, pane}` |
| `output_iframe_src` | always `''` in next-realm |
| `output_dependency_graph` | from `get_output_dependency_graph()` |
| `output_pack_preview_cards` | from `get_output_report_pack_preview_cards(out_base=...)` |
| `output_focus_pack_code` | `?pack=` slug, max 160 chars |
| `output_doc_library` | from `build_document_library_manage_context(request, studio_output_native=True)` or `None` |
| `output_documents_denied` | True when user lacks `settings.manage` |
| `output_reports_native` | dict with page_title / page_subtitle / 4 child URLs |
| `output_reports_denied` | True when user lacks `settings.manage` |
| `output_credentials_native` | dict |
| `output_branding_native` | dict |
| `output_policy_native` | dict |
| `output_reportcard_builder` | from `build_reportcard_builder_context(...)` or `None` |
| `output_builder_denied` | True when user lacks `settings.manage` |

**Missing for the next-realm readiness cockpit** (treated as coordinator tasks):

- `output_readiness_summary` — proposed dict carrying packs_total / packs_with_deps /
  packs_missing_deps / documents_total / documents_published / service_online flag.
- `output_last_published_at` — there is no published-vs-draft state on ReportPack.

The new readiness preview pane renders honest derived counts (`{{ output_dependency_graph|length }}`,
filter for those with non-empty dependencies) until a real readiness service ships.

## 3. Output categories → routes

| Category | Real route | Manager-only |
| --- | --- | --- |
| Reports & packs | `studio_os:output?pane=reports` | No |
| Documents | `studio_os:output?pane=documents` | No |
| Report cards | `studio_os:output?pane=builder` | No |
| Credentials | `studio_os:output?pane=credentials` | No |
| Branding | `studio_os:output?pane=branding` | No |
| Policy | `studio_os:output?pane=policy` | No |
| Dependency graph | `studio_os:output?pane=dependency` | No |
| Public output | (none) | — |
| Portal output | (none) | — |
| Exports queue | (none) | — |

The three categories without routes are hidden in the readiness pane — no dummy `href="#"`.

## 4. Horizontal overflow risks (root causes)

1. `output_dependency_graph_body.html` — Long pack codes / dependency item joins can
   blow line width. Fix in CSS via `word-break: break-word` + `min-width: 0` on the
   list items. No template change needed.
2. `output_reportcard_builder_wrapper.html` — Passes through to a non-owned partial
   (`siteconfig/partials/reportcard_builder_inner.html`). Wrap include in a
   `min-width: 0` shell; cannot modify the inner partial.
3. `output_documents_native_wrapper.html` — Passes through to a non-owned partial
   (`portal/partials/document_library_manage_inner.html`). Same shell wrap strategy.
4. `output_mobile_tabs.html` — Already horizontally scrollable via `overflow-x-auto`.
   Adds a wrap-fallback at 390px in the new CSS so very narrow viewports stack tabs.
5. `output_canvas.html` — Iframe fallback already `width: 100%` via `.studio-os-iframe`.
   No change needed; we keep the iframe path as a safety net but expect it to be
   unreachable in next-realm.

## 5. Output readiness — today vs target

**Today**

- "Ready" ≈ `ReportPack.is_active=True`
- No version state, no last-published-at, no draft↔published FSM
- Missing-data state implicit via `len(dependencies) == 0`

**Next-realm target**

- Cockpit tile group: Reports / Documents / Report cards / Credentials / Branding
- Per-pack chip: `Ready` (deps present) | `Missing data` (deps empty) | `Unknown`
- Honest "Readiness service offline" state when context vars absent

The new template implements the target with honest fallbacks; the **coordinator
task** (`services.py` + `views.py`) is a follow-up to wire a real
`get_output_readiness_summary()` rather than derive client-side.

## 6. Branding inheritance — the real chain

| Layer | Token / file |
| --- | --- |
| Tenant defaults | `RuntimeDefaults` typed columns |
| Site settings | `SiteSettings.brand_payload` |
| Context | `siteconfig.context_processors` |
| Meta bridge | `templates/partials/rmc_theme_meta.html` |
| Bootstrap | `static/js/theme-preference-bootstrap.js` (writes `html[data-resolved-theme]`) |
| Tokens | `static/css/design-tokens.css` (`--school-primary`, `--school-accent`) |
| Reports | inherit at print via the same tokens |

The new branding pane visualizes this chain with swatches generated from `var(--*)`,
never from inline hex.

## 7. Tenant scope

- Studio gated by `user_can_access_studio_on_request(request)`.
- Manager-host detection (`request.public_host_kind == 'manager'`) keeps the legacy
  iframe path; tenant host gets the native left-rail workspace.
- `ReportPack` is global (single source of truth across tenants); per-tenant readiness
  numbers come from tenant-scoped downstream views.

## 8. Required actions

**Keep**
- `output_dependency_graph_body.html` copy (already typographic)
- `output_documents_native_wrapper.html` / `output_reportcard_builder_wrapper.html` pass-throughs
- `output_credentials_body.html` (real-link-only)

**Minor repair**
- `output_mode_canvas.html` — extract empty state into rmc-output-cockpit grammar
- `output_canvas.html` — host the readiness preview pane above pane content; wrap iframe fallback in `min-width:0`
- `output_branding_inheritance_body.html` — add token-swatch visualization
- `output_policy_registry_body.html` — convert paragraphs into responsive list
- `output_reports_library_body.html` — add readiness chips
- `output_rail.html` — small badge for hub-leaving items
- `output_mobile_tabs.html` — 390px wrap fallback hook

**New**
- `output_readiness_preview_pane.html` — readiness tiles + per-output preview entry
- `static/css/studio-output-cockpit.css` — `.rmc-output-*` grammar
- `apps/studio_os/tests/test_output_readiness_cockpit.py`

**Coordinator tasks** (not blocking)

1. `apps/studio_os/services.py` — add `get_output_readiness_summary()`.
2. `apps/studio_os/views.py` — wire `context['output_readiness_summary']` under
   `mode == 'output'`, with try/except returning `{"service_online": False}` on failure.

## 9. Scanner risks

All zero-tolerance scanners expected to stay at 0:

- `scan_money_float` — no money rendering in Output partials.
- `scan_off_token_colors` — only `var(--*)` in new CSS.
- `scan_theme_attribute_contract` — no `data-theme` writes.
- `scan_sticky_with_overflow_hidden` — no `position: sticky` in new CSS.
- `scan_reveal_armed_invariants` — no `rmc-reveal*` introduced.
- `scan_pii_logging_smell` — no logging in templates.

## 10. Deferred (honest)

- Real readiness service (dataclass + per-tenant counts) — coordinator task above.
- Per-pack version state — requires a `ReportPack.published_at` column, out of scope.
- Draft↔published workflow — out of scope.
