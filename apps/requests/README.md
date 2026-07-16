# apps/requests

> One inbox for every "may I…?" in the platform: access requests, approvals, the
> decision that resolves them, and the audit trail behind it.

**Tenancy:** SHARED (public schema; `AccessRequest.school` is a nullable FK and views scope by `request.school` when a tenant host is bound)
**Scale:** 3 models · 5 migrations · 2 test modules · ~1.6k LOC

## What this app owns

Requests is the unified approval surface. Nine request types
(`FINANCE_ACCESS`, `MODULE_ACCESS`, `GRADE_APPROVAL`, `LEAVE_APPROVAL`,
`REPORT_REQUEST`, `PORTAL_FEATURE_ACCESS`, `DOCUMENT_REQUEST`, `REFUND_REQUEST`,
`OTHER`) land in one queue with one reference format, one status vocabulary, and
one audit chain, so a reviewer does not need to know which app the underlying
work belongs to.

The architectural decision that explains everything here is that **`AccessRequest`
is a router, not the source of truth.** For request types that wrap another app's
model, the real row lives elsewhere — `evals.GradeApprovalRequest`,
`people.TeacherLeaveRequest`, `finance.ReportRequest` — and `AccessRequest` is a
mirror of it, attached by a `GenericForeignKey` and kept in sync by `post_save`
signals in `signals.py`. Approving in this app does not just flip a status here:
`services.apply_request_decision` is the single chokepoint that writes the actual
grant into the owning app (setting `StudentGuardian.can_view_finance`, granting a
`module.<name>.<action>` Permission, moving the leave/grade/report row).

That means the *effect* of an approval is defined by an `_apply_*` handler, and a
type with no handler produces a decision and a notification but changes no access.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `AccessRequest` | `requests_accessrequest` | The request itself: type, status, `REQ-YYYYMMDD-XXXXXXXX` reference, requester/assignee, `details` JSON payload, and a `GenericForeignKey` to the row it mirrors (if any) |
| `RequestDecision` | `requests_requestdecision` | An approve / deny / clarify decision with reason and decider. Append-only history — a request can carry several |
| `RequestAudit` | `requests_requestaudit` | Every action taken on a request, written via `AccessRequest.add_audit()` |

`RequestDecision` and `RequestAudit` carry no `school` FK; they are scoped
transitively through `request.school`.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| URL | `requests:dashboard` | `/requests/` — filterable queue with type/status counts |
| URL | `requests:detail` | `/requests/<uuid>/` — review + decide |
| URL | `requests:module_access` | `/requests/module-access/` — self-service module-access request |
| Celery task | `requests.remind_pending_assignees` | Nudges assignees with pending work; opt-in per tenant |
| Module | `services` | `create_access_request`, `sync_request_for_target`, `apply_request_decision`, `notify_requester` |
| Module | `signals` | `post_save` mirrors for `GradeApprovalRequest`, `TeacherLeaveRequest`, `ReportRequest` |

Mounted on both the tenant host (`config/tenant_urls.py`) and the default urlconf
(`config/urls.py`) at `requests/`.

## Before you change this

- **`apply_request_decision` is the only place a decision becomes real, and it is
  `@transaction.atomic` for that reason.** The status flip, the `RequestDecision`
  row, the audit entry, the side effect in the owning app, and the requester
  notification either all land or none do. Do not add a code path that sets
  `AccessRequest.status` directly — it would report an approval that granted
  nothing.
- **Not every request type has an `_apply_*` handler.** Only `FINANCE_ACCESS`,
  `MODULE_ACCESS`, `GRADE_APPROVAL`, `LEAVE_APPROVAL`, and `REPORT_REQUEST` have
  one. `PORTAL_FEATURE_ACCESS`, `DOCUMENT_REQUEST`, `REFUND_REQUEST`, and `OTHER`
  are recorded and audited, but approving them grants nothing automatically —
  a human does the work off-platform. If you add a type, decide explicitly which
  of the two it is.
- **The signals are one-directional mirrors and they will re-fire.**
  `sync_request_for_target` is a `get_or_create` keyed on
  `(request_type, target_content_type, target_object_id)`, so it must stay
  idempotent — `_apply_grade_approval` saves the target, which fires the
  `post_save` mirror straight back into this app. Make it non-idempotent and you
  get a loop.
- **`MODULE_ACCESS` approval mints Permission rows.** `_apply_module_access`
  builds the code `module.<module>.<action>` from the requester's own `details`
  JSON and `get_or_create`s the `Permission`. `action` is clamped to
  `{read, write}` and a blank module is a no-op — those two guards are the whole
  defense against a self-service request minting an arbitrary permission code.
  Treat `details` as untrusted input.
- **`school` is nullable and the dashboard scopes conditionally.** On a tenant
  host `requests_dashboard` filters by `request.school`; with no bound school it
  lists unscoped (an operator view). The `tenant-isolation-allow` comments in
  `views.py` and `tasks.py` mark reviewed exceptions, not oversights — check the
  next line before you assume a leak.
- **`schema_name` is denormalized at write time** by `_resolve_scope`, falling
  back through `schema_name` → `subdomain` → `slug`. It is a snapshot; renaming a
  school does not backfill it.
- **The reminder task is opt-in and defaults to off.** It reads
  `requests_reminder_interval_hours` per school via `get_effective_config`; `0`
  means disabled, and that is the default. It runs per-tenant through
  `_run_with_tenant_context` over `get_active_school_ids()`, and logs every run to
  `AutomationExecutionLog` — a silent run is a bug.
- `notify_requester` writes **two** things: a `finance.Notification` and a
  `communication.Message` (with a resolved locale target). Both are expected
  downstream; dropping one degrades the parent/staff inbox.
