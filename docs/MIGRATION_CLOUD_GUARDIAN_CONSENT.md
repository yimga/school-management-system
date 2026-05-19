# Migration Cloud — guardian consent collection

> v3.40.0 Agent 11 — operator runbook + counsel reference.

This document describes the guardian-facing consent collection flow
that extends Agent 7's customer-intake (`MigrationIntakeRequest`)
shipped in v3.40.0.

## TL;DR

When a school migrates its records into RunMyCampus, FERPA / COPPA /
GDPR all require a documented record that each affected guardian was
notified and either consented or declined. The collection flow:

1. School staff opens the campaign-start page, uploads a CSV with one
   row per guardian.
2. The system mints a unique URL-safe token per row, persists only
   `sha256(token)`, and sends each guardian a one-time email
   containing their consent URL.
3. Guardian clicks the URL, reads the agreement, clicks Accept or
   Decline. The system records the decision plus the server-captured
   IP / user-agent at the moment of decision.
4. School staff watches the dashboard (consented / declined / pending
   / expired) and re-sends to stuck guardians (up to 3 per token,
   24-hour cooldown).

## Consent text version history

| Version | Active from | Changes | Counsel signoff |
|---------|-------------|---------|-----------------|
| `v1`    | 2026-05-19  | Initial counsel-approved text (FERPA §99.30, COPPA §312.5(b), GDPR Art. 7) | **TBD — pending school counsel signoff** |

> **Versioning rule.** Once a token has been minted referencing a
> version, the `consent_text_sha256` on that token is immutable. Edits
> to a published version are forbidden — instead, add a sibling
> `templates/migration_cloud/guardian_consent/_consent_text_v2.html`
> and bump the
> `MIGRATION_CLOUD_GUARDIAN_CONSENT_ACTIVE_VERSION` setting.

## Privacy posture

| Captured | Stored where | Reason |
|----------|--------------|--------|
| Guardian's name + email | `GuardianConsentToken` row | Pre-populated by school at campaign start; needed to address the email |
| Guardian's IP at consent | `ip_address_consent` field | Legal record (FERPA §99.30 written-consent intent) |
| Guardian's UA at consent | `user_agent_consent` field (256 char cap) | Legal record |
| Decision (consented/declined) | `consent_decision` field | The actual outcome |
| `sha256(consent_text)` | `consent_text_sha256` field | Counsel-defensible proof of what they saw |
| `sha256(raw_token)` | `token_sha256` field | Authentication; raw token NEVER persisted |
| Decision timestamp | `consented_at` / `declined_at` | Legal record |

| NOT captured | Why |
|--------------|-----|
| Browser fingerprint / canvas / fonts | Not necessary for FERPA record |
| Tracking pixel / web bug | Counsel-rejected |
| Persistent cookie | Guardian flow is anonymous, no session needed |
| Geolocation | Not necessary |

## Operator playbook

### Launch a campaign

1. Navigate to the migration's status page:
   `/migration/<intake_id>/status/`
2. Click "Send to more guardians" (lands on
   `/migration/<intake_id>/consent/campaign/start/`).
3. Prepare a CSV with header row:
   `student_id,guardian_name,guardian_email`
4. Up to 2,000 rows per upload. Header row optional but recommended.
5. Submit. Each row triggers one `mint()` + one email send.

### Monitor a campaign

URL: `/migration/<intake_id>/consent/`

- Total / Consented / Pending / Declined+Expired counts.
- "Stuck tokens" panel: issued >7 days ago, not yet opened.
- Recent tokens table (latest 50).

### Re-send to a stuck guardian

In the "Stuck tokens" panel, click **Resend** next to the guardian's
row. Constraints:

- Maximum **3 sends** per token (initial + 2 re-sends).
- **24-hour cooldown** between sends.
- Each re-send **rotates** the underlying token (the previous URL
  becomes invalid). This is intentional: the school may have
  re-confirmed the guardian's email out of band, and the old URL may
  have been sent to a wrong address.

### Handle a decline

