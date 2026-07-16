# apps/sales

> The internal founder-led GTM pipeline: leads, stages, activity notes, and the
> first-100-schools dashboard. Operator-only, no external CRM.

**Tenancy:** SHARED (public schema; and unlike most shared apps, these rows carry no `school` FK at all — see below)
**Scale:** 3 models · 3 migrations · 3 test modules · ~1.1k LOC

## What this app owns

Sales is the platform operator's own CRM. It tracks prospective schools through
a seeded stage pipeline, records dated activity against each lead, and renders
two operator surfaces: a kanban pipeline board and the "first 100 schools"
readiness dashboard.

The decision that makes this app unlike every other app in the repo: **a `Lead`
has no `school` FK, deliberately.** A prospect is not a tenant. There is no
schema, no RLS policy, and no `request.school` to scope by, because the subject
of the row is a school that has not been onboarded yet. Isolation here is not
tenancy — it is the `require_control_plane_access` decorator on every view, and
the fact that the app is mounted only under `config/manager_urls.py` at
`sales/`. That single gate is the entire boundary. This is also, per the app's
own docstring, *not billing*: money lives in `finance` and `billing`.

The second thing to know is that lead metadata is **encoded in free text**. The
first-100 dashboard does not read columns for region, school type, package, or
pilot status — it regex-parses `[key:value]` tags out of `Lead.notes` via
`_parse_lead_tags`, and derives `readiness_score` arithmetically from
`stage.sort_order`. It is a deliberately cheap slice, not a modelled one.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `Lead` | `sales_lead` | A prospect or customer record for founder-led GTM (not billing). Carries `school_name` as plain text, contact details, a `PROTECT`ed stage FK, `decision_maker`, an internal `deal_owner`, and `next_follow_up` |
| `PipelineStage` | `sales_pipelinestage` | Normalized, seeded stage row (`key`, `label`, `sort_order`). Exists so display labels stay editable while code references the stable `key` |
| `ActivityLog` | `sales_activitylog` | A dated note against a lead, internal only. `Lead.notes` is the one-line summary; this is the running history |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| URL | `sales:pipeline_board` | `/sales/` — kanban by stage, with overdue / due-today / 7-day follow-up counters |
| URL | `sales:first_100_schools_dashboard` | `/sales/first-100/` — readiness rows + pilot evidence |
| URL | `sales:lead_create` | `/sales/leads/new/` |
| URL | `sales:lead_detail` | `/sales/leads/<pk>/` |
| URL | `sales:update_stage` | `/sales/leads/<pk>/stage/` — POST only |
| Module | `pilot_register` | `PILOT_REGISTER` — a frozen, in-code tuple of tracked pilots and their go/no-go gates |

Mounted on the manager host only. No Celery tasks, no management commands.

## Before you change this

- **`require_control_plane_access` is the only thing standing between a prospect
  list and the world.** There is no tenant scoping to fall back on, because there
  is no tenant. Every view in `views.py` carries it. A new view without it is a
  data leak, not a permissions bug.
- **`pilot_register.PILOT_REGISTER` is code, not data, and it is a source of
  truth.** Its docstring is explicit: when a pilot moves forward, update the row
  *here first* so the operator dashboard and downstream comms templates stay
  aligned, and removing a row removes the pilot from the platform record — do not
  do it silently. It is the internal preparedness checklist (what stage, what
  gate, which features/PSPs are blocking); real prospect data belongs in the
  `Lead` table and the finance side.
- **Editing `Lead.notes` can silently destroy lead metadata.** `region`, `type`,
  `package`, `pilot`, `blocker`, and `pain` on the first-100 dashboard come from
  `[key:value]` tags parsed out of that free-text field. A well-meaning cleanup of
  a note blanks those columns with no error. If this slice grows, promote the
  tags to real fields rather than adding more of them.
- **`readiness_score` is derived, not measured.** It is
  `min(100, (stage.sort_order + 1) * 12 + 15 if pilot_candidate)`. It reflects
  pipeline position and nothing about the prospect. Do not present it as an
  assessment, and note that it moves whenever someone reorders `sort_order`.
- **`PipelineStage` is seeded and `Lead.stage` is `on_delete=PROTECT`.** Deleting
  a stage with leads on it raises. Change the `label` freely — that is what the
  split is for — but treat `key` as an API, because view code branches on it
  (`pilot`, `demo_done`, `demo`).
- **The first-100 dashboard degrades instead of failing.** `load_raw_scorecard()`
  is wrapped and sets `scorecard_ok = False` on `OSError`/`ValueError`/`KeyError`,
  so a missing evidence file renders an honest empty state rather than a 500.
  Keep that shape.
- The board caps at 500 leads (200 when searching) and the dashboard at 100.
  Those are unpaginated slices; at real volume they truncate silently.
