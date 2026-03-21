# Template editing convention (single tree)

**Gap closed:** Duplicate-looking paths such as `templates/finance/...` vs `templates\finance\...` must not drift. On Windows the OS may treat them as one directory, but editors and tools can target different spellings.

**Rule for agents and humans**

1. Always reference and edit templates under **`templates/`** using **forward slashes** only (e.g. `templates/finance/invoices.html`).
2. After edits, run template source tests that read from `Path(BASE_DIR) / "templates" / ...` (e.g. `apps/finance/tests/test_finance_form_draft_templates.py`).
3. If CI or a second checkout shows divergent copies, reconcile to the forward-slash path and remove stray duplicates.

**Related:** [MEGA_FILE_SPLIT_PLAN_BR12.md](MEGA_FILE_SPLIT_PLAN_BR12.md), RESILIENT_EDGE / N3 rows in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).
