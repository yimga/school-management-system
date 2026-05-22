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

## Code references

- `apps/schools/welcome_email.py` — HTML + set-password link
- `apps/schools/provision_email_urls.py` — tenant absolute URLs for email
- `apps/schools/tasks.py` — sends welcome mail inline when provisioning completes
- `render.yaml` — default SMTP host comments (Brevo)
