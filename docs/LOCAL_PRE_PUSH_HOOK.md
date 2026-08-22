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

## Behaviour: enforcing by default, override on demand

**This inverted on 2026-08-21.** It was warn-by-default, on the reasoning that a
shared clone should never wedge a teammate mid-push. That reasoning assumed
something downstream would catch whatever slipped through — and nothing does.
Branch protection is unavailable on this plan (see above), and **GitHub Actions
has started no job since 2026-08-15**: each run is created and immediately refused
with *"The job was not started because an Actions budget is preventing further
use"*, so every workflow reports red without ever executing. Warn-only on top of
that meant nothing, anywhere, enforced anything.

* **ENFORCING (default).** A failed gate exits non-zero and `git push` aborts.
* **WARN-ONLY (override).** `--warn-only`, or `RMC_PREPUSH_STRICT=0`. Still one env
  var away on purpose: the goal is not to make the override hard, it is to make
  skipping a red gate a decision someone made and can be seen in a shell history,
  rather than the silent default.
* **Timeouts are not findings.** A gate that exceeds the ceiling reports
  `TIMED OUT … this is a RESOURCE result, not a finding` and names the command to
  re-run it alone. The ceiling is `RMC_PREPUSH_GATE_TIMEOUT_S` (default **600s**),
  deliberately generous — several agents share this machine, and a squeezed ceiling
  manufactures failures that look exactly like real ones. On 2026-08-21
  `python-files-parse` "failed" at the old 120s while being entirely clean (8,617
  files, 0 findings). Raise the ceiling before reaching for the override.

```sh
python scripts/pre_push_boundary_check.py              # enforcing (default)
python scripts/pre_push_boundary_check.py --warn-only  # report, exit 0
python scripts/pre_push_boundary_check.py --list       # show the gate list
RMC_PREPUSH_STRICT=0 git push                          # override for one push
RMC_PREPUSH_GATE_TIMEOUT_S=1200 git push               # slow or busy machine
```

## Keeping it in sync with CI

`GATES` in `scripts/pre_push_boundary_check.py` mirrors the CI step invocations in
`.github/workflows/architectural-boundaries.yml` **flag-for-flag** — a green run
here means a green `architectural-boundaries` job there. When a gate is added,
removed, or re-flagged in that workflow, update `GATES` to match.
`scripts/tests/test_pre_push_boundary_check.py` locks the enforcement contract
(blocks by default; `--warn-only` and `RMC_PREPUSH_STRICT=0` release it; an
exported-but-empty value is not an override) and that every referenced gate script
+ flag still exists.

## Scope

This hook covers only the **stdlib-only** boundary gates (no Django import), which
is both the fast subset and the one that catches CSS/template redness. Django-
dependent gates (reference-integrity family, RBAC coverage, migration drift, the
full test suite) still run in CI (`ci.yml`) and are not duplicated here — the goal
is a sub-10-second pre-push check, not a full CI mirror.
