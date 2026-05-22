# Email deliverability guide (v3.58.x Wave 9 Agent M)

This doc is the SOT for getting RunMyCampus email out of the spam folder
and landing reliably in the recipient's inbox. It's written for tenant
operators (school IT) and platform operators (control-plane staff)
who don't necessarily live in DNS panels every day.

Cross-links:

- Operator dashboard: `/super/email/health/`
- Operator config form: `/super/email/configure/`
- Shared-secret rotation guidance: [`docs/SECURITY_KEYS.md`](SECURITY_KEYS.md)
- Source code: `apps/schoolops/email_delivery.py`,
  `apps/schoolops/views_email_webhook.py`,
  `apps/schoolops/views_email_health.py`.

---

## 1. The three pillars: SPF, DKIM, DMARC

Modern receiving servers (Gmail, Outlook, Yahoo, Apple Mail) trust an
incoming message far more when all three of the following alignments
pass. Skip any one and your verification + password-reset emails will
silently land in spam.

### 1.1 SPF (Sender Policy Framework)

SPF is a DNS TXT record on your sending domain that lists the IPs / hosts
ALLOWED to send mail "From:" that domain. If a message arrives from an
IP NOT in the list, the receiver lowers the trust score.

**Where it lives:** TXT record on the apex of your sending domain
(e.g. `yourschool.edu`, NOT `mail.yourschool.edu`).

**Generic shape:**

```
yourschool.edu.    IN    TXT    "v=spf1 include:_spf.<provider>.com ~all"
```

The `~all` at the end says "anything not in this list — soft-fail".
Use `-all` (hard-fail) once you're confident the include chain is
complete.

### 1.2 DKIM (DomainKeys Identified Mail)

DKIM is a cryptographic signature on every outbound message. The
sending server signs with a private key; the public key lives in a
DNS TXT record at a provider-specific selector. The receiver fetches
the public key and verifies the signature.

**Where it lives:** TXT record at `<selector>._domainkey.yourschool.edu`.
The selector is provider-specific (Postmark uses `20220809pm`,
SendGrid uses `s1` / `s2`, Mailgun uses `pic` / `k1`).

**Why it matters:** A passing DKIM signature proves the message wasn't
modified in transit AND was authorized by the domain owner. Without
DKIM, DMARC (below) cannot align and your mail will be quarantined.

### 1.3 DMARC (Domain-based Message Authentication, Reporting & Conformance)

DMARC tells receiving servers what to do when SPF or DKIM fails, AND
where to send daily aggregate reports so you can see attempted
spoofing.

**Where it lives:** TXT record at `_dmarc.yourschool.edu`.

**Recommended starting policy (monitoring only, no enforcement yet):**

```
_dmarc.yourschool.edu.    IN    TXT    "v=DMARC1; p=none; rua=mailto:postmaster@yourschool.edu; ruf=mailto:postmaster@yourschool.edu; pct=100; aspf=r; adkim=r"
```

After 4-6 weeks of clean aggregate reports, tighten to `p=quarantine`,
then `p=reject`.

---

## 2. Per-provider recipes

The platform supports any SMTP-relay-compatible vendor. The five
covered below are the ones we've shipped explicit webhook signature
verifiers for.

### 2.1 Gmail / Google Workspace (small districts, single school)

Best for: small schools (≤ 2 000 students), already on Google Workspace.

1. In Google Admin Console: Apps → Google Workspace → Gmail → Routing.
2. Enable SMTP relay service. Allow the platform's egress IP.
3. SPF: `include:_spf.google.com`
4. DKIM: Admin Console → Authenticate email → Generate DKIM key →
   Add the TXT record at the printed selector.
5. DMARC: as above, start with `p=none`.

**Daily send limit:** 2 000 messages/day per Workspace user. For
larger districts use SES / SendGrid.

### 2.2 Amazon SES (AWS)

Best for: AWS-native deployments. Cheap at scale.

1. Verify the sending domain in SES console (TXT record SES generates).
2. Move out of the sandbox: Support → Open case → Increase sending limit.
   You must explain how you handle bounces + complaints. RunMyCampus's
   `/super/email/health/` dashboard satisfies this requirement —
   include the URL in the case.
3. SPF: `include:amazonses.com`
4. DKIM: Console flips this on automatically and adds 3 CNAMEs at
   `<token>._domainkey.yourschool.edu`. Paste them into DNS.
5. Bounce webhook: create an SNS topic → subscribe an API Gateway →
   Lambda forwarder. The Lambda HMACs the body with your shared secret
   and POSTs to `/super/email/webhook/ses/` with the
   `X-RMC-SNS-Signature` header. Paste the shared secret into
   `/super/email/configure/`.

### 2.3 Postmark

Best for: high-deliverability transactional needs.

1. Sign up; verify domain.
2. SPF: `include:spf.mtasv.net`
3. DKIM: Postmark UI generates a TXT record; paste it.
4. Server token: copy from Postmark → Servers → API Tokens.
5. Webhook signature secret: Postmark → Servers → Settings → Webhooks →
   Bounce webhook → set URL to
   `https://<your-host>/super/email/webhook/postmark/`. Copy the
   "Signing secret" Postmark generates and paste it into the
   "Postmark webhook secret" field on `/super/email/configure/`.

### 2.4 SendGrid (Twilio)

Best for: mixed transactional + marketing volume.

1. Sign up; complete Domain Authentication wizard.
2. SPF: `include:sendgrid.net`
3. DKIM: SendGrid generates 2 CNAMEs (`s1._domainkey`, `s2._domainkey`);
   paste them.
4. API key: Settings → API Keys → Create API Key (Restricted Access,
   Mail Send permission).
