# apps/assist_dock

> The right-edge floating assistant rail — chips, badges, quick actions, AI
> actions, presence, and the dual-control operator impersonation flow.

**Tenancy:** SHARED (public schema; prefs hang off `User`, which is public too, so they survive a tenant switch)
**Scale:** 8 models · 4 migrations · 20 test modules · ~9.8k LOC

## What this app owns

Assist Dock is the persistent assistant rail every shell renders. It owns the chip
registry, the live badge resolvers, page-aware quick actions, the AI action
vocabulary, per-user dock preferences, cross-worker presence and cursors, the share
short-link, and — the heaviest thing here — the operator impersonation flow with its
dual-control grant and append-only audit trail.

The defining decision is that **the registry is code, not data**. Every chip is an
`AssistDockSlot` registered by calling `register_slot(...)` from any app's
`AppConfig.ready` hook. The registry is process-local, idempotent (re-registering an
id overwrites), and adds **no DB tables and no migrations**. That inverts the usual
dependency: this app never imports the apps that contribute chips, so a new chip is
a one-line entry in the owning app rather than an edit here. The 4 migrations this
app does ship are for the things that genuinely need durability — prefs, presence,
insights, short links, and the impersonation records.

The second decision is defensiveness. The context processor runs on **every page
request** in every shell, so any failure logs at debug and returns an empty payload —
a misconfigured slot must never break page rendering. Badge resolvers carry the same
contract: fast (under ~50 ms), tolerant of missing tenant context, return `None` to
suppress.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `UserAssistDockPrefs` | `assist_dock_userassistdockprefs` | One row per user, JSON payload: pinned order, hidden slots, dock side (RTL-friendly), density, halo mute, `locale_preference` |
| `ImpersonationGrant` | `assist_dock_impersonationgrant` | One operator-issued grant authorizing a second operator to impersonate; single-use, time-limited |
| `ImpersonationSession` | `assist_dock_impersonationsession` | A concrete session created by consuming a grant |
| `ImpersonationAuditEvent` | `assist_dock_impersonationauditevent` | **Append-only** log of every impersonation state transition; never deleted, FERPA-retention-aligned |
| `PresencePing` | `assist_dock_presenceping` | Durable, cross-worker presence row mirroring the in-memory hot path |
| `InsightRecord` | `assist_dock_insightrecord` | Durable, cross-worker copilot insight |
| `AssistDockShortLink` | `assist_dock_assistdockshortlink` | 24h short-link minted by the share chip |
| `AssistDockShortLinkRecipient` | `assist_dock_assistdockshortlinkrecipient` | One row per recipient the operator emailed |

The impersonation models live in `impersonation.py` (next to the FSM they belong
to), not `models.py`.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `registry` | The chip SOT — `register_slot(...)`, `get_slots_for(surface=, role=)`; `"*"` means any |
| Module | `context_processors` | Exposes `assist_dock` to every template; fails soft to an empty payload |
| Module | `badges` / `default_badges` | Pluggable badge resolvers (6 defaults) |
| Module | `quick_actions` / `ai_actions` | Page-bound shortcuts; AI actions route through `services.ai_helpers` (never `services.ai_gateway` — CI-fenced) |
| Module | `impersonation` | Dual-control grant FSM: `requested → approved → consumed` (+ `expired` / `revoked`) |
| Module | `middleware` | `AssistDockLocaleMiddleware` — applies the user's `locale_preference` after Django's `LocaleMiddleware`; never raises |
| Module | `presence` / `cursors` | In-memory + Lock-protected, TTL-swept, mirrored to rows |
| Module | `short_links` | 16-byte urlsafe tokens, 24h default TTL, 7-day hard cap |
| URLs | `impersonation_request`, `impersonation_approve`, `impersonation_start`, `impersonation_stop`, `impersonation_revoke`, `impersonate`, `context`, `context_stream`, `insights`, `presence`, `share_mint`, `share_resolve`, `registry_introspect`, `prefs`, `theme`, `translate`, … (30) | |

No Celery tasks and no management commands.

## Before you change this

- **Impersonation is dual-control by design and must stay that way.** Only a
  SUPERADMIN can request *or* approve; `approver != grantor` is the whole point of
  the control. The grant is single-use, scoped to one target user, time-limited
  (30 min default from approval, 4 h absolute ceiling), and consumed at session start.
  Every transition writes an `ImpersonationAuditEvent`.
- **Two impersonation residuals are known and intentional — do not read the flow as
  more locked-down than it is.** (1) *No RBAC restore*: the impersonator inherits the
  target's full permissions for the session. A view that must refuse impersonation has
  to check `request.session.get('_impersonator_id') is None` itself — password change
  is the canonical example. (2) *No action-level audit*: only session start/stop is
  logged; mid-session actions log under the impersonated user's pk via the normal
  request log. Per-click receipts need a new model, not a tweak.
- **The impersonator's real user is NOT swapped out for logging.** `request.user`
  remains the operator, so the audit actor is already correct; `logging_context` in
  `apps/observability` flags the "during impersonation of school X" fact separately.
- **The context processor must never raise.** It runs on every request in every
  shell. Same for the locale middleware — any failure logs at DEBUG and lets Django's
  original locale stand.
- **Presence, cursors, and insights are per-process and in-memory**, mirrored to rows
  so other workers can merge. Cursors are **not** true WebSocket co-browse — clients
  heartbeat at ~4 Hz over POST and read peers via the existing SSE `context_stream`.
  The honest residual (real WebSocket/WebRTC, 60fps, voice/screen) is disclosed in
  the impersonate landing copy. Keep that copy honest if you change the transport.
- **AI action prompts are rendered with plain `str.format`** — no eval, no template
  engine — so a hostile `page_excerpt` cannot escape the prompt boundary. Do not swap
  in a real template engine here.
- Adding a chip means calling `register_slot(...)` from **your** app's
  `AppConfig.ready`, not editing this app. Super-only chips declare
  `roles=frozenset({"SUPERADMIN"})`.