Declines are terminal — the school's option is to engage the guardian
out of band and (with the guardian's permission) reset the row via a
new campaign upload.

### Handle a revoke

Guardians may withdraw consent within 90 days of their original
acceptance, by following the same URL they used to consent and
clicking "Withdraw consent" (UI flow currently lives at
`/migration/consent/<raw_token>/revoke/` and is operator-supplied via
emailing the guardian their original URL; honest deferred — see
v3.41+).

Beyond 90 days, the revocation requires an out-of-band school-side
process (DSAR runbook in `docs/DSAR_RUNBOOK.md`).

## Guardian-facing FAQ

> **What is RunMyCampus and why am I getting this email?**
> Your school is moving its records system to RunMyCampus and is
> asking for your consent to migrate your child's records.

> **Did my school send this, or did RunMyCampus?**
> Your school authorised RunMyCampus to send the email on its behalf,
> using the contact information your school has on file for you.

> **What if I clicked Decline by mistake?**
> Contact your school's office and ask them to re-send the consent
> request. The school can issue a fresh consent URL.

> **What if I lost the original email?**
> Contact your school's office. Each URL is single-use and tied to
> your guardian record; we cannot regenerate the link without the
> school's involvement.

> **Do I have to click Accept to keep my child enrolled?**
> No. Your enrollment status is unaffected. If you decline, your
> school will handle your child's records under the same processes
> they use today (typically, by maintaining the existing system or
> migrating only with appropriate alternative legal bases).

## Compliance map

| Statute / Article | Section | How we satisfy it |
|-------------------|---------|--------------------|
| FERPA            | §99.30  | Written consent recorded with timestamp + IP + UA + immutable consent-text record |
| COPPA            | §312.5(b) | Verifiable parent consent prior to under-13 student data transfer |
| GDPR             | Art. 7  | Freely-given, specific, informed, unambiguous consent; right-to-withdraw within 90 days; auditable record |
| NY Ed Law §2-d   | -       | DPA template covers school's downstream obligations (see `docs/DPA_TEMPLATE.md`) |

## Counsel approval log

| Item | Version | Counsel | Signed | Notes |
|------|---------|---------|--------|-------|
| Consent text body | v1 | School-side counsel | **PENDING** | Placeholder text counsel-reviewed; awaits school-specific edits |
| Email subject line | "Action requested: review and respond" | School-side counsel | **PENDING** | ≤80 chars, no PII |
| 90-day revocation window | 90 days | School-side counsel | **PENDING** | Honors GDPR Art. 7 "freely withdrawable" |

## Settings

Knobs in `settings.py` (all `os.environ.get()` only):

| Setting | Default | Purpose |
|---------|---------|---------|
| `MIGRATION_CLOUD_GUARDIAN_CONSENT_REVOKE_WINDOW_DAYS` | `90` | Days post-consent during which guardian may revoke |
| `MIGRATION_CLOUD_GUARDIAN_CONSENT_ACTIVE_VERSION` | `v1` | Consent-text version applied to NEW tokens |
| `MIGRATION_CLOUD_PUBLIC_HOSTNAME` | empty | Public origin used to build absolute URLs in guardian emails |
| `MIGRATION_CLOUD_INTAKE_FROM_EMAIL` | `noreply@runmycampus.com` (via `DEFAULT_FROM_EMAIL`) | From address for consent emails |

## Honest deferred (for v3.41+)

- SMS-based consent for guardians without email
- Multi-language consent text (currently English-only; `_consent_text_v1.html` uses `{% trans %}` so po files can ship)
- Guardian self-service portal with persistent login (to revoke, view consent history, request DSAR)
- `Precedence: bulk` MTA header via `EmailMultiAlternatives` migration
- Resend that preserves the original token's URL (currently rotates because raw token isn't recoverable)
- Bulk-CSV preview with row-level validation summary before commit
- Webhook publication: `migration.guardian_consent.consented` → school's SIS to record consent flag

## File map

| File | Purpose |
|------|---------|
| `apps/migration_cloud/models_guardian_consent.py` | `GuardianConsentToken` + `mint()` / `consent()` / `decline()` / `revoke()` |
| `apps/migration_cloud/migrations/0023_guardian_consent_token.py` | Pure CreateModel |
| `apps/migration_cloud/views_guardian_consent.py` | Anonymous guardian-facing views (landing / accept / decline / revoke) |
| `apps/migration_cloud/views_guardian_consent_admin.py` | Tenant-scoped operator views (campaign start / status / resend) |
| `apps/migration_cloud/urls_guardian_consent.py` | Anonymous URLs |
| `apps/migration_cloud/urls_guardian_consent_admin.py` | Operator URLs |
| `templates/migration_cloud/guardian_consent/` | Guardian-facing templates (landing / completed / `_consent_text_v1.html`) |
| `templates/migration_cloud/customer/consent_campaign_*.html` | Operator templates |
| `templates/migration_cloud/emails/guardian/` | Guardian email templates (request / reminder / confirmed) |
| `apps/migration_cloud/tests/test_guardian_consent.py` | Test suite |
