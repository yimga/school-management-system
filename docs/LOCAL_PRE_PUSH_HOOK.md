# Local pre-push boundary-gate hook

## Why this exists

`architectural-boundaries.yml` — the workflow that runs every zero-tolerance
CSS/template gate (`scan_undefined_css_classes`, `scan_off_token_colors`,
`scan_theme_locked_token_text`, `scan_inline_style_off_token`,
`audit_template_render_safety`, `scan_attribute_context_includes`,
`verify_service_worker_version`) — triggers **only on `pull_request`** (plus
manual `workflow_dispatch`). A commit pushed straight to `main` never runs it,
so redness lands on the default branch and is only discovered later, when some
unrelated PR finally runs the workflow.

The usual fix — making `architectural-boundaries` a **required status check** via
GitHub branch protection — is **not available on this repository**: it is private
on the free plan, and the branch-protection API returns
`403 Upgrade to GitHub Pro or make this repository public`. So the only
enforcement lever left is *local*: run the fast gates before the push leaves the
machine.

That is what this hook does. It is a client-side mirror of the CI job's
stdlib-only gates (the fast subset, and precisely the subset that has repeatedly
shipped red to `main`).

## Install (once per clone)

```sh
python scripts/install_git_hooks.py          # install / refresh
python scripts/install_git_hooks.py --check   # report status (exit 1 if missing)
python scripts/install_git_hooks.py --uninstall
```

Hooks live in `<git-dir>/hooks/` and are **not** version-controlled; the
version-controlled source of truth is [`.githooks/pre-push`](../.githooks/pre-push)
plus the runner [`scripts/pre_push_boundary_check.py`](../scripts/pre_push_boundary_check.py).
Run the installer in **every** clone that pushes (including the one the
peer/agent session works from — that is the clone that has been landing red).

## Behaviour: warn by default, strict on demand

* **WARN (default).** Every gate runs; failures are reported loudly, but the push
  is **not** blocked (exit 0). This makes it safe to install into a shared clone —
  it will never wedge a push mid-flight, even if the working tree is currently red.
* **STRICT.** Set `RMC_PREPUSH_STRICT=1` (or run the checker with `--strict`) and a
  red gate aborts `git push`. Turn this on once your tree is clean and you want the
  machine to hold the line.

```sh
python scripts/pre_push_boundary_check.py            # warn-only, ad-hoc
python scripts/pre_push_boundary_check.py --strict   # block on red
python scripts/pre_push_boundary_check.py --list     # show the gate list
RMC_PREPUSH_STRICT=1 git push                        # block via env for one push
```

## Keeping it in sync with CI

`GATES` in `scripts/pre_push_boundary_check.py` mirrors the CI step invocations in
`.github/workflows/architectural-boundaries.yml` **flag-for-flag** — a green run
here means a green `architectural-boundaries` job there. When a gate is added,
removed, or re-flagged in that workflow, update `GATES` to match.
`scripts/tests/test_pre_push_boundary_check.py` locks the warn/strict contract and
that every referenced gate script + flag still exists.

## Scope

This hook covers only the **stdlib-only** boundary gates (no Django import), which
is both the fast subset and the one that catches CSS/template redness. Django-
dependent gates (reference-integrity family, RBAC coverage, migration drift, the
full test suite) still run in CI (`ci.yml`) and are not duplicated here — the goal
is a sub-10-second pre-push check, not a full CI mirror.
