# N28 — Predictive / proactive platform (roadmap)

**Shipped (partial):** `StudentAtRiskSignal` sync from nightly `RiskFactor`; intervention workflow + audit (BR-06 / EWS). Dashboard hooks vary by role.

**Shipped (increment 2026-03):** **`GET /api/internal/north-star/upcoming-deadlines/`** — JSON list of upcoming **grading deadlines** (from `SubjectAssignment.grading_deadline_at`) plus **public calendar** entries (`_merged_upcoming_events`); tenant scope via `school_id` or `request.school`. Teacher dashboard already surfaces a **7-day horizon** subset (`teacher_deadline_items` in `evals` teacher dashboard).

## Next product increments

| Increment | Description | Owner hint |
|-----------|-------------|------------|
| **Deadlines** | Extend beyond grading+calendar: fee / compliance deadlines on role-home; wire API to BI/parent cards. | Academics + finance |
| **Suggested actions** | Extend `get_recommended_next_steps` / Studio recommendations with rule-based “if overdue then …”. | Dashboard |
| **Parent/student** | Portal cards: “Action required” from requests + attendance anomalies. | Portal |

## Non-goals

- Black-box ML scoring without audit trail — any new signal must log to `PlatformEventLog` or domain audit.

**SOT:** Mark N28 **[x] structural** only when the increments above are **product-signed**; until then keep **[ ]** with this roadmap linked.
