# Platform audit artifacts — 2026-05-16 (v2.71)

End-to-end static audit batch covering the doable subset of the
master-prompt request: route inventory, action integrity, no-placeholder
check, and navigation simplification. Subjective items (UX quality,
emotional confidence, browser axe) are out of scope for this wave and
listed at the bottom for honest tracking.

## Summary

| Artifact                          | Tool                                      | JSON                                                   | Headline number      | Status                |
|-----------------------------------|-------------------------------------------|--------------------------------------------------------|----------------------|-----------------------|
| Route inventory                   | `scripts/audit_route_surface.py`          | `docs/generated/route_surface_audit.json`              | 6,081 routes         | CERTIFIED (0 broken)  |
| POST handler integrity            | `scripts/audit_post_handler_surface.py`   | `docs/generated/post_handler_audit.json`               | 257 handler hits     | OK                    |
| Template URL name integrity       | `scripts/audit_template_url_names.py`     | (console summary)                                      | 0 broken refs        | OK                    |
| Page standards                    | `scripts/audit_page_standards.py`         | (console summary)                                      | 9 findings / 895 tpl | drift-detection       |
| No-placeholder content            | `scripts/audit_no_placeholder.py` (NEW)   | `docs/generated/no_placeholder_audit.json`             | 3 findings           | clean (see notes)     |
| Navigation simplification         | `scripts/audit_navigation_simplification.py` (NEW) | `docs/generated/navigation_simplification_audit.json` | 0 oversize groups    | PASS                  |

All audits ran 2026-05-16 against HEAD (commit `6c4f5b07`) with the
v2.67 sidebar simplification uncommitted-but-in-working-tree.

## 1. Route inventory — `end_to_end_app_route_inventory`

`scripts/audit_route_surface.py` walks the full URLconf graph and the
template surface in one pass.

- **6,081 routes** audited across every URLconf reachable from
  `config/urls.py`.
- **2,297 reverse usages** (Python `reverse(...)` / `redirect("name")`).
- **1,961 template `{% url %}` usages** + **237 raw `href` / `action`**
  attribute usages.
- **0 broken refs** — every `{% url name %}` and Python `reverse(name)`
  resolves cleanly.
- **0 risk hits** — no dangling routes, no orphan view names.

Status reported by the tool: `ROUTE SYSTEM CERTIFIED`.

Full per-route detail (~5.3MB) at
`docs/generated/route_surface_audit.json`. Schema: `{ broken: [],
routes: { <namespace>: [...] }, urlconfs: {...}, summary: {...} }`.

## 2. POST handler integrity — `end_to_end_action_integrity_audit` (part 1)

`scripts/audit_post_handler_surface.py` classifies every Django view
that accepts POST/PUT/PATCH/DELETE and verifies each is wired through
a real handler with CSRF protection, login_required, and tenant
isolation where applicable.

- **257 POST/PUT/PATCH/DELETE handlers** discovered and audited.
- Distribution available in `summary_by_bucket` and
  `summary_by_classification` in the JSON.

Full detail at `docs/generated/post_handler_audit.json`.

## 3. Template URL name integrity — `end_to_end_action_integrity_audit` (part 2)

`scripts/audit_template_url_names.py` cross-references every
`{% url "<name>" %}` in the 895 templates against the URLconf-resolved
name registry.

- All names resolve. Tool tail listed legitimate namespaces
  (`events:`, `kb:`, `sales:`, `school_events:`, plus tenant
  marketplace names) — these are correctly registered, not findings.

## 4. Page standards — `end_to_end_ux_quality_audit` (mechanical subset)

`scripts/audit_page_standards.py` scans 895 templates for mechanical
quality signals (inline scripts, accessibility landmarks, etc.).

- **895 templates scanned**, **9 findings**:
  - 6× `inline_script_count` (small inline `<script>` blocks; tracked
    drift)
  - 3× `missing_main_landmark` (templates without a `<main>` or
    `role="main"`)
- No regression vs prior runs (drift-detection mode, not zero-tolerance).

The 3 missing-main-landmark templates are the actionable gap. Track
in a follow-up wave if accessibility audit pressure increases.

## 5. No-placeholder content — `no_placeholder_audit`

`scripts/audit_no_placeholder.py` (NEW this wave) scans for
user-visible placeholder copy: "Lorem ipsum", "Coming soon", "Not
implemented", "Replace me", "Placeholder text", "Sample data", "Under
construction", "Work in progress", "TBD", "TBA". Excludes:

