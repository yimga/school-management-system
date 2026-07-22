# Eager filter-arg VariableDoesNotExist — completion prompt

**Pass token (only when the verifier prints it):** `EAGER_FILTER_ARG_COMPLETION_PASS`

## What this seals

Django resolves every filter **argument** eagerly. A missing top-level context
variable used as a `|default:`, `|default_if_none:`, `|slice:`, or `|add:`
argument raises `VariableDoesNotExist` and **500s the page** — even when the
left-hand value is already set.

Production incident (2026-07-22): `/super/schools/` and `/configuration/` failed with
`Failed lookup for key [ops_surface]` inside
`{% include … with page_host=page_host|default:ops_surface|… %}`.

## Hard rule for agents

Do **not** claim this class is fixed, closed, sealed, or “done” until:

```bash
python scripts/verify_eager_filter_arg_completion.py
```

prints **`EAGER_FILTER_ARG_COMPLETION_PASS`** (exit code 0).

A green static scanner alone is **not** completion. The completion verifier also
proves banned patterns are gone, CI/pre-push wiring exists, Django behavioral
seals hold, sparse-context renders of the ops-center frame and planner strip
succeed, every ops-frame consumer is clean, and the Django regression module is green.

### Static-only subset (deps-free CI)

```bash
python scripts/verify_eager_filter_arg_completion.py --static-only
```

Still must exit 0. Full completion for a ship claim requires the **full** run
(without `--static-only`).

## Safe patterns

- Literal defaults only: `|default:""`, `|default:":5"`, `|default:_("…")`, `|default:None`, `|default:False`
- Bind optionals first: `{% with lim=backend_max_items_slice|default:":5" %}…|slice:lim…{% endwith %}`
- Prefer `{% if %}` / `{% firstof %}` over `|default:other_context_var`
- Proven in-scope loop/`{% with %}` names may use `{# default-fallback-allow: <reason> #}` on the same line or the line above

## Forbidden

- `|default:ops_surface`, `|default:ops_page_archetype`, `|default:PREVIEW_NOTE`
- `|slice:backend_max_items_slice` without a prior literal-safe binding
- `|default:SITE_THEME` / `|default:SITE` as theme fallbacks
- Claiming done from narrative, partial scanners, or a single page smoke check

## Audit artifact

On every run the verifier writes:

`docs/generated/eager_filter_arg_completion_audit.json`

Inspect failed rows there before declaring progress.

## Related gates

- `scripts/scan_include_with_default_context_var.py --strict` (static 0-findings)
- `scripts/tests/test_scan_include_with_default_context_var.py`
- `apps/platform_runtime/tests/test_operational_center_frame_include.py`
