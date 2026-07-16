# apps/communication

> Every message the school sends a human — in-app, email, SMS, WhatsApp, push —
> and the consent / delivery evidence that proves what happened.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 30 models · 32 migrations · 32 test modules · ~20k LOC

## What this app owns

Communication owns the outbound edge of the platform. Internal messaging
(direct threads, group threads, mentions, blocks), school announcements with an
approval workflow, the parent/teacher feed, and the transports that carry all of
it to a phone or an inbox.

The defining design decision is that **no caller picks a channel.** Before
Phase 4 every feature hardcoded its own transport ("send an SMS for a fee
reminder"), and the granular `NotificationPreference` model was consulted
nowhere. `dispatch.py` inverted that: a caller raises an *event*, and the router
resolves it:

```
event_key --EVENT_CATEGORY_MAP--> Category
Category  --DEFAULT_CHANNELS_BY_CATEGORY--> [Channel, ...]
pref.is_muted(category)         -> skip the whole event
pref.allows(category, channel)  -> skip that one channel
per-channel transport gate      -> consent / guardian flags / quiet hours
```

Those two maps are the single source of truth, keyed off the model's
`TextChoices` rather than bare string literals. `notification_service` is the
one place that talks to a vendor; no other app imports Twilio, `send_mail`, or
`EmailMessage` for notifications. `announcement_delivery` and the WhatsApp
Parent OS both route back through `dispatch_event` rather than re-deciding
channels for themselves.

The second decision that shapes the schema: **recipients are stored hashed.**
`ConsentEvent`, `MessageDeliveryReceipt`, and `SmsSendLog` all persist
`sha256(identifier.lower())[:12]` and never the raw phone number or token.

## Key models

The 14 that carry the app (of 30 declared — the rest are attachments, read
state, and virtual-classroom rows).

| Model | Table | Purpose |
| --- | --- | --- |
| `Message` | `communication_message` | Internal user-to-user message |
| `MessageThread` | `communication_messagethread` | Group thread for a class / department / role |
| `ThreadMessage` | `communication_threadmessage` | Post in a group thread; audit-friendly soft delete/edit |
| `DirectConversation` | `communication_directconversation` | Staff–parent conversation. Only staff can open it; staff closing it ends the parent's ability to reply |
| `MessageBlock` | `communication_messageblock` | One user blocking another from direct messages. Group threads are deliberately unaffected |
| `Announcement` | `communication_announcement` | School-scoped, audience-targeted announcement with an optional PENDING_APPROVAL step |
| `AnnouncementAuditLog` | `communication_announcementauditlog` | Who created / updated / approved an announcement |
| `ClassAnnouncement` | `communication_classannouncement` | Class or department scoped notice with RBAC-aware visibility |
| `NotificationPreference` | `communication_notificationpreference` | Per-user per-category mute, channel overrides, quiet hours, digest cadence — enforced at send time by `dispatch` |
| `ConsentEvent` | `communication_consent_event` | Append-only cross-channel consent decision (a texted STOP, a preference toggle). CAN-SPAM / CASL / GDPR / TCPA evidence |
| `MessageDeliveryReceipt` | `communication_message_delivery_receipt` | Latest provider status per outbound message per channel, upserted by webhook on the provider's own message id |
| `SmsSendLog` | `communication_smssendlog` | Provider-level SMS idempotency log, gated on **before** the provider call so a retry cannot double-send a real SMS |
| `OutboundMessageQueue` | `communication_outboundmessagequeue` | Queue for WhatsApp/SMS when a provider is configured |
| `CommunicationTemplate` | `communication_communicationtemplate` | Per-tenant notification template override over the code catalog |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `dispatch` | Event → preference → channel router. The single fan-out path |
| Module | `notification_service` | The only vendor-facing send path (email / SMS / push / WhatsApp) |
| Module | `channel_adapter` | Adapter registry + selection (reliability × cost, tie-broken by registry order) |
| Module | `consent` | Write/query the consent log; never raises into a send path |
| Module | `template_catalog` | Declarative code-level template inventory; read-only at runtime |
| Module | `secret_config` | Fernet-wraps secret-named keys in `ServiceIntegration.config` at the storage boundary |
| Module | `email_signing` | DKIM posture detection + the production deploy gate |
| Module | `circuit_breaker` | Opens after N provider failures in a window; caller falls back or fails fast |
| Module | `whatsapp_parent_os` | Pure inbound routing kernel — performs no network I/O |
| Module | `tenant_deliverability` | Per-tenant bounce / complaint / delivered rates and health bands |
| Celery | `process_outbound_message_queue` | Drains `OutboundMessageQueue` |
| Celery | `kudos_perfect_attendance_3d_task` | Mints `AchievementEvent` rows for the feed |
| Command | `send_parent_digests` | Digest cadence fan-out |
| Command | `redrive_outbound_messages` | Re-queue stuck outbound rows |
| Command | `encrypt_channel_secrets` | Backfill for rows written before `secret_config` landed |
| Command | `check_email_signing` | Reports DKIM posture from the CLI |
| Command | `purge_thread_message_retention` | Retention sweep over thread messages |
| Command | `sync_department_threads` | Reconcile department thread membership |
| Command | `verify_whatsapp_parent_os_resolver` | Resolver health check |
| Webhook | `whatsapp_webhook`, `sms_inbound_webhook`, `sms_status_webhook` | Inbound provider callbacks |

## Before you change this

- **Do not hardcode a channel at a call site.** Raise an event through
  `dispatch.dispatch_event` and let `EVENT_CATEGORY_MAP` /
  `DEFAULT_CHANNELS_BY_CATEGORY` decide. Adding a channel string at a transport
  call site re-creates the exact bug this module was built to remove.
- **Recipient PII must stay hashed.** `ConsentEvent`, `MessageDeliveryReceipt`,
  and `SmsSendLog` store a 12-hex sha256 prefix only. The provider message id is
  an opaque vendor handle and is not PII. Do not add a raw-phone column for
  convenience.
- **`is_channel_suppressed` fails OPEN on a read error, deliberately.** A
  transient DB blip returns False so legitimate mail still goes out; an explicit
  STOP is durable in the log and re-evaluated on the next send. Note the module
  docstring says "fail-CLOSED" — the function docstring and the code are the
  accurate account. Its query is also deliberately not school-filtered (it
  carries a `tenant-isolation-allow` marker): a withdrawal binds to the hashed
  identifier, not to one school.
- **`communication.Announcement` is not a duplicate of `portal.Announcement`.**
  The portal one is a simple date-windowed banner with no school FK, rendered by
  a context processor. This one is school-scoped, audience-targeted, and
  approvable. The model docstring says plainly: do not merge them.
- **`AppConfig.ready()` raises on purpose.** When `EMAIL_SIGNING_REQUIRED=True`
  and no DKIM-signing backend is wired, deploy fails loudly rather than sending
  forgeable mail — a spoofed `From: principal@school.edu` is a tuition-fraud
  vector. Every other exception in `ready()` is downgraded to a warning so app
  loading never breaks; keep that asymmetry.
- **`deliver_announcement` is idempotent via `delivered_at`.** A re-fired
  publish or a retried scheduled run must not double-deliver. Batches are
  capped; keep them capped.
- **`whatsapp_parent_os` does no network I/O and must not start.** It is a pure
  kernel; the webhook view sends whatever `OutboundIntent` it returns. AI calls
  route through `services.ai_helpers`, never `services.ai_gateway` directly.
- **`secret_config` encryption is idempotent and backward-compatible by
  design.** Already-encrypted values are left alone and pre-existing plaintext
  passes through until the next save or the backfill command. Do not "simplify"
  it into a hard cutover — a half-migrated table is the expected state.
