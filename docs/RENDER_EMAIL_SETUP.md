# Render outbound email (welcome + notifications)

Provisioning sends a **welcome email with a set-password link** after the Celery worker finishes `provision_school_task`. Mail is sent with Django’s **SMTP** backend (`EMAIL_*` env vars). Secrets are **not** stored in the repo — configure them in the Render Dashboard.

## Recommended free tier: Brevo (formerly Sendinblue)

| Item | Value |
|------|--------|
| Free allowance | ~300 transactional emails/day |
| SMTP host | `smtp-relay.brevo.com` |
| Port | `587` (TLS) |
| Login | Your Brevo account email |
| Password | **SMTP key** from Brevo → SMTP & API → Generate SMTP key |

**Steps**

1. Sign up at [https://www.brevo.com](https://www.brevo.com).
2. Verify a sender (Settings → Senders): e.g. `noreply@runmycampus.com` (domain DNS helps deliverability).
3. Create an SMTP key; copy it once.
4. In **Render**, set on **both** `school-management-system` (web) **and** `school-management-system-worker`:

| Variable | Example |
|----------|---------|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | `smtp-relay.brevo.com` |
| `EMAIL_PORT` | `587` |
| `EMAIL_USE_TLS` | `True` |
| `EMAIL_HOST_USER` | your Brevo login email |
| `EMAIL_HOST_PASSWORD` | Brevo SMTP key (secret) |
| `DEFAULT_FROM_EMAIL` | `noreply@runmycampus.com` (must match verified sender) |

5. Redeploy worker + web. Create a test school; in **worker logs** look for `Welcome email sent to …`.

> **Deliverability (do not skip):** verifying a sender is the minimum. For mail to
> reach the inbox (not spam) you must add **SPF + DKIM** (and ideally DMARC) DNS
> records for the sending domain — Brevo gives you the exact TXT records under
> *Senders, Domains & Dedicated IPs → Domains → Authenticate*. Full walkthrough:
> [docs/EMAIL_DELIVERABILITY.md](EMAIL_DELIVERABILITY.md).

> **render.yaml note:** `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` are declared
> `sync: false` on both the web and worker services, so a Blueprint deploy will
> **prompt** you for them rather than silently leaving mail unconfigured.

## Alternatives (also SMTP-compatible)

| Provider | Free tier (approx.) | SMTP host |
|----------|---------------------|-----------|
| SendGrid | 100 emails/day | `smtp.sendgrid.net` (user `apikey`, password = API key) |
| Mailgun | Trial then paid | `smtp.mailgun.org` |
| Gmail | Not for production bulk | `smtp.gmail.com` + App Password (low limits, spam risk) |

## Common failures

- **Worker has no `EMAIL_*`** — welcome mail runs on the worker after provisioning; web-only SMTP vars are not enough.
- **Worker suspended / queue backlog** — provisioning (and mail) waits until the worker runs.
- **Unverified sender** — Brevo/SendGrid reject or spam-folder mail from `DEFAULT_FROM_EMAIL`.
- **Spam folder** — check promotions/spam for the contact email used in Tenant Studio.

## Signup *activation / verification* email (the "no activation email" case)

This is a **different** path from the welcome email above and a common source of
confusion:

- It is sent by the **web** service (not the worker), from
  `apps/schools/signup_views.py`, via
  `send_transactional(..., async_send=True)`.
- `async_send=True` dispatches the SMTP attempt on a **daemon thread** and
  returns `{ok: True, queued: True}` immediately, so the signup request always
  succeeds. If `EMAIL_*` is misconfigured, the failure is recorded on an
  `EmailDeliveryEvent` audit row but the user simply never receives mail — it
  looks like "signup worked but no email arrived."
- Therefore the **web** service also needs the `EMAIL_*` env vars — not just the
  worker. Set them on both.

### In-app SMTP settings need `DJANGO_CRYPTOGRAPHY_KEYS`

`get_resolved_smtp_config` cascades tenant `School.settings["email_delivery"]`
→ operator `SiteSettings.email_delivery` → env vars. If you configured SMTP in
the **in-app operator settings page**, the password is stored Fernet-encrypted
(`host_password_encrypted_b64`) and `DJANGO_CRYPTOGRAPHY_KEYS` must be set or it
decrypts to empty (→ `no_smtp_password` → silent failure). The plain `EMAIL_*`
env-var path needs no Fernet key — prefer it for simplicity.

## Diagnose in one command

```
python manage.py test_email_health                 # full diagnosis
python manage.py test_email_health --send-to you@x # also send a live test email
python manage.py test_email_health --json          # machine-readable
```
Reports the resolved `source` (env / site_settings_override), whether
host/user/password resolved, and a severity-ranked diagnosis
(`non_smtp_backend`, `no_smtp_host`, `no_smtp_user`, `no_smtp_password`,
`fernet_unavailable`, …). `verdict.deliverable` is the bottom line.

## Code references

- `apps/schools/welcome_email.py` — HTML + set-password link (welcome email)
- `apps/schools/signup_views.py` — signup verification/activation email (web, async)
- `apps/schoolops/email_delivery.py` — `send_transactional` + `get_resolved_smtp_config`
- `apps/schools/provision_email_urls.py` — tenant absolute URLs for email
- `apps/schools/tasks.py` — sends welcome mail inline when provisioning completes
- `apps/schoolops/management/commands/test_email_health.py` — the diagnostic above
- `render.yaml` — default SMTP host comments (Brevo)
