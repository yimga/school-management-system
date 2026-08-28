# Gate detector-integrity audit — 2026-08-28

**Status:** harness landed and running clean; three gates confirmed broken with
evidence; the rest of the DEAD list is an open work queue, not a conclusion.

## Why

This repository defends itself with 64 pre-push gates. On a good day all 64
print PASS — and PASS answers two completely different questions with the same
word:

1. the tree is clean, or
2. the gate cannot see.

Nothing here could tell those apart. `verify_ci_gate_wiring.py` closed the
neighbouring hole — it proves a gate is *invoked* — but it cannot prove that a
gate, once invoked, does anything at all.

Case 2 is not hypothetical here. Four gates wired on 2026-08-27 carry
"existed, passed, and enforced nothing" in their own registry comment.
`verify_audit_log_append_only` matched the last two names of an attribute chain,
so it could only ever see a bare `AuditLog.objects.update()` — a form that is
not valid Django and nobody writes — and printed PASS while a real
`filter(...).update()` sat in `apps/compliance/privacy.py`.
`scan_sms_template_length` only opened files whose *name* said sms.

## Method

`scripts/verify_gates_can_fail.py` holds one mutation per gate: a small,
specific defect of exactly the class that gate claims to catch. It plants the
defect, runs the gate, and calls the gate DEAD if it still exits 0.

Two structural rules make it hold its shape:

* **Completeness.** Every label in `pre_push_boundary_check.GATES` and
  `DJANGO_GATES` must carry a mutation or an entry in `UNPROVEN` with a written
  reason. A new gate cannot arrive without its own proof — the same trick
  `verify_ci_gate_wiring.REQUIRED_GATES` uses. This found a gate on its first
  run: there are **64**, not the 63 anyone had been counting.
* **Isolation.** Mutations are applied in a detached worktree, never the shared
  checkout, which routinely carries other agents' uncommitted work. Isolation
  also makes the restore path non-critical: a background timeout has killed a
  mutation harness here before, after which `finally` never ran.

## Results

| verdict | count | meaning |
| --- | --- | --- |
| PROVEN | 42 | planted its own defect, gate went red |
| DEAD (confirmed) | 3 | gate stayed green, blindness reproduced by hand |
| DEAD (unadjudicated) | 10 | gate stayed green, cause not yet established |
| DRIFTED | 2 | the mutation's anchor no longer exists in the tree |
| EXEMPT | 8 | no single-file defect models the contract; reason written down |

65 gates. Full run 241s in a reused worktree; the `--list` completeness arm,
which is the part wired into pre-push, runs in 0.15s.

A DRIFTED verdict is a finding in its own right: the proof stopped proving and
said so, rather than quietly passing.

## The harness's own first bug

The first run produced nineteen DEAD verdicts. SIX of them were the harness's
fault, not the gates'. Three shared one root cause, and it is worth writing down
because it is the same failure mode the tool exists to catch.

Planted files were created **untracked**. Several scanners enumerate their
corpus with `git ls-files` rather than walking the filesystem —
`scan_duplicate_dict_keys` says so in its own docstring — so the planted defect
was invisible and the gate returned a truthful, useless zero. Exactly a detector
reporting clean because it could not see.

Planting now uses `git add -N`, and the between-case cleanup is `reset --hard`
rather than `checkout -- .` (an intent-to-add entry survives both `checkout` and
`clean -fd`, and would leak into the next gate's corpus).

The other three bad mutations were shape errors, each instructive: an unclosed
`<span>` where the balance walker deliberately tolerates phrasing elements a
browser auto-closes; a marker removed once where it occurs twice, so the gate's
`"marker" in text` still found the survivor; and pages whose filename or parent
template put them outside the corpus the gate collects.

That is why a DEAD verdict is treated as a **hypothesis**. A gate is only
reported as broken once the blindness has been reproduced a second way, by hand,
and the evidence written into `CONFIRMED_DEAD`. Everything else prints
UNADJUDICATED.

## Confirmed findings

### 1. `rls-force-coverage` never checks FORCE

The string `FORCE` appears exactly once in `scripts/scan_rls_force_coverage.py`
— in its docstring. The actual test is filename substring matching:

```python
has_enable = any("enable_rls" in n for n in names)
has_deny = any("rls_policy_default_deny" in n or "rls_default_deny" in n for n in names)
```

Emptying all four RLS migrations in `apps/academics` to `operations = []`, with
the filenames kept, still reports `rls_force_coverage scan: 0 gap(s)`.

This matters because of the property the gate is named for. PostgreSQL exempts a
table's **owner** from its own row policies unless `FORCE ROW LEVEL SECURITY` is
set, and Django connects *as* the owner. Without FORCE the policies are
decorative on the one connection that matters — and that is the isolation
mechanism on every sovereign edge box running `USE_DJANGO_TENANTS=0` + RLS. The
gate has never verified it on any table.

### 2. `rls-policy-coverage` is content-blind

Same shape, narrower claim. It pairs `*enable_rls_postgresql*.py` against
`*rls_policy_default_deny*.py` by filename and never opens either file. The
gutted-migration tree above still prints "every enable_rls_postgresql migration
has a matching rls_policy_default_deny".

The gate does what its own docstring says — it is a structural pairing check. It
is the pre-push registry comment that oversells it ("the property they protect
is the isolation mechanism on every sovereign edge box"). An empty migration
with the right name satisfies both this gate and #1.

### 3. `broad-except-baseline` is blind to every new file

In `--allowlist` mode — which is how both `pre_push_boundary_check.py` and
`architectural-boundaries.yml` invoke it — the comparison iterates the
**allowlist's** keys, not the scan's:

```python
for path, allowed_count in sorted(allowlist.items()):
    actual = counts.get(path, 0)
    if actual > allowed_count:
        violations.append(...)
```

A file absent from the allowlist is never examined. A new tracked module
carrying both `except Exception:` and `except BaseException:` passes cleanly.

The gate can only ratchet already-listed files downward. It cannot see a new
broad except anywhere — which is the direction the registry comment says it was
wired to protect: "A broad `except Exception` swallows the failure it was not
written for. One around edge-TLS would have settled a box on plain HTTP in
silence."

The capability exists; the invocation bypasses it. Without `--allowlist` the
same scanner finds the pre-existing population immediately.

## Open queue

The remaining DEAD verdicts are unadjudicated. Each is either a real blind spot
or a badly-shaped mutation, and the only way to know is to reproduce it by hand,
the way the three above were. They are listed in the harness output and in
`CONFIRMED_DEAD`'s absence, not hidden.

Two mutations are DRIFTED — their anchors no longer exist in the tree. A drifted
anchor is also a finding: the proof stopped proving and said so, rather than
quietly passing.

## Related: 13 worktrees that can delete the repository

Found while building the above, and fixed by `scripts/audit_worktree_health.py`.

Forty worktrees are registered against this checkout. `git worktree prune`
clears exactly one — it only removes worktrees whose directory is *gone*.
Thirteen others are **hollow**: the directory still exists, the checkout has been
gutted (a cleared scratchpad, a temp sweeper, a killed `git worktree add`), and
the index still lists every tracked file. `git status` inside them reports
**181,034 deletions in total**, 15,620 in the worst one. A single `git commit -a`
in any of those directories removes the tree.

All thirteen are fully merged into `origin/main`, so nothing is lost by removing
them. The tool checks that before offering any of them, and reports UNKNOWN —
refusing removal — when the check cannot be answered.
