# §0.1.5 / Wave 8 — verification stub

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§0.1.5** and **§0.1.5.1** (full narrative, checkboxes, and closure policy).

**Do not duplicate status here.** Row-level completion and external caveats live **only** in the SOT and in **[SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md)** (external OPEN table).

## Commands (repo)

```bash
python scripts/verify_sot_pillar_evidence.py
python -m pytest apps/portal/tests/
# Full gate (see TEST_DATABASE.md on Windows):
# bash scripts/pre_deploy_gate.sh
```

## Django tests + `render()`

`django.shortcuts.render()` returns `HttpResponse` **without** `response.context`. Tests should patch `render`, assert on response body (`assertContains`), or use other patterns — see portal tests.
