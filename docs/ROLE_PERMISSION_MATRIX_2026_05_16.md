# Role / permission matrix — 2026-05-16 (v2.75)

Static cross-reference of every URL pattern to its view's
access-control decorators. Designed to catch the class of bug
the master-prompt called out: "real bugs hide in this kind of
table — it's how access-control regressions get caught."

## How it works

`scripts/audit_role_permission_matrix.py` AST-walks every
`apps/*/views*.py`, extracts decorators per function/class, then
AST-walks every `apps/*/urls.py` to map `path("X", view)` patterns
back to the view. The result is a row per URL with: decorators,
DRF permission_classes, role-required list, and four boolean
flags (`login_gated`, `role_gated`, `permission_gated`,
`candidate_anonymous`).

Output:
- `docs/generated/role_permission_matrix.json` — canonical
- `docs/generated/role_permission_matrix.csv` — open in any
  spreadsheet for filter/sort

## Headline numbers

| Metric                         | Count |
|--------------------------------|------:|
| URL → view rows                | 633   |
| Views indexed across apps      | 1,197 |
| Login-gated                    | 539   |
| Role-gated                     | 56    |
| Permission-gated (feature)     | 91    |
| Candidate-anonymous            | 56    |
| Unresolved view symbol         | 38    |

"Login-gated" + "candidate-anonymous" don't sum to 633 because a
view can be DRF-permission-gated without `@login_required`, etc.

## Candidate-anonymous: review hit-list

56 routes have no detected `@login_required` / `@role_required` /
`@permission_required` decorator and no DRF `permission_classes`.
**This does NOT mean they're unprotected** — many are intentional
public surfaces, and others are protected by middleware (RLS,
TenantContextMiddleware, custom auth handlers).

Rough triage of the 56:

| Bucket                              | Approx | Notes                                                                 |
|-------------------------------------|------:|------------------------------------------------------------------------|
| Intentional public (auth flow, marketing, KB, FAQ, release notes, healthz, webhooks) | ~40 | Verified safe by spot-check |
| Magic-link / token-auth (photo-upload, badge-verify, OIDC/SAML callbacks) | ~7 | Authorize via token in URL, not session |
| Admissions / applicant-facing | ~3 | Anonymous applicants by design |
| **Worth review** | **~6** | publisher_dashboard, publisher_app_detail, metadata_search_api, metadata_governance_ui, metadata_lineage_api, metadata_lineage_graph_ui |

The 6 routes worth review are in `apps/marketplace/urls.py` and
`apps/metadata/urls.py`. They render dashboards / governance UIs
that should plausibly require login (or operator role). Confirm
each is either:
- Protected by middleware (then we leave a `# rbac-allow: <reason>`
  marker for next-time-the-scanner-runs honesty), OR
- Genuinely a gap (add the right decorator).

This is a **scanner**, not a verdict. The 6 routes are starting
points for a code review, not bug reports.

## Unresolved: 38 routes

Routes whose `view_symbol` doesn't match any function/class in
`apps/*/views*.py`. Common causes:
- Cross-app import (`from apps.X.views import Y as Z`) where the
  alias `Z` isn't a top-level symbol in any local `views*.py`.
- DRF generic views built by `as_view()` at import time.
- Imperative wrapping (`url_view = login_required(view)`) in the
  URLconf.
- Lambda / functools.partial / factory-built handlers.

These show up with empty decorator lists but are flagged
`unresolved=true` rather than `candidate_anonymous=true` so they
don't pollute the security-review list. The CSV has a separate
`unresolved` column for filtering.

## Role-gated breakdown (56 routes)

| Role required          | Route count |
|------------------------|------------:|
| ADMIN (incl. variants) | high        |
| TEACHER                | medium      |
| BURSAR                 | low         |
| PARENT / STUDENT       | low         |

Use the CSV's `roles_required` column to filter.

## What this scanner does NOT catch

- **Middleware-based protection.** RLS, TenantContextMiddleware,
  AccessControlMiddleware are not detected — a view can be
  effectively protected without any decorator on the view itself.
- **Imperative wrapping in `urlpatterns`.** If someone writes
  `path("X", login_required(view_fn))`, my regex sees `login_required`
  as the "view symbol" and gets confused. (Real prevalence: low.)
- **Conditional decorators.** `if SOMETHING: @decorator` is
  AST-detected but classification assumes the decorator always
  applies.
- **Custom middleware acting as auth.** Tenant middleware that
  rejects requests by role is invisible to a per-view AST walk.

The scanner is the **first pass**, not the SOT for access control.
Per-route deep review is still required for security-critical
surfaces.

## How to re-run

```pwsh
cd beta/school-management-system
python scripts/audit_role_permission_matrix.py
```

Output lands in `docs/generated/role_permission_matrix.{json,csv}`.

## Open the matrix as a spreadsheet

```pwsh
# Windows
start docs/generated/role_permission_matrix.csv
```

Filter `candidate_anonymous = 1` + `urls_file != marketing*` for
the review hit-list.

## Recommendations

1. **Triage the 6 marketplace/metadata routes** flagged above.
   Either confirm protection-by-middleware (add `# rbac-allow:`
   marker so future scanner runs are silent) or wrap with the
   right decorator.
2. **Resolve the 38 unresolved entries** if you want full
   coverage — most are aliased imports the scanner can be taught
   about by tracking `from X import Y as Z` in URLconfs. Worth
   doing if you start relying on the matrix for security signoff.
3. **Run on every PR** by adding it to `architectural-boundaries.yml`
   with a baseline (the `candidate_anonymous` count = 56) so any
   *new* anonymous-candidate route requires explicit justification
   in a marker comment. Same pattern as the other scanners.
