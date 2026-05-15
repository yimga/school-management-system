# Tenant-isolation queryset safety scanner

## Why this exists

Postgres Row-Level Security (RLS) is the platform's last-line defence
against cross-tenant data leakage. RLS is set by the
`SET app.current_school_id = ...` session-bound binding the request
middleware installs. **It is non-negotiable.**

But RLS is a backstop. A queryset that forgets to filter by
`school=` runs *correctly* against RLS today — and *incorrectly* the
moment someone deploys the platform with RLS disabled, or runs a
management command outside a request cycle, or chains an unscoped
queryset that escapes the binding.

The scanner encodes every `<TenantModel>.objects.filter()` / `.get()` /
`.all()` call site in `apps/` that does not include a `school=` /
`school_id=` / `school__in=` / `school_id__in=` kwarg, then compares the
result against a committed baseline. CI fails any pull request that
introduces a *new* unscoped query without explaining it.

## What "tenant-scoped" means here

A model is tenant-scoped if its class body assigns either
`school = ...` or `school_id = ...`. The scanner walks
`apps/**/models*.py`, AST-parses every `class ... :` block, and records
the model name when either field is present. As of 2026-05-14 this
yields 194 distinct tenant-scoped model names across all apps.

## Running it

```bash
# Show the current scan result (does not write anything):
python scripts/scan_tenant_queryset_safety.py

# Just the summary header, no per-line findings:
python scripts/scan_tenant_queryset_safety.py --summary

# Rewrite the committed baseline (only after you fix or accept a
# finding):
python scripts/scan_tenant_queryset_safety.py --write-baseline

# Compare current code against the baseline; non-zero exit if any
# new finding exists:
python scripts/scan_tenant_queryset_safety.py --compare
```

The baseline is committed at
`var/security-audit-baseline-tenant-isolation.json`.

CI workflow:
[`.github/workflows/tenant-isolation-scan.yml`](../.github/workflows/tenant-isolation-scan.yml)
runs `--compare` on every PR that touches `apps/**/*.py`, the scanner
itself, or the baseline.

## How to fix a flagged finding

When CI reports a new unscoped query at, say,
`apps/finance/views.py:142  Invoice.objects.filter(...)  (no_school_filter)`:

1. Read the line. Is the queryset already scoped by some earlier
   `.filter()` in the same chain that the scanner couldn't see?
   - If yes, **make the scoping explicit** in this call. Add the
     `school=request.school` kwarg. The scanner trades recall for
     precision; it cannot chase cross-file chains, and that's by
     design — making the binding explicit costs nothing and improves
     readability.
2. Is the queryset truly cross-tenant by intent (a control-plane
   admin operation, an aggregate across schools)?
   - Move the call behind a control-plane permission gate (it should
     already be — verify it is).
   - Then update the baseline: `python scripts/scan_tenant_queryset_safety.py
     --write-baseline` and commit the changed JSON with the new finding
     plus a one-line justification in the PR description.

## What the scanner does *not* catch

It is precision-tuned. It will miss:

- **Chained querysets** across files
  (`qs = Model.objects.all()` exported from one module and `.filter()`'d
  in another). Make the binding explicit at the head of the chain.
- **Dynamic attribute lookup** (`getattr(Model, "objects").filter(...)`).
- **Custom managers** with implicit tenant scoping baked in. The
  scanner assumes `Model.objects` is the default `Manager` and flags
  anything that looks unscoped. If you've written a tenant-aware
  manager, document it inline and either: (a) re-name the model
  attribute so it doesn't match `objects`, or (b) accept the noise on
  the baseline.
- **`.raw()` SQL.** Out of scope; review separately.

Cross-tenant data leakage is one of the highest-severity defects this
platform can ship. The baseline is intentionally large (769 findings as
of 2026-05-14) because the scanner is precision-tuned and many findings
are chained-querysets that *are* tenant-bound at the head of the chain.
The point of the baseline is to **stop the count from growing.**

## Roadmap

1. **Burn down the baseline.** Pick a high-count app per wave (e.g.
   `evals` has 118 findings) and make every query explicit. Each
   commit that reduces the count is a net security improvement.
2. **Extend to write paths.** The scanner currently audits
   `.filter()` / `.get()` / `.all()`. `Model.objects.create()` /
   `.update()` / `.delete()` are next.
3. **Promote to a hard pre-commit hook.** Once the baseline is under
   ~100 findings, run on every commit, not just on CI.

See also: [SECURITY.md](SECURITY.md),
[PENTEST_SOW_2026_05_14.md](PENTEST_SOW_2026_05_14.md),
[`apps/schools/migrations/0048_*.py`](../apps/schools/migrations/)
(RLS owner-role binding).
