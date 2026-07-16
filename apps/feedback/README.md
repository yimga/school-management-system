# apps/feedback

> Voice of Customer: feedback intake from every role, the feature-request →
> roadmap → release-note loop, the help center's search telemetry, and the
> public status page.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 14 models · 9 migrations · 20 test modules · ~4.8k LOC

## What this app owns

Feedback owns the whole round trip between a user hitting friction and the
platform answering. A teacher, parent, student, or admin files a
`FeedbackSubmission`; it is triaged (`FeedbackTriageEvent`); it may become a
`FeatureRequest` that others vote on (`FeedbackVote`); an operator promotes it
to a `RoadmapItem`; shipping it produces a `ReleaseNote` — and the submitters
get told. That last hop is the point. The app also owns the help center's
telemetry side (zero-result searches, KB deflection, support-AI ratings) and
the public `/status/` page.

The defining design decision is **privacy is enforced at the service layer, not
at the form**. `submit_feedback` calls `_student_privacy_defaults(role,
privacy_level)`, which *overrides* what the caller asked for: a student's
submission is forced to `SCHOOL_PRIVATE` with `moderation_required=True` even
when the request explicitly asks for `PUBLIC_CANDIDATE`. A child cannot publish
to a public board by accident or by crafting a request, because the decision
does not live anywhere the request can reach. `visible_feedback_for_user` is the
matching read-side gate — parents and students see only their own.

The second decision is **telemetry without content**. Help-center analytics is
fingerprinted, not recorded: `HelpSearchQueryLog` keeps zero-result and
deflection signal, `SupportDeflectionEvent` is explicitly aggregate with no raw
query text, and `SupportAISessionRating` / `SupportAIInteractionReview` are
fingerprint-only with no PII payload. The platform learns which help content is
missing without accumulating a log of what individual users typed while
confused.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `FeedbackSubmission` | `feedback_feedbacksubmission` | The core intake row — carries role, privacy level, moderation flag, source context |
| `FeedbackTriageEvent` | `feedback_feedbacktriageevent` | Triage state transitions on a submission |
| `FeedbackComment` | `feedback_feedbackcomment` | Discussion on a submission |
| `FeedbackAttachment` | `feedback_feedbackattachment` | File attached to a submission |
| `FeatureRequest` | `feedback_featurerequest` | A promoted ask others can vote on (SUBMITTED/TRIAGING/UNDER_REVIEW/NEEDS_MORE_INFO/…) |
| `FeedbackVote` | `feedback_feedbackvote` | One vote on a feature request |
| `RoadmapItem` | `feedback_roadmapitem` | Operator-curated roadmap entry |
| `ReleaseNote` | `feedback_releasenote` | Shipped-change note; its state change is what notifies submitters |
| `SurveyResponse` | `feedback_surveyresponse` | Survey/pulse response |
| `HelpSearchQueryLog` | `feedback_helpsearchquerylog` | Zero-result + deflection analytics (fingerprinted queries) |
| `HelpContentGapTask` | `feedback_helpcontentgaptask` | Operator backlog for repeated zero-result help searches |
| `SupportDeflectionEvent` | `feedback_supportdeflectionevent` | Aggregate KB-deflection telemetry — no raw query text |
| `SupportAISessionRating` | `feedback_supportaisessionrating` | Thumbs/stars after a support SSE session (fingerprint-only) |
| `SupportAIInteractionReview` | `feedback_supportaiinteractionreview` | Human-in-the-loop queue for thumbs-down / failed support AI (no PII payload) |

All 14 declared models are listed.

## Surfaces

This app is routed on **three hosts from three separate url modules** — see the
gotchas below.

| Kind | Name | Notes |
| --- | --- | --- |
| `tenant_urls.py` | `feedback:` on `config.tenant_urls` | `school_feedback`, `teacher_feedback`, `parent_feedback`, `student_feedback`, `school_contact_us`, `school_feature_center`, `school_roadmap`, `public_status`, `public_status_json` |
| `urls.py` | `feedback:` on `config.urls` + `config.manager_urls` | `help_center`, `contact_us`, `feature_center`, `product_roadmap`, `release_notes_public`, `pulse`, `vote_feature`, `contextual` |
| `operator_urls.py` | `feedback_operator:` at `super/feedback/` on `config.urls` | `voice_of_customer`, `product_feedback`, `product_roadmap`, `operator_feedback_action`, `add_to_roadmap` |
| Service | `services.py` | `submit_feedback` / `visible_feedback_for_user` — the privacy chokepoints |
| Module | `signals.py` | `post_save`/`pre_save` handlers emitting transactional email on ReleaseNote / FeedbackSubmission state changes |
| Module | `db_readiness.py` | Table-existence guard for unmigrated DBs (see gotchas) |
| Context processor | `support_links` | Host-aware help / feature / contact URLs, wired globally in settings |
| Management command | `migrate_product_feedback_legacy`, `purge_help_telemetry` | Legacy migration; telemetry retention purge |

No Celery tasks.

## Before you change this

- **Never bypass `submit_feedback` to create a `FeedbackSubmission`.** The
  student-privacy override lives in the service, so a direct
  `FeedbackSubmission.objects.create(...)` silently skips it and can publish a
  child's submission to a public board. Same for reads: use
  `visible_feedback_for_user`, not a raw queryset.
- **`public_status` and `public_status_json` are deliberately anonymous** and
  carry `# rbac-allow:` markers saying so. They are consumed by external
  monitors. Keep them PII-free — that is the condition of them being public, not
  an oversight to "secure".
- **This app is a TENANT app that is also queried from the public schema.** The
  `db_readiness` querysets carry `# tenant-isolation-allow:
  manager-global-open-count-public-schema-help-center` markers because the
  manager host counts open feature requests globally. If you add a query here,
  be explicit about which side of that line it is on — the app's tenancy does not
  by itself tell you.
- **`feedback_schema_ready()` is `@lru_cache(maxsize=1)` and process-global.**
  It answers "do the feedback tables exist?" by introspecting
  `connection.introspection.table_names()` — but under django-tenants the
  connection's schema varies per request, and a single cached slot cannot
  represent more than one schema. `clear_feedback_schema_ready_cache()` exists
  for that reason. Treat this as a coarse "has this deployment been migrated at
  all" guard, not a per-tenant readiness check, and do not extend it into one
  without replacing the caching.
- **The whole readiness layer exists because production DBs can be unmigrated.**
  `run_feedback_query(callable, default=...)` returns the default rather than
  500ing, and the queryset factories return `.none()`. That is why the help
  center degrades to empty instead of erroring on a fresh or partly-migrated
  deployment.
- **Three url modules mean `reverse()` is host-sensitive.** The `feedback:`
  namespace exists on the tenant host (from `tenant_urls.py`) *and* on the
  default/manager hosts (from `urls.py`) with **different names registered in
  each**. A name like `school_feedback` resolves only on the tenant host;
  `help_center` only on the others. This is exactly what
  `verify_cross_host_template_reverse` guards — resolve host-varying targets in
  the view or use the `support_links` context processor rather than hardcoding
  `{% url %}` in a shared template.
- `db_readiness.py` contains leftover agent-debug instrumentation (`# region
  agent log` blocks writing JSON lines to `debug-22cfee.log`). It is residue
  from a debugging session, not a contract — it swallows `OSError` so it cannot
  break anything, but do not build on it, and removing it is a cleanup, not a
  behavior change.