5. Event webhook: Settings → Mail Settings → Event Webhook →
   `https://<your-host>/super/email/webhook/sendgrid/`. Enable
   **Bounce** and **Dropped** events.
6. **Signed Event Webhook:** SendGrid uses Ed25519. Until pynacl is
   wired (see honest deferral below), paste the public key into the
   "SendGrid webhook Ed25519 public key" field — the platform accepts
   the deliveries but marks them `signature_unverified=True` in the
   dashboard.

### 2.5 Mailgun

Best for: developer-friendly transactional sends, EU data residency.

1. Sign up; add domain.
2. SPF: `include:mailgun.org`
3. DKIM: Mailgun generates a TXT at `pic._domainkey.yourschool.edu`
   (or `k1._domainkey.yourschool.edu` for older accounts); paste it.
4. SMTP credentials: Sending → Domain settings → SMTP credentials.
5. Webhook signing key: Sending → Webhooks → Webhook signing key.
   Paste the key into "Mailgun webhook signing key" on
   `/super/email/configure/`. Then configure
   **Permanent failure (bounce)** and **Temporary failure** webhooks
   to POST to `https://<your-host>/super/email/webhook/mailgun/`.

---

## 3. Sample DNS records (template — replace placeholders)

```
;; SPF
yourschool.edu.                  IN  TXT  "v=spf1 include:_spf.google.com include:amazonses.com include:sendgrid.net ~all"

;; DKIM — Postmark example
20220809pm._domainkey.yourschool.edu.   IN  TXT  "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQ...IDAQAB"

;; DKIM — SES example (CNAME, NOT TXT)
abcdefghij._domainkey.yourschool.edu.   IN  CNAME  abcdefghij.dkim.amazonses.com.

;; DMARC — monitoring-only starting policy
_dmarc.yourschool.edu.           IN  TXT  "v=DMARC1; p=none; rua=mailto:postmaster@yourschool.edu; pct=100"

;; BIMI (optional — shows your logo in Gmail next to verified messages)
default._bimi.yourschool.edu.    IN  TXT  "v=BIMI1; l=https://yourschool.edu/logo.svg;"
```

---

## 4. Pre-launch checklist for tenant operators

Before flipping the email-delivery override on in production:

- [ ] SPF record published, `include:` chain covers your provider.
- [ ] DKIM record published, selector matches the provider's wizard.
- [ ] DMARC record published at `p=none` (monitoring) for at least 1 week.
- [ ] Bounce webhook URL configured at the provider AND the matching
      shared secret pasted into `/super/email/configure/`.
- [ ] "Send test email to me" button on `/super/email/configure/`
      lands in your inbox (NOT spam) within 30 seconds.
- [ ] `/super/email/health/` shows `Sent` count incrementing on the
      live SSE stream when test emails fire.
- [ ] Per-tenant hourly cap (`SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP`,
      default 200) is appropriate for your school size. Bump via env
      var if you do nightly bulk newsletters; lower if you've seen
      runaway-loop incidents.

---

## 5. "What to do if email lands in spam"

1. **Check the headers.** Most webmail clients show original headers
   on demand. Look for `spf=pass`, `dkim=pass`, `dmarc=pass`. Any
   `fail` is your culprit.
2. **Send a test to <https://www.mail-tester.com>.** You get a numeric
   score + a list of things to fix. Aim for ≥ 8/10.
3. **Warm up the sending IP gradually.** New IPs sending burst-volume
   land in spam by default. Start at 50 messages/day for a week,
   double weekly.
4. **Audit your content.** Avoid `URGENT!!`, all-caps subjects, single-
   image messages, link shorteners. Use a real `Reply-To` set to a
   monitored address.
5. **Check your blocklists.** Paste your sending IP into
   <https://mxtoolbox.com/blacklists.aspx>. Delisting requests are
   per-blocklist.
6. **Verify the platform isn't rate-limited.**
   `/super/email/health/` will show
   `error_kind=rate_limit_exceeded` rows when the per-tenant cap
   blocks a send. Raise the cap via env var if legitimate volume
   exceeds the default.
7. **Inspect bounces.** `/super/email/health/` "Bounce rate" panel
   shows last 24h / 7d / 30d breakdown by kind. `hard_5xx` or
   `provider_HardBounce` rows mean the recipient address is dead —
   suppress the address upstream so you don't keep hitting it.

---

## 6. Honest deferrals (v3.58.x)

These are documented gaps the platform acknowledges but has NOT yet
shipped fixes for:

- **SendGrid Ed25519 signature verification.** Requires `pynacl` (or
  similar) in the platform dependency set. The webhook view currently
  accepts SendGrid deliveries when the operator has pasted a public
  key but marks them `signature_unverified=True`. Tracked for a
  future wave.
- **Mailgun + SES bounce-classification taxonomies.** Each provider
  uses a different vocabulary for bounce types. The platform records
  the raw provider label as `bounce_kind="provider_<type>"` — operator
  reports must join on the literal string until we publish a
  cross-provider normalization map.
- **AWS native SNS message-signing certificate verification.** The
  platform requires a shared-secret HMAC via an API Gateway + Lambda
  relay, NOT direct AWS-signed SNS delivery. Direct AWS-signed
  delivery would require fetching AWS's signing certs at runtime —
  out of scope for v3.58.x.
- **Webhook → EmailDeliveryEvent matching by full Message-ID.** The
  current schema only persists `to_hash` + `subject_prefix`; the
  webhook view does a forgiving prefix match on `subject_prefix`.
  A future migration will add an indexed `message_id_prefix` column
  so bounce attribution is deterministic.
