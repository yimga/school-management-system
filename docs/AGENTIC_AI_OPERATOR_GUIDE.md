# Agentic AI — Operator Guide

**Wave K + Wave P-B · v3.95.1 · 2026-05-26**

The agentic AI primitive is RMC's answer to Canvas IgniteAgent and Gemini-in-Classroom: a **permission-aware, audit-traced action executor** that can suggest *and* (with explicit confirmation) execute parameterized actions on behalf of staff.

## Three principles

1. **Never auto-execute mutating actions.** The agent *proposes*; a human *confirms*; the runner *executes*.
2. Every action declares its required role + tenant scope + reversibility. The verifier blocks anything outside the caller's grant before the runner runs.
3. AI calls route through `services.ai_helpers` ONLY — never `services.ai_gateway`. The boundary scanner enforces this at baseline 0.

## Action registry

8 actions seeded in [services/ai_agentic.py](beta/school-management-system/services/ai_agentic.py):

| Action | Impact | Roles | Auto-confirm? |
|---|---|---|---|
| `summarize_attendance_report` | read_only | TEACHER, DEAN, PRINCIPAL, LEADERSHIP, ADMIN | yes |
| `summarize_outstanding_fees` | read_only | BURSAR, FINANCE_STAFF, PRINCIPAL, LEADERSHIP, ADMIN | yes |
| `draft_parent_announcement` | read_only | TEACHER, COMMS_STAFF, PRINCIPAL, LEADERSHIP, ADMIN | yes |
| `send_parent_message` | mutating | COMMS_STAFF, PRINCIPAL, LEADERSHIP, ADMIN | **no — confirm required** |
| `mark_student_absent` | mutating | TEACHER, PRINCIPAL, LEADERSHIP, ADMIN | **no** |
| `apply_fee_waiver` | mutating | BURSAR, PRINCIPAL, LEADERSHIP, ADMIN | **no** |
| `schedule_parent_callback` | mutating | COMMS_STAFF, ADMIN | **no** |
| `purge_student_record` | **destructive** | PRINCIPAL, LEADERSHIP, DPO, ADMIN | **no** |

## Bridged runners

Wave P-B ships concrete runners for the 3 read-only actions in [services/ai_agentic_runners.py](beta/school-management-system/services/ai_agentic_runners.py):

- `run_summarize_attendance_report` — queries `apps.academics.AttendanceRecord` for today's records on the given class.
- `run_summarize_outstanding_fees` — queries `apps.finance.StudentInvoice` for unpaid rows.
- `run_draft_parent_announcement` — pure text generation (no I/O).

Mutating runners are **intentionally not auto-bridged**. Operators wire them via `execute_action(..., runner=their_runner)` per surface — this enforces that every mutating runner gets a deliberate code review.

## End-to-end flow

```python
from services.ai_agentic import (
    ActionContext, ProposedAction, propose_actions, execute_action,
)
from services.ai_agentic_runners import get_runner_for

ctx = ActionContext(
    tenant_id="t1",
    user_id="staff-42",
    user_roles=("TEACHER",),
    confirmed_by="",  # filled at execute time
)

# 1. Suggest
proposals = propose_actions(prompt="How's attendance in 5A?", ctx=ctx)
# → [ProposedAction(action='summarize_attendance_report', params={'date_range':'today'}, ...)]

# 2. Execute (read-only — no confirmation needed)
result = execute_action(
    proposals[0],
    ctx=ctx,
    runner=get_runner_for("summarize_attendance_report"),
)
# → ExecutionResult(ok=True, result={'summary': '5A: 28/30 present today (93%)...', ...})
```

## Live AI mode

Set `mock_mode=False` in `propose_actions` and pass `helper_invoke_json_task` (typically `services.ai_helpers.invoke_json_task`). The kernel will request a structured response from LiteLLM and **filter unknown action names** before returning — the registry is the authority on what's executable.

## Audit

Every `execute_action` call emits to the `audit_sink` callback (when supplied):

```json
{
  "action": "summarize_attendance_report",
  "tenant_id": "t1",
  "user_id_hash": "abc123...",
  "audit_id": "ag_<sha256-prefix>",
  "executed": true,
  "impact": "read_only"
}
```

`user_id_hash` is SHA-256 truncated — no raw user IDs in audit rows.

## Tests

[services/tests/test_ai_agentic.py](beta/school-management-system/services/tests/test_ai_agentic.py) — 25 unit tests covering permissions, confirmation gating, runner exceptions, audit-sink failures.
