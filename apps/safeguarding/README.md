# apps/safeguarding

> Child-protection concern intake, the KCSIE-2026 category registry, and the
> Designated Safeguarding Lead (DSL) handoff.

**Tenancy:** SHARED (public schema; rows are scoped by an explicit `school` reference, not by a Postgres schema)
**Scale:** 0 models · 0 migrations · 3 test modules · ~1.4k LOC

## What this app owns

Safeguarding is the pathway a member of staff uses to raise a concern about a
child, and the pathway a Designated Safeguarding Lead uses to triage it. It owns
three things: the concern lifecycle FSM, the KCSIE-2026 category registry that
classifies a concern and decides whether it is urgent, and the DSL notification
handoff that turns a submitted concern into an actionable inbox entry.

The defining design decision is that `concern_kernel.py` is **storage-agnostic**.
It does not write anything. A transition returns the next state, the audit row,
and the ledger entry as plain data, and the *caller* persists them. That is what
makes the FSM and the category rules testable without Django's audit chain, and
it is why this app declares no models at all.

Concern lifecycle:

```
DRAFT -> SUBMITTED -> ACKNOWLEDGED -> ACTION_TAKEN -> CLOSED
                            |
                            +-------> REFERRED_EXTERNAL -> CLOSED
```

## Key models

**None — this app declares no Django models and ships no migrations.** That is
deliberate, not an omission. Concern state and the DSL inbox live in the
`School.settings["safeguarding"]` JSON bucket (`dsl_inbox` is a parallel FIFO
list capped at 200 entries per tenant), so the whole slice adds zero migrations.
If you are looking for a `SafeguardingConcern` table, it does not exist.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `audit_privilege_context_task` | Privilege-context audit sweep (`tasks.py`) |
| Module | `concern_kernel` | Pure FSM + KCSIE category registry; returns state, no writes |
| Module | `dsl_notify` | Best-effort DSL inbox entry with a deep-link to the concern |
| Module | `wizard_config_kernel` | Safeguarding setup-wizard configuration |

This app exposes no URLs of its own (no `urls.py`); its views are reached through
the surfaces that embed it.

## Before you change this

- **PII must not spread.** The kernel runs a regex pass over concern narrative
  text to strip email/phone-like strings before it reaches the ledger, so the
  audit row keeps the *shape* of the narrative but not contact details — those
  belong on `StudentProfile` / guardian rows and must not be duplicated here.
  `dsl_notify` follows the same rule: the inbox entry carries `concern_id`, URL,
  category, urgency, and timestamp — never the narrative body. The deep-link is
  the only path to the sensitive text. Keep it that way.
- **Every transition writes exactly one `CRITICAL`-sensitivity audit row.** This
  is a safeguarding audit invariant, not a logging preference.
- **DSL-only stages require `dsl_user_id`** in the transition args; the kernel
  raises a typed exception if it is missing. Do not make it optional.
- **The DSL notifier is best-effort by contract.** A failure to write the inbox
  entry must never block the concern submission itself — callers wrap it in
  try/except and log a warning. A concern being recorded always outranks the
  notification about it.
- The KCSIE banner previously fired without an `entry_id` and produced a false
  positive; entry identity is now required (`12b46183a`).
