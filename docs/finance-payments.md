## Fee + Payment Integration Guide

### Fee setup (classroom + specialty + custom items)
1. Create a `FeePlan` inside the Finance admin. Pick the academic year, classroom, specialty, and an informative name (e.g., `Form 3 Sci Tuition`).
2. Use the inline `FeeItem` editor to add tuition, activity, or custom fees. Each `FeeItem` inherits the plan’s classroom/specialty context, so invoices are issued per class and subject grouping.
3. Optional installments can be added to `FeeItem` records if you need parts (down payment, balance, etc.).
4. Run `Generate Fee Invoices` in the Finance dashboard to apply the plan to every student in the linked academic year/classroom/specialty.

### Payment providers (cash, bank, MTN, Orange)
- Finance normalizes collection methods (`PaymentMethod`). MTN MoMo and Orange Money have dedicated provider slugs (`mtn_momo`, `orange_momo`). Bank and cash use the default ledger flow.
- Create an `Integration` entry with `provider="payments"` for each channel:
  ```json
  {
    "provider_slug": "mtn_momo",
    "base_url": "https://momo.example.com/pay",
    "secret": "super-secret",
    "callback_path": "/finance/payments/webhook/mtn_momo/",
    "signature_format": "{invoice_id}:{amount}",
    "signature_header": "X-Signature"
  }
  ```
  - `base_url`: the redirect URL parents open to pay.
  - `callback_path`: the webhook path Render exposes (can be absolute or relative).
  - `secret`: shared secret used to sign callbacks.
  - `signature_format`: optional format string for signing/verifying payloads.
  - `signature_header`: optional custom header name (default `X-Signature`).
- The Finance dashboard automatically builds signed links that include `sig` + `callback` parameters. You can share those with parents or embed them in reminder emails.

### Webhooks & auto-payments
- Render exposes `POST /finance/payments/webhook/<provider_slug>/`. The payload must include `invoice_id`, `amount`, and optionally `reference`/`external_reference`.
- The webhook verifies the HMAC signature using the integration secret. On success it creates a `Payment` record (duplicate submissions are deduped via `external_reference`) and posts it to the ledger.
- Example payload: `{"invoice_id": 123, "amount": 85000, "reference": "MTN-RTR-789"}` with the signature header.

### Reminders & receipts
- The `send_payment_reminders` management command emails guardians (who have `can_view_finance=True`) before the invoice due date using the configured email `Integration`.
- Schedule the command on Render (cron or worker) so reminders fire regularly. It reuses the same payment link and tracks sends in `PaymentReminderLog`.
- Receipts are available via the Finance invoice list and download as PDFs via WeasyPrint whenever the environment supports it.

### Environment variables
Ensure the following vars exist on Render (and locally):
| Key | Purpose |
| --- | --- |
| `DATABASE_URL` | Primary database connection (required). |
| `SECRET_KEY` | Django secret used for signing payment links. |
| `SITE_URL` | Base URL used to build callback links. |
| `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | For reminder emails. |
| `DEFAULT_FROM_EMAIL` | Email address used when sending reminders. |
| `MTN_MOMO_SECRET` / `ORANGE_MOMO_SECRET` (optional) | Can be referenced inside integration configs if you prefer env variables to be injected manually.

### Commands
- `python manage.py send_payment_reminders`: send upcoming invoice reminders.
- `python manage.py migrate`: apply the new `PaymentReminder*` tables and webhook-ready schema.
- `python manage.py seed_finance_defaults`: reseed OHADA compliance + Chart of Accounts if needed.
