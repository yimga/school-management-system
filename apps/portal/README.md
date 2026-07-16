# apps/portal

> The parent / student / teacher front door: guardian linking, the family
> experience, teacher pedagogical records, the AI gateway, and the help + KB
> stack.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 28 models · 45 migrations · 114 test modules · ~58k LOC

## What this app owns

Portal is where non-admin humans meet the platform. It owns the guardian
identity chain (invite → claim → `ParentStudentLink` → what that parent may
see), the parent and student dashboards, the teacher's pedagogical record-keeping
(lesson plans, Cahier de Texte with its supervisor visa workflow, in-service
training log), and the whole help surface — knowledge base, FAQs, forums,
guided journeys, and support deflection.

It is also the platform's **AI gateway**. The `ai_*` and `views_ai_*` modules
own provider resolution, the intent router, streaming, surface context, and the
drafting endpoints (announcements, parent messages, report-card comments). This
is deliberately centralized: other apps consume AI through portal rather than
each reaching for a provider.

The app is unusually large and layered because it accreted in waves, and the
layering is visible in the code. `portal_models.py` holds the **oldest** parent-
portal models and they are not written the way the rest of the platform is —
see the gotchas before you touch them. Newer slices (`models_kb`,
`models_forums`, document lifecycle) follow current conventions. Do not assume
one file's style is the app's style.

Because portal is a TENANT app, most models rely on the Postgres schema for
isolation and carry no `school` FK at all; a few later ones (`KBArticle`,
`HostedOfficeDocument`, `PortalFeatureItem`) do carry one.

## Key models

Portal declares 28 models. These are the ones that carry the core flows — the
list is deliberately not exhaustive.

| Model | Table | Purpose |
| --- | --- | --- |
| `ParentStudentLink` | `portal_parentstudentlink` | The guardian↔student edge and its access level. The gate for everything a parent sees. |
| `GuardianLinkInvitation` | `portal_guardianlinkinvitation` | Token invite for a guardian to link to a student (pending/accepted/declined/expired). |
| `PendingGuardianInvite` | `portal_pendingguardianinvite` | Lightweight claim token staff can issue to a guardian. |
| `PortalFeatureAccess` | `portal_portalfeatureaccess` | Per-parent feature switches (view_grades, view_fees, message_teacher, …). |
| `PortalAuditLog` | `portal_portalauditlog` | Parent portal activity log with IP + user agent. |
| `PortalSession` | `portal_portalsession` | Parent portal session tracking for security. |
| `PortalNotification` | `portal_portalnotification` | Parent-facing notifications. |
| `PortalPreferences` | `portal_portalpreferences` | Parent portal experience preferences. |
| `ParentMessage` | `portal_parentmessage` | Parent↔school messaging. |
| `AttendanceJustification` | `portal_attendancejustification` | Parent-submitted absence excuse / medical note. |
| `FormSignature` | `portal_formsignature` | Electronic signature on school forms (registration, consent, extra fees). |
| `LessonPlan` | `portal_lessonplan` | Teacher weekly lesson notes (PDF). A teacher sees only their own. |
| `LessonPlanAttachment` | `portal_lessonplanattachment` | Extra resource files on a lesson plan. |
| `CahierDeTexteEntry` | `portal_cahierdetexteentry` | Structured lesson diary; linked to syllabus, with a supervisor visa workflow. |
| `TeacherTrainingEntry` | `portal_teachertrainingentry` | In-service / professional development log. Teacher sees only their own. |
| `KBArticle` | `portal_kbarticle` | Knowledge-base how-to article. |
| `KBCategory` | `portal_kbcategory` | KB article categories. |
| `DocumentCategory` | `portal_documentcategory` | Configurable Document Library folder. |
| `HostedOfficeDocument` | `portal_hostedofficedocument` | Document opened via Collabora/LibreOffice Online (WOPI). |
| `PhotoUploadToken` | `portal_photouploadtoken` | Short-lived token for uploading a profile photo from a phone. |
| `Announcement` | `portal_announcement` | Date-windowed global banner ribbon. |
| `Event` | `portal_event` | School event calendar. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `ai_provider` / `ai_startup` / `ai_intent_router` / `ai_surface_context` | AI gateway internals |
| Module | `views_ai_draft`, `views_ai_stream`, `views_ai_gateway` | Drafting + streaming endpoints |
| Module | `one_record` | `build_student_one_record_data` — cross-module Student 360 aggregate; **no URL building** |
| Module | `student_results_visibility` | Per-tenant policy for grades on the student dashboard (`off` / `published` / `entered`) |
| Module | `parent_identity` | Simplified-home default + multi-school guardian switcher context |
| Module | `document_lifecycle` | DRAFT → REVIEW → APPROVED → ARCHIVED/RETRACTED transitions + search index |
| Module | `wedge_checks` | Live-checks registered into the wedge registry by import side effect |
| URL | `claim_invite`, `child_digital_id`, `badge_verify` | Guardian claim + child identity |
| URL | `cahier_list`, `cahier_visa`, `cahier_verify_list`, `cahier_request_revisions` | Cahier de Texte visa workflow |
| URL | `api_offline_enqueue`, `api_offline_apply_batch`, `api_offline_process` | Offline sync ingress |
| URL | `api_parent_data_rights_status` | Parent GDPR/DSAR status |
| URL | `ai_stream`, `ai_mode`, `ai_draft_*`, `ai_suggest_replies`, `ai_summarize_thread` | AI surfaces |
| Celery | `generate_ai_response_async`, `apply_support_ticket_ai_triage` | AI async work |
| Celery | `reindex_kb_help_embeddings_weekly`, `archive_stale_kb_articles_monthly` | KB hygiene |
| Celery | `build_code_support_index_weekly`, `purge_help_telemetry_monthly` | Support index / retention |
| Celery | `notify_forum_reply_task`, `help_north_star_weekly_email` | Notifications |
| Command | `seed_kb_articles`, `seed_faqs`, `import_docs_to_kb`, `generate_kb_odt` | KB seeding/export |
| Command | `migrate_kb_embeddings_to_pgvector`, `reindex_kb_help_embeddings` | Embedding store |
| Command | `cleanup_photo_upload_tokens`, `crawl_portal_role_urls`, `verify_onboarding_setup` | Hygiene / verification |

