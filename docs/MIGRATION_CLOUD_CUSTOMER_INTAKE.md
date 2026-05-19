# Migration Cloud — customer-facing intake + status flow (v3.40.0)

The customer-side surface a school tenant uses to request, authorize, and
monitor a SIS migration into RunMyCampus. Distinct from the operator
(`/super/migration/`) and tenant-mirror (`/portal/configure/migration/`)
surfaces — this one is mounted at `/migration/` and uses the school's
own staff credentials (NOT `staff_member_required`).

## At a glance

| Property | Value |
|---|---|
| Mount point | `/migration/` |
| Namespace | `migration_intake_customer` |
| Auth model | `LoginRequiredMixin` + tenant-scoped queryset filter |
| Cross-tenant access | 404 (not 403, to prevent UUID enumeration) |
| Model | `apps.migration_cloud.models_intake.MigrationIntakeRequest` |
| Migration | `0022_migration_intake_request` |

## Walkthrough — a school's first migration

1. **Land on the list.** The school admin logs into their tenant
   portal and visits `/migration/`. Empty state shows a single primary
   action: "Start your first migration".

2. **Pick a vendor.** `/migration/start/` shows the 6 supported source
   SIS vendors (PowerSchool / Blackbaud / Veracross / Alma / FACTS /
   Skyward), a counsel-signoff acknowledgment checkbox, and a free-text
   field for any notes the RunMyCampus team should see.

3. **Sign the agreement.** On submit, the school is redirected to
   `/migration/<id>/sign-maa/`. The full text of the active Migration
   Authorization Agreement (MAA v1.0 as of v3.40.0 — v2.0 is still
   pending counsel signoff) is rendered verbatim. The school admin
   enters their name, role, ticks the "I have authority" box, and
   submits.

4. **Monitor progress.** Post-sign redirect to `/migration/<id>/status/`
   shows a 7-stage progress bar:

   ```
   Intake submitted -> MAA pending -> MAA signed
       -> Extracting -> Validating
       -> Awaiting your approval -> Live
   ```

   On environments with `MIGRATION_CLOUD_SSE_TRANSPORT = "asgi-daphne"`
   the page subscribes to a Server-Sent Events stream and updates in
   real time. Elsewhere it falls back to a 30-second `<meta refresh>`.

5. **Receive emails.** Each state transition triggers a transactional
   email to the requesting user (subject to the user's `receives_email`
   preference): "We received your intake", "Agreement signed",
   "Extraction complete", "Migration complete", "Needs attention".

6. **Abandon if needed.** Before extraction begins (i.e. while in
   `intake-draft` or `maa-pending-counsel`), the school can soft-cancel
   the request via `/migration/<id>/abandon/`. A signed MAA is retained
   for audit; only the request itself is marked `abandoned`.

## State machine

ASCII diagram of the 12 states + 17 transitions:

```
intake-draft
   |
   v
maa-pending-counsel --------+
   |                        |
   v                        v
maa-signed              abandoned (terminal)
   |
   v
extraction-in-progress -----+
   |                        |
   v                        v
extraction-complete       failed (terminal)
   |
   v
validation-in-progress
   |
   v
validation-complete
   |
   v
promotion-pending-approval
   |
   v
promotion-in-progress
   |
   v
complete (terminal)
```

`abandoned` may only be entered from `intake-draft` or
`maa-pending-counsel`. `failed` may be entered from any non-terminal
state. The state machine refuses transitions outside this graph
(raises `MigrationIntakeStateError`).

### pct_complete anchors

| State | pct_complete |
|---|---|
| intake-draft | 0 |
| maa-pending-counsel | 10 |
| maa-signed | 15 |
| extraction-in-progress | 30 |
| extraction-complete | 45 |
| validation-in-progress | 60 |
| validation-complete | 75 |
| promotion-pending-approval | 85 |
| promotion-in-progress | 90 |
| complete | 100 |
| failed | 50 (frozen midpoint) |
| abandoned | 0 |

## Email template inventory

All under `templates/migration_cloud/emails/customer/` — both `.txt`
(plain) and `.html` (rich) variants. Subjects are <=80 chars and
contain no PII.

| Trigger state | Template basename | Subject |
|---|---|---|
| `maa-pending-counsel` | `intake_received` | "We received your migration request" |
| `maa-signed` | `intake_maa_signed` | "Migration agreement signed - extraction begins shortly" |
| `extraction-complete` | `intake_extraction_complete` | "Migration extraction complete - validation underway" |
| `complete` | `intake_complete` | "Your migration is complete" |
| `failed` | `intake_failed` | "Your migration needs attention" |

The `intake_failed` template surfaces `notes_from_runmycampus_team`
in the body so the school knows what to do next.

## Privacy posture

What surfaces in the customer flow:

* **Status page** — vendor label, current state, progress %, the last
  10 audit events for this intake (event_type + UTC timestamp only),
  operator-side notes (`notes_from_runmycampus_team`), the school's
  own notes (`notes_for_runmycampus_team`).
* **Sign-MAA page** — full MAA body text (verbatim, version-pinned),
  default holder name pre-filled from the requesting user's profile,
  role + holder-name input.
* **Emails** — school name, vendor label, intake UUID, status URL.
  No raw email addresses, signature text, counsel PDF URLs, or
  per-record data ever surface.

What is redacted everywhere:

* `signature_text` — verbatim MAA body is captured server-side at
  sign time; the post-sign view never re-renders it.
* `counsel_signoff_pdf_url` — never logged, never echoed to email or
  template context.
* MAA body — emails reference the intake reference number only.
* Raw tenant slug — audit log stores `sha256(slug)[:12]` only.

## Configuration

Optional Django settings consulted (all have safe defaults):

```python
# config/settings.py
MIGRATION_CLOUD_INTAKE_FROM_EMAIL = "migrations@runmycampus.com"
# Falls back to DEFAULT_FROM_EMAIL.

MIGRATION_CLOUD_SSE_TRANSPORT = "asgi-daphne"
# Customer status page uses SSE when this is "asgi-daphne".
# WSGI-fallback environments use <meta refresh>.
```

## Files

* `apps/migration_cloud/models_intake.py` — model + state machine.
* `apps/migration_cloud/views_customer.py` — 6 customer-facing views.
* `apps/migration_cloud/signals_intake.py` — state-change email dispatch.
* `apps/migration_cloud/urls_customer.py` — URL grammar.
* `apps/migration_cloud/migrations/0022_migration_intake_request.py` — DB migration.
* `templates/migration_cloud/customer/*.html` — 5 page templates + 1 partial.
* `templates/migration_cloud/emails/customer/*.{txt,html}` — 5 email pairs.
* `apps/migration_cloud/tests/test_customer_intake.py` — test suite.

## Honest deferred for v3.41+

* Counsel signoff PDF storage moved to S3 (currently a TextField URL —
  fine for MVP, not great for audit retention).
* Guardian consent collection UI — fields are persisted (collected /
  required counts) but no UI surface yet.
* Browser-extension-driven status updates — the companion extension
  could push extraction progress directly to the intake's SSE feed
  instead of polling.
* Multi-vendor parallel migrations — current model assumes one
  vendor per intake; some schools migrate from two sources
  simultaneously.
