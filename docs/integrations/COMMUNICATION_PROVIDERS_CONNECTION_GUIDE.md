# Communication Providers Connection Guide

How to wire up SMS / email / push / WhatsApp providers to a deployment.

Cross-reference: `apps/communication/`.

## Email — SendGrid (default)

1. **Sign up:** https://signup.sendgrid.com/
2. **Verify a sending domain:** Settings → Sender Authentication → Authenticate Your Domain → follow CNAME records (DKIM + SPF). Use the same domain as the tenant (e.g. `mail.runmycampus.com`).
3. **Create an API key:** Settings → API Keys → Restricted Access (`Mail Send` only).
4. **Set deployment env vars:**
   ```
   EMAIL_BACKEND=django_sendgrid_v5.backends.SendgridBackend
   SENDGRID_API_KEY=SG.xxxx...
   DEFAULT_FROM_EMAIL=no-reply@mail.runmycampus.com
   ```
5. **Verify:** trigger any password-reset; confirm delivery in the recipient inbox + SendGrid → Activity feed.

### Alternative: AWS SES
- Requires moving out of sandbox (request production access from AWS).
- Region must support SES email sending (e.g. us-east-1, eu-west-1).
- Use `EMAIL_BACKEND=django_ses.SESBackend` + IAM access keys.

## SMS — Twilio (default)

1. **Sign up:** https://www.twilio.com/try-twilio
2. **Buy a long code or short code** for the sending country.
3. **Capture credentials** from the console:
   - `ACCOUNT_SID`
   - `AUTH_TOKEN`
   - `MESSAGING_SERVICE_SID` (recommended over a single number)
4. **Set deployment env vars:**
   ```
   TWILIO_ACCOUNT_SID=ACxxxx...
   TWILIO_AUTH_TOKEN=xxxx...
   TWILIO_MESSAGING_SERVICE_SID=MGxxxx...
   ```
5. **Verify:** in Django admin → Communications → send a test SMS to a verified test number.

### Africa-focused alternatives
- **Africa's Talking** (https://africastalking.com/): broader coverage in KE/UG/TZ/RW/MW/NG.
- **Termii** (https://termii.com/): NG-strong.
- Aggregators have similar wiring: API key + sender ID + base URL → set env vars; the repo communication adapter abstracts the provider differences.

## WhatsApp Business

1. **Apply via Meta or via Twilio:**
   - Direct: https://www.facebook.com/business/m/whatsapp/business-api
   - Via Twilio: easier — same Twilio creds, sender added in console.
2. **Get phone-number SID** approved.
3. **Set env vars** (Twilio path uses the existing Twilio creds + an additional `TWILIO_WHATSAPP_FROM` number).

## Push (web + mobile)

Web push — out of the box (Service Worker is included). No vendor required.

Mobile push (APNs / FCM) — only relevant once the mobile shells are released. Configuration is per-store and out of scope for this guide.

## What this guide does NOT cover

- Telecom regulatory registrations for sender IDs in countries that require them (NG, KE, IN, UAE).
- A2P 10DLC registration in the US.
- Customer-side spam list / DKIM rotation.