## Before you change this

- **The legacy models in `portal_models.py` use raw `IntegerField`, not
  ForeignKeys.** `ParentStudentLink.parent_id`, `.student_id`,
  `PortalFeatureAccess.parent_id`, `PortalAuditLog.parent_id`,
  `GuardianLinkInvitation.student_id` / `.created_by` are bare integers. There is
  **no referential integrity and no cascade** on these: deleting a user or
  student leaves orphan rows pointing at a dead id, and you cannot `select_related`
  across them. Anything reading these must tolerate a dangling id. Do not assume
  a Django relation exists because the field is named `*_id`.
- **`ParentStudentLink` is the parent authorization gate.** A parent's access to
  grades, fees, and attendance flows from this row and its `access_level`. Adding
  a parent-facing surface that queries by user without consulting the link (and
  `PortalFeatureAccess`) is how you leak another family's child.
- **Uploads are tenant-prefixed, but the prefix is derived, not guaranteed.**
  `_portal_upload_to` builds `tenants/<school_id>/portal/...` from the *related*
  object (`instance.teacher.school_id`, `instance.student.school_id`). If that
  relation is missing, `school_id` is `None` and the file falls back to a shared
  `tenant_uploads/portal/...` path — outside per-tenant media scoping. If you add
  an uploading model, wire its `school_id` resolver deliberately.
- **`ready()` must never block Django boot.** The AI startup probe does network
  I/O; it is wrapped in a bare `except` on purpose, skipped for management
  commands (`management_command_skips_ai_startup_probe`) and when
  `AI_GATEWAY_ENABLED` is false. The `wedge_checks` import is a *registration
  side effect* — it looks unused, it is not; removing it silently unregisters the
  wedge live-checks.
- **Teacher pedagogical records are own-only by RBAC.** `LessonPlan` and
  `TeacherTrainingEntry` restrict a teacher to their own rows. A "helpful"
  unfiltered queryset in an admin or export view breaks that contract.
- **`one_record.build_student_one_record_data` builds no URLs.** It aggregates DB
  sections only, and is consumed by Student 360, search story cards, and APIs.
  Keep URL construction in the callers or you couple the aggregate to one host's
  urlconf.
- **`student_results_visibility` falls back to `published` for unknown or blank
  values, not to `off`.** If you add a mode, add it to `_VALID_MODES` — otherwise
  it normalizes away to `published` and silently shows more than intended.
- **Portal reverses URLs across hosts.** This app is reachable from tenant and
  operator hosts; a hardcoded `{% url %}` to a surface that only exists on the
  other host raises `NoReverseMatch` and 500s the page. Pass an explicit
  `urlconf=` when reversing across hosts.
- The `ai_*` / `views_ai_*` and `help_*` / `kb_*` families are large and
  overlapping. Before adding a module, check whether the seam already exists —
  the help stack alone spans search, forums, journeys, deflection, governance,
  and telemetry.
