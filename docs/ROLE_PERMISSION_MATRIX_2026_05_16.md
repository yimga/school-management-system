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

| Metric                         | v2.80 | v2.82 |
|--------------------------------|------:|------:|
| URL → view rows                | 633   | 633   |
| Views indexed across apps      | 1,197 | 1,197 |
| Login-gated                    | 539   | **559** |
| Role-gated                     | 56    | **74**  |
| Permission-gated (feature)     | 91    | 91    |
| Candidate-anonymous            | 56    | **36** |
| Unresolved view symbol         | 38    | 38    |

v2.82 improvements:
- Scanner now recognizes 12 more project-specific auth decorators
  (`require_super_access_with_host`, `require_super_access`,
  `require_control_plane_access`, `require_school`, `require_school_permission`,
  `require_feature`, `require_parent_child_access`, `finance_access_required`,
  `evaluation_access_required`, `mfa_required`, `observability_auth_required`,
  `webhook_security_required`). This recategorized 18 routes from
  candidate-anonymous to login/role-gated (no code change — same routes,
  better classification).
- 2 real refactors: `student_portal_grades` and `regulatory_export` had
  inline `if not request.user.is_authenticated` checks that the AST can't
  see. Converted both to `@login_required` decorators — pure refactor,
  same behavior, now auditable from the function signature.

"Login-gated" + "candidate-anonymous" don't sum to 633 because a
view can be DRF-permission-gated without `@login_required`, etc.

## Candidate-anonymous: review hit-list (v2.82 update)

**36 routes** remain after v2.82's triage and decorator-recognition
expansion. **This does NOT mean they're unprotected** — most are
intentional public surfaces, and a handful are protected by middleware
or inline-auth checks the AST can't see.

Rough triage of the 36:

| Bucket                              | Approx | Notes                                                                 |
|-------------------------------------|------:|------------------------------------------------------------------------|
| Auth flow itself (login/logout/redirect, OIDC, SAML) | 10 | Cannot be auth-gated by definition |
| Public knowledge base (KB, FAQ, articles, downloads, search) | 9 | Explicitly public — KB is the help center |
| Token-auth (photo-upload UUID, badge verify, report share token, WOPI) | 9 | Authorize via token in URL, not session |
| Public marketing / release notes / admissions | 3 | Intentional |
| Webhooks (payment provider) | 1 | HMAC-verified inline |
| Onboarding magic-links (teacher / student / parent medal case) | 3 | Token-driven entry points |
| Studio audit JSON (intentional graceful-degrade) | 1 | `studio_audit_api` returns `{audit: []}` for non-authorized users |

### v2.82 confirmed fixes

| Route                       | Was                                                | Now                                |
|-----------------------------|----------------------------------------------------|------------------------------------|
| `student_portal_grades`     | Inline `if not authenticated: redirect_to_login`   | `@login_required` decorator        |
| `regulatory_export`         | Inline `if not authenticated: redirect`            | `@login_required` decorator        |

Both were already authenticated — the refactor just makes the auth
visible at the function signature so reviewers (and the AST scanner)
can see it.

### v2.82 confirmed-protected via custom decorators (originally flagged)

The 6 marketplace/metadata routes flagged in v2.80 turned out to be
protected by `@require_super_access_with_host` — a project-specific
control-plane gate that requires (1) manager host or `/super/` path
AND (2) authenticated user AND (3) SUPERADMIN role. The scanner was
just blind to that decorator name. Adding it to `KNOWN_AUTH_DECORATORS`
recategorizes all 6 plus 12 others.

| Route                          | Decorator                                  |
|--------------------------------|--------------------------------------------|
| `publisher_dashboard`          | `@require_super_access_with_host`          |
| `publisher_app_detail`         | `@require_super_access_with_host`          |
| `metadata_search_api`          | `@require_super_access_with_host`          |
| `metadata_governance_ui`       | `@require_super_access_with_host`          |
| `metadata_lineage_api`         | `@require_super_access_with_host`          |
| `metadata_lineage_graph_ui`    | `@require_super_access_with_host`          |

This is the value of the matrix: surface candidates, then a code
review either confirms protection (and the scanner learns) or
finds a real gap (and the code gets fixed).

## CI gate (v2.82)

The scanner now exits 1 when the candidate-anonymous count exceeds
a passed-in maximum:

```pwsh
python scripts/audit_role_permission_matrix.py --max-candidate-anonymous 36
```

This is wired into `.github/workflows/architectural-boundaries.yml`
as a new `rbac-matrix` job. **Baseline pinned at 36.** Any new route
that lands without a recognized auth decorator (or middleware
documentation via `# rbac-allow: <reason>`) makes the CI gate fail.

### How to update the gate

When you legitimately reduce the count (by fixing a route or by
teaching the scanner about a new decorator), open
`.github/workflows/architectural-boundaries.yml`, find the
`rbac-matrix` job, and lower the `--max-candidate-anonymous` value.
**Never raise the number** — that silences the scanner. Triage every
new entry first.

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
