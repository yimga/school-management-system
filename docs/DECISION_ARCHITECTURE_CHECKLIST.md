# Decision architecture checklist (§1.8 / §8.0)

**Purpose:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §1.8 and §8.0. Every important page, dashboard, workflow, and control must answer seven questions before acceptance. This checklist is the formal declaration template.

**Authority:** RUNMYCAMPUS §8.0 enforces that **no new or materially changed** dashboard, page, workflow, or control is accepted unless it declares these seven answers (in code or in a registry/doc). Use this checklist in PRs or attach to [DASHBOARD_TAXONOMY_AND_REGISTRY.md](DASHBOARD_TAXONOMY_AND_REGISTRY.md) when adding dashboards.

**Reference:** Full wording and enforcement policy: [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md) (Decision architecture meta-layer).

---

## The seven questions (declare before merge)

| # | Question | Your answer (required) |
|---|----------|------------------------|
| 1 | **Who is this for?** (primary user / role) | e.g. school admin, teacher, parent, operator, super |
| 2 | **What question are they asking?** (primary job-to-be-done) | e.g. "What do I need to do next?" "Where are my child's grades?" |
| 3 | **What state are they in?** (context) | e.g. setup, operational, post-launch, first-time, returning |
| 4 | **What action should they take next?** (primary CTA / next-best-action) | e.g. "Open workflow center", "Pay fees", "View report" |
| 5 | **What confidence signal do we show?** (state clarity, success/error, progress) | e.g. progress bar, status badge, empty state, error message |
| 6 | **What happens if they are wrong?** (wrong-path handling, validation, recovery) | e.g. validation message, rollback, undo, help link |
| 7 | **What is the fallback path?** (escape hatch, help, support, rollback) | e.g. "Back to dashboard", "Contact support", "Cancel" |

---

## When to use this checklist

- **New dashboard or page:** Fill the table above and add the dashboard to [DASHBOARD_TAXONOMY_AND_REGISTRY.md](DASHBOARD_TAXONOMY_AND_REGISTRY.md) with the same declarations.
- **Materially changed** existing dashboard/page/workflow/control: Update the registry row or attach this checklist to the PR with the seven answers filled.
- **New workflow or control surface:** Either add a row to a registry (e.g. workflow catalog) that includes these seven fields, or attach this checklist with answers.

**Enforcement:** Reviewers and merge gates expect the seven answers to be declared (in this checklist, in DASHBOARD_TAXONOMY_AND_REGISTRY, or in code/registry) before accepting the change. No open loop.

---

## Optional: in-code declaration (pattern choice; seven answers remain required)

For pages that are code-first, you may declare the seven answers in code (e.g. a view that passes a `decision_architecture` dict to the template, or a registry module). The checklist above remains the canonical template; in-code declarations should map 1:1 to these seven questions. **All seven answers are non-negotiable** whether declared in this checklist, in the dashboard registry, or in code.

**Example (Python):** View or context can pass a dict with keys aligned to the seven questions:

```python
DECISION_ARCHITECTURE_KEYS = (
    "who_is_this_for",
    "what_question_are_they_asking",
    "what_state_are_they_in",
    "what_action_should_they_take_next",
    "what_confidence_signal_do_we_show",
    "what_happens_if_they_are_wrong",
    "what_is_the_fallback_path",
)
# In view context: decision_architecture = {k: "..." for k in DECISION_ARCHITECTURE_KEYS}
```

**Example (template):** When using the dashboard registry, the seven answers are stored in [DASHBOARD_TAXONOMY_AND_REGISTRY.md](DASHBOARD_TAXONOMY_AND_REGISTRY.md); new dashboards must add a row with the same semantics.

---

## Completion gate

- [x] Checklist doc exists in repo (`docs/DECISION_ARCHITECTURE_CHECKLIST.md`).
- [x] When-to-use and enforcement stated (declare before acceptance; reviewers/merge gates expect seven answers).
- [x] DASHBOARD_TAXONOMY_AND_REGISTRY and DESIGN_SYSTEM_BEHAVIOR reference this checklist and §1.8/§8.0.
- [x] Optional in-code declaration pattern documented (dict keys + registry).

**Status:** **DONE.** Decision architecture is enforceable: checklist and template are in repo; OPERATING_DISCIPLINE_LAYERS, DASHBOARD_TAXONOMY_AND_REGISTRY, and DESIGN_SYSTEM_BEHAVIOR require alignment; no new or materially changed dashboard/page/workflow/control is accepted without the seven answers declared.