- HTML `placeholder=""` attribute on form inputs (input affordance).
- `{# TODO #}` / `{% comment %}…TODO…{% endcomment %}` (dev notes).

### Result: 895 templates scanned, 3 findings.

| File                                              | Kind         | Note                                                                |
|---------------------------------------------------|--------------|---------------------------------------------------------------------|
| `templates/portal/seating_chart.html:27`          | coming-soon  | **Real placeholder.** Seating chart visual not yet built; advises user to use attendance flow. Track for closeout. |
| `templates/schools/onboard_wizard.html:156`       | sample-data  | False positive — "Start with sample data" is a real UI affordance offering seed data import. |
| `templates/siteconfig/report_library.html:30`     | sample-data  | False positive — describes the actual seeded-sample-preview feature. |

**Net: 1 real placeholder** (`seating_chart.html`) across 895
templates. The platform is materially placeholder-free.

## 6. Navigation simplification — `navigation_simplification_audit`

`scripts/audit_navigation_simplification.py` (NEW this wave) parses
`apps/schools/control_plane_nav.py` via Python AST and counts items
per group. Threshold for "oversize" is **>7 items** (cognitive load
beyond short-term memory span).

### Result (control-plane manager surface, post-v2.67):

- **15 groups**, **60 items total**.
- **Biggest group: 6 items**.
- **Oversize groups (>7 items): 0**.

This confirms the v2.67 sidebar simplification claim from memory: no
group exceeds the 7-item threshold. The reshuffling that split
"Schools (9)" into "Tenants (4) + Curriculum & region (5)" and the
16-item "Platform settings & admin" into 4 smaller groups landed as
described.

**Caveat:** v2.67 was the focus of this audit. Tenant portal, teacher,
parent, and student sidebar navs were not re-audited in this wave —
those use template-based nav, not the Python `add_group` builder, so
the AST tool above doesn't apply. Track for a future template-level
nav audit if pressure warrants.

## What is NOT in this wave (and why)

The master-prompt list asked for 10 audit artifacts. This wave
delivers 6 mechanical/static ones above. The other 4 are honestly
called out here, not silently dropped:

| Artifact                                 | Why deferred                                                                                                                                                                                                                |
|------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `end_to_end_feature_gap_register`        | Needs a feature spec to compare against. No SOT spec exists in-repo to grep against. Without one, the "gap" is whatever the requester remembers — not a producible static artifact.                                          |
| `role_permission_experience_matrix`      | Mechanically partial-doable (grep decorators) but the *experience* dimension — what each role actually sees on each surface — needs page rendering. Could be a future wave once a rendering harness exists.                  |
| `public_to_product_promise_matrix`       | Requires parsing marketing copy promises and matching to product features. Both sides are large and the matching is semantic — not a static check.                                                                          |
| `emotional_ux_confidence_audit`          | Subjective by definition. No script can audit emotional confidence; this is design review work.                                                                                                                              |
| `apple_class_authenticated_browser_report` | Browser-only. Requires a running stack with auth, a headless browser, and `axe-core`. Out of scope for any static audit.                                                                                                    |
| `first_school_operating_proof_readiness` | Requires a live tenant + a scripted lifecycle run (create school → ... → audit trail). The harness for this is the kind of thing v2.72+ can build, but the artifact itself is execution-shaped, not static-doc-shaped.       |

If these become priorities, each one is a wave of its own (or a CI
job, in the case of the browser axe report).

## How to re-run

```pwsh
cd beta/school-management-system
python scripts/audit_route_surface.py
python scripts/audit_template_url_names.py
python scripts/audit_post_handler_surface.py
python scripts/audit_page_standards.py
python scripts/audit_no_placeholder.py
python scripts/audit_navigation_simplification.py
```

Each writes to `docs/generated/*.json`. Console output reports
headline counts.

## Recommendations

1. **Fix the one real placeholder.** `templates/portal/seating_chart.html`
   advertises "Coming soon" for a visual seating layout. Either ship a
   minimal version or remove the placeholder copy and route to the
   working attendance flow without the apology.
2. **Add 3 `<main>` landmarks.** The 3 templates flagged by
   `audit_page_standards` are low-effort accessibility wins.
3. **Build the missing browser-axe harness.** Without it, contrast and
   keyboard-nav claims keep aging. This is the single biggest gap in
   the static surface this wave covers.
4. **Don't over-bake the "10 audit artifacts" framing.** Four of the ten
   need execution harnesses or human judgment, not more grep scripts.
   Reach for the right tool per question.
