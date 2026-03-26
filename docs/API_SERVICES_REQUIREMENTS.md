# API & Services Requirements for School Management Platform

## Overview
This document lists all APIs and external services needed to run the platform, including providers, pricing, and free alternatives.

---

## 1. **EMAIL SERVICES** 📧

### **Required for:** User notifications, password resets, grade publications, deadline reminders

### **Options:**

#### **A. SMTP (Free/Paid)**
- **Gmail SMTP** (Free)
  - **Provider:** Google
  - **Platform:** Gmail account
  - **Limits:** 500 emails/day (free account), 2000/day (Google Workspace)
  - **Setup:** Use Gmail app password
  - **Cost:** FREE (personal) or $6/user/month (Google Workspace)
  - **Best for:** Small schools, development

- **SendGrid** (Freemium)
  - **Provider:** Twilio SendGrid
  - **Platform:** https://sendgrid.com
  - **Free Tier:** 100 emails/day forever
  - **Paid:** Starts at $19.95/month (50,000 emails)
  - **Best for:** Production, reliable delivery

- **Mailgun** (Freemium)
  - **Provider:** Mailgun
  - **Platform:** https://mailgun.com
  - **Free Tier:** 5,000 emails/month for 3 months, then 1,000/month
  - **Paid:** Starts at $35/month (50,000 emails)
  - **Best for:** Developers, transactional emails

- **Amazon SES** (Very Cheap)
  - **Provider:** AWS
  - **Platform:** https://aws.amazon.com/ses
  - **Free Tier:** 62,000 emails/month (if on EC2)
  - **Paid:** $0.10 per 1,000 emails
  - **Best for:** High volume, AWS users

#### **B. Free Alternatives:**
- **Django Console Backend** (Development only)
  - Prints emails to console
  - **Cost:** FREE
  - **Use:** Development/testing

- **Mailtrap** (Testing)
  - **Provider:** Mailtrap
  - **Platform:** https://mailtrap.io
  - **Free Tier:** 500 emails/month
  - **Best for:** Testing email templates

**Recommendation:** Start with Gmail SMTP (free), upgrade to SendGrid or Mailgun for production.

---

## 2. **SMS SERVICES** 📱

### **Required for:** Grade publication notifications, deadline reminders, parent alerts

### **Options:**

#### **A. Twilio** (Paid)
- **Provider:** Twilio
- **Platform:** https://twilio.com
- **Free Tier:** $15.50 credit (trial)
- **Paid:** ~$0.0075 per SMS (varies by country)
- **Setup:** Requires `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
- **Best for:** Global, reliable, developer-friendly

#### **B. AfricasTalking** (Paid)
- **Provider:** AfricasTalking
- **Platform:** https://africastalking.com
- **Free Tier:** None
- **Paid:** ~$0.01 per SMS (Africa-focused)
- **Setup:** Requires API key
- **Best for:** African markets, competitive rates

#### **C. Free Alternatives:**
- **Console Logging** (Development)
  - Logs SMS to console
  - **Cost:** FREE
  - **Use:** Development/testing

- **WhatsApp Deep Links** (Free)
  - Uses `wa.me` links (no API needed)
  - **Cost:** FREE
  - **Use:** Manual communication (already implemented)
  - **Note:** Requires WhatsApp Business API for automation (paid)

**Recommendation:** Use WhatsApp deep links for now (free), add Twilio/AfricasTalking when budget allows.

---

## 3. **WHATSAPP BUSINESS API** 💬

### **Required for:** Automated WhatsApp messaging (optional, currently using deep links)

### **Options:**

#### **A. WhatsApp Business Cloud API** (Paid)
- **Provider:** Meta (via Twilio/MessageBird)
- **Platform:** https://developers.facebook.com/docs/whatsapp
- **Free Tier:** None
- **Paid:** ~$0.005-0.01 per message (varies by country)
- **Setup:** Requires Twilio account + WhatsApp Business verification
- **Best for:** Automated messaging at scale

#### **B. Twilio WhatsApp** (Paid)
- **Provider:** Twilio
- **Platform:** https://twilio.com/whatsapp
- **Free Tier:** $15.50 credit (trial)
- **Paid:** ~$0.005 per message
- **Best for:** Easy integration if already using Twilio

#### **C. Free Alternative:**
- **WhatsApp Deep Links** (Current Implementation)
  - Uses `wa.me` links
  - **Cost:** FREE
  - **Limitation:** Manual only (user clicks link)
  - **Status:** ✅ Already implemented

**Recommendation:** Keep using deep links (free) until automation is needed.

---

## 4. **PAYMENT PROCESSORS** 💳

### **Required for:** Fee payments, invoice processing

### **⚠️ IMPORTANT FOR CAMEROON/BUEA:**
**Stripe does NOT directly integrate with MTN Mobile Money or Orange Money.** However, your platform **already has MTN MoMo and Orange Money processors built-in!** These are the preferred payment methods in Cameroon.

### **Options for Cameroon/Buea:**

#### **A. MTN Mobile Money** ✅ **ALREADY INTEGRATED** (Recommended for Cameroon)
- **Provider:** MTN Cameroon
- **Platform:** MTN Mobile Money API
- **Status:** ✅ Already implemented in `apps/finance/payment_processors.py`
- **Fees:** Contact MTN Cameroon for merchant account rates (typically 1-2% per transaction)
- **Setup:** Requires `MTN_MOMO_API_KEY`, `MTN_MOMO_API_SECRET` from MTN Cameroon
- **How to get:** Contact MTN Cameroon Business Services or visit MTN Cameroon office
- **Best for:** Cameroon (most popular mobile money)
- **Free Alternative:** Manual payment entry (see below)

#### **B. Orange Money** ✅ **ALREADY INTEGRATED** (Recommended for Cameroon)
- **Provider:** Orange Cameroon
- **Platform:** Orange Money API
- **Status:** ✅ Already implemented in `apps/finance/payment_processors.py`
- **Fees:** Contact Orange Cameroon for merchant account rates (typically 1-2% per transaction)
- **Setup:** Requires `ORANGE_MONEY_API_KEY`, `ORANGE_MONEY_API_SECRET` from Orange Cameroon
- **How to get:** Contact Orange Cameroon Business Services or visit Orange Cameroon office
- **Best for:** Cameroon (second most popular mobile money)
- **Free Alternative:** Manual payment entry (see below)

#### **C. Stripe** (Paid - International Cards Only)
- **Provider:** Stripe
- **Platform:** https://stripe.com
- **Free Tier:** None
- **Fees:** 2.9% + $0.30 per transaction
- **⚠️ LIMITATION:** Stripe does NOT support MTN MoMo or Orange Money directly
- **Best for:** International card payments (not common in Cameroon)
- **Note:** Stripe is mainly for credit/debit cards, not mobile money

#### **D. Flutterwave** (Paid - Supports Mobile Money)
- **Provider:** Flutterwave
- **Platform:** https://flutterwave.com
- **Free Tier:** None
- **Fees:** ~1.4% + $0.20 per transaction
- **Supports:** MTN MoMo, Orange Money, Airtel Money (via their API)
- **Best for:** If you want a single API for multiple mobile money providers
- **Note:** More expensive than direct MTN/Orange integration

#### **E. Paystack** (Paid - Nigeria/Ghana Focus)
- **Provider:** Paystack
- **Platform:** https://paystack.com
- **Free Tier:** None
- **Fees:** ~1.5% + $0.20 per transaction
- **Limitation:** Not available in Cameroon (Nigeria, Ghana, South Africa only)

#### **F. PayPal** (Paid - International)
- **Provider:** PayPal
- **Platform:** https://paypal.com/developer
- **Free Tier:** None
- **Fees:** 2.9% + $0.30 per transaction
- **⚠️ LIMITATION:** PayPal does NOT support MTN MoMo or Orange Money
- **Best for:** International payments (not common in Cameroon)

#### **G. FREE ALTERNATIVE: Manual Payment Entry** ✅ **RECOMMENDED TO START**
- **How it works:** Parents pay via MTN MoMo/Orange Money manually, then:
  1. Parent sends payment confirmation (screenshot/receipt)
  2. School admin records payment in the system
  3. Payment is marked as paid
- **Cost:** **FREE** (no API fees)
- **Setup:** No API keys needed
- **Status:** ✅ Already implemented in the platform
- **Best for:** Small-medium schools, starting out, avoiding API fees
- **Workflow:** 
  - Parent receives invoice with payment code
  - Parent pays via MTN MoMo/Orange Money app
  - Parent sends confirmation to school
  - Admin records payment in Finance module

**Recommendation for Buea, Cameroon:**
1. **Start with Manual Payment Entry** (FREE) - No API needed, works immediately
2. **Add MTN MoMo API** when volume grows (contact MTN Cameroon Business Services)
3. **Add Orange Money API** if many parents use Orange (contact Orange Cameroon Business Services)
4. **Skip Stripe/PayPal** - They don't support mobile money in Cameroon

---

## 5. **DATABASE** 🗄️

### **Required for:** Core data storage

### **Options:**

#### **A. PostgreSQL** (Free/Paid)
- **Provider:** Various (AWS RDS, Render, Railway, Supabase)
- **Free Tier Options:**
  - **Supabase:** 500MB free
  - **Railway:** $5/month credit (effectively free for small apps)
  - **Render:** Free tier available
  - **Neon:** 3GB free
- **Paid:** $5-20/month for small-medium databases
- **Best for:** Production, reliable, scalable

#### **B. SQLite** (Free)
- **Built-in:** Python/Django
- **Cost:** FREE
- **Limitations:** Single file, not ideal for production with multiple workers
- **Best for:** Development, small deployments

**Recommendation:** Use SQLite for development, PostgreSQL (Supabase/Railway free tier) for production.

---

## 6. **CACHING & BACKGROUND TASKS** ⚡

### **Required for:** Performance, async tasks (email/SMS sending)

### **Options:**

#### **A. Redis** (Free/Paid)
- **Provider:** Various (Redis Cloud, Upstash, Railway)
- **Free Tier Options:**
  - **Upstash:** 10,000 commands/day free
  - **Redis Cloud:** 30MB free
  - **Railway:** Included in $5 credit
- **Paid:** $5-10/month for small instances
- **Use:** Caching, Celery broker, sessions

#### **B. Free Alternatives:**
- **Django LocMemCache** (Free)
  - In-memory cache (per worker)
  - **Cost:** FREE
  - **Limitation:** Not shared across workers
  - **Use:** Development, single-worker deployments

- **Django Database Backend** (Free)
  - Uses database for Celery results
  - **Cost:** FREE
  - **Use:** Small deployments (already configured)

**Recommendation:** Start with LocMemCache + Database backend (free), add Redis when scaling.

---

## 7. **AI/ML SERVICES** 🤖

### **Required for:** AI Copilot / internal chat (optional)

### **Default (RunMyCampus): self-hosted Ollama**

- **Product chat** (`general_chat`) uses **Ollama + rules fallback** only — no Google Gemini in code paths.
- **Setup:** Install [Ollama](https://ollama.com), `ollama pull <model>`, set `OLLAMA_ENDPOINT` and `OLLAMA_MODEL` (see `.env.example` and `docs/OLLAMA_OPERATIONS_AND_UPDATES.md`).
- **Cost:** Infrastructure you operate; no per-token bill to Google for copilot.
- **Optional gateway tasks** (workflow draft, etc.) may use **vLLM** or **LiteLLM** proxy if configured — separate from copilot chat.

### **Alternatives (not required for copilot)**

- **Disable AI** — set `AI_GATEWAY_ENABLED=0` or leave Ollama down; rules fallback may still respond if enabled.
- Third-party SaaS LLMs are **not** wired for in-product chat in this repository.

---

## 8. **MONITORING & OBSERVABILITY** 📊

### **Required for:** Error tracking, performance monitoring

### **Options:**

#### **A. Sentry** (Freemium)
- **Provider:** Sentry
- **Platform:** https://sentry.io
- **Free Tier:** 5,000 events/month
- **Paid:** Starts at $26/month (50,000 events)
- **Setup:** Requires `SENTRY_DSN`
- **Best for:** Production error tracking

#### **B. Prometheus** (Free)
- **Provider:** Self-hosted or Grafana Cloud
- **Platform:** https://prometheus.io
- **Free Tier:** Self-hosted is free
- **Grafana Cloud:** 10,000 series free
- **Setup:** Already integrated (`prometheus-client`)
- **Best for:** Metrics, performance monitoring

#### **C. Free Alternatives:**
- **Django Logging** (Free)
  - File-based logging
  - **Cost:** FREE
  - **Use:** Basic error tracking

- **Console Logging** (Free)
  - Prints to console
  - **Cost:** FREE
  - **Use:** Development

**Recommendation:** Use Prometheus (free, already integrated) + Sentry free tier for production.

---

## 9. **STATIC FILE STORAGE** 📁

### **Required for:** CSS, JS, images, uploaded files

### **Options:**

#### **A. WhiteNoise** (Free) ✅ Currently Used
- **Built-in:** Django middleware
- **Cost:** FREE
- **Limitation:** Served by Django (not ideal for high traffic)
- **Best for:** Small-medium deployments

#### **B. AWS S3** (Paid)
- **Provider:** AWS
- **Platform:** https://aws.amazon.com/s3
- **Free Tier:** 5GB storage, 20,000 GET requests/month (first year)
- **Paid:** $0.023/GB storage, $0.005 per 1,000 requests
- **Best for:** High traffic, scalable

#### **C. Cloudflare R2** (Freemium)
- **Provider:** Cloudflare
- **Platform:** https://cloudflare.com/products/r2
- **Free Tier:** 10GB storage, 1M Class A operations/month
- **Paid:** $0.015/GB storage
- **Best for:** S3-compatible, cheaper than S3

#### **D. Free Alternatives:**
- **WhiteNoise** (Current)
  - **Cost:** FREE
  - **Use:** Small-medium deployments

**Recommendation:** Keep WhiteNoise for now, migrate to Cloudflare R2 when traffic grows.

---

## 10. **GEOIP SERVICES** 🌍

### **Required for:** IP-based country detection (compliance)

### **Options:**

#### **A. MaxMind GeoLite2** (Free)
- **Provider:** MaxMind
- **Platform:** https://dev.maxmind.com/geoip/geolite2-free-geoip-database
- **Free Tier:** Free database (requires account)
- **Setup:** Already integrated (`geoip2`, `maxminddb-geolite2`)
- **Best for:** Free, accurate

#### **B. ipapi.co** (Freemium)
- **Provider:** ipapi.co
- **Platform:** https://ipapi.co
- **Free Tier:** 1,000 requests/day
- **Paid:** $10/month (unlimited)
- **Best for:** API-based (no database updates)

**Recommendation:** Use MaxMind GeoLite2 (free, already integrated).

---

## 11. **WEBHOOK SECURITY** 🔒

### **Required for:** Payment webhook verification

### **Options:**

#### **A. Built-in Signature Verification** (Free) ✅ Currently Used
- **Implementation:** Django middleware
- **Cost:** FREE
- **Use:** Verify webhook signatures from payment providers

**Recommendation:** Use built-in verification (already implemented).

---

## SUMMARY TABLE

| Service | Required? | Free Option | Paid Option | Recommendation for Cameroon |
|---------|-----------|-------------|-------------|----------------------------|
| **Email** | ✅ Yes | Gmail SMTP | SendGrid/Mailgun | Start with Gmail (free), upgrade if needed |
| **SMS** | ⚠️ Optional | WhatsApp Deep Links | Twilio/AfricasTalking | Use WhatsApp deep links (free) |
| **WhatsApp API** | ⚠️ Optional | Deep Links (manual) | Twilio WhatsApp | Keep deep links (free), add API later |
| **Payments** | ⚠️ Optional | **Manual Entry** ✅ | MTN MoMo/Orange Money API | **Start with Manual Entry (FREE)** - No API fees! |
| **Database** | ✅ Yes | SQLite (dev) | PostgreSQL (prod) | SQLite dev, PostgreSQL (Supabase free) prod |
| **Cache/Redis** | ⚠️ Optional | LocMemCache | Redis Cloud | Start with LocMemCache (free), add Redis later |
| **AI Copilot** | ⚠️ Optional | Disable | Self-hosted Ollama | Run Ollama on your network or disable; see `docs/OLLAMA_OPERATIONS_AND_UPDATES.md` |
| **Monitoring** | ✅ Recommended | Prometheus (free) | Sentry (free tier) | Use Prometheus + Sentry free tier |
| **Static Files** | ✅ Yes | WhiteNoise | Cloudflare R2 | Keep WhiteNoise (free), migrate to R2 later |
| **GeoIP** | ✅ Yes | MaxMind GeoLite2 | - | Use MaxMind (free, already integrated) |

---

## MINIMUM VIABLE SETUP (FREE) ✅ **RECOMMENDED FOR BUEA, CAMEROON**

For a school in Buea, Cameroon to run the platform with **zero API costs**:

1. **Email:** Gmail SMTP (free) - 500 emails/day
2. **SMS:** WhatsApp Deep Links (free, manual) - Parents click link to message school
3. **Payments:** **Manual Payment Entry** (free) - Parents pay via MTN MoMo/Orange Money, admin records payment
4. **Database:** SQLite (dev) or PostgreSQL (Supabase free tier - 500MB)
5. **Cache:** LocMemCache (free) - Built into Django
6. **AI:** Disable AI Copilot (free) — or run **Ollama** on your own hardware (no Google API key)
7. **Monitoring:** Prometheus (free, self-hosted) - Already integrated
8. **Static Files:** WhiteNoise (free) - Already configured
9. **GeoIP:** MaxMind GeoLite2 (free) - Already integrated

**Total Monthly Cost: $0** 💰

**Payment Workflow (Free):**
1. School generates invoice with payment code
2. Parent pays via MTN Mobile Money or Orange Money app
3. Parent sends payment confirmation (screenshot/receipt) via WhatsApp
4. School admin records payment in Finance module
5. Payment is marked as paid, invoice updated

**This works perfectly for small-medium schools in Cameroon!**

---

## RECOMMENDED PRODUCTION SETUP FOR CAMEROON

For a production deployment in Buea, Cameroon with reliability:

### **Option 1: Still Free (Recommended)**
1. **Email:** Gmail SMTP (free) - Upgrade to SendGrid only if hitting limits
2. **SMS:** WhatsApp Deep Links (free) - Works perfectly for Cameroon
3. **Payments:** **Manual Payment Entry** (free) - Most cost-effective for Cameroon
4. **Database:** PostgreSQL on Supabase (free tier - 500MB)
5. **Cache:** LocMemCache (free) - Upgrade to Redis only if scaling
6. **AI:** Google Gemini (free tier - 60 req/min) or disable
7. **Monitoring:** Prometheus (free) + Sentry (free tier)
8. **Static Files:** WhiteNoise (free) - Upgrade to Cloudflare R2 only if high traffic
9. **GeoIP:** MaxMind GeoLite2 (free)

**Estimated Monthly Cost: $0** 💰

### **Option 2: With Mobile Money APIs (When Volume Grows)**
1. **Email:** Gmail SMTP (free) or SendGrid ($19.95/month)
2. **SMS:** WhatsApp Deep Links (free) or Twilio (~$0.0075/SMS)
3. **Payments:** **MTN Mobile Money API** (contact MTN Cameroon for rates, typically 1-2% per transaction)
   - OR **Orange Money API** (contact Orange Cameroon for rates, typically 1-2% per transaction)
   - **Note:** You can use BOTH - parents choose their preferred mobile money
4. **Database:** PostgreSQL on Supabase (free tier) or Railway ($5/month)
5. **Cache:** Redis on Upstash (free tier) or Railway ($5/month)
6. **AI:** Self-hosted **Ollama** or disable
7. **Monitoring:** Sentry (free tier) + Prometheus (free)
8. **Static Files:** WhiteNoise (free) or Cloudflare R2 (free tier)
9. **GeoIP:** MaxMind GeoLite2 (free)

**Estimated Monthly Cost: $5-30** (mostly payment processing fees, no fixed costs)

**Key Point:** Even with mobile money APIs, you can still use manual entry as a fallback!

---

## WHERE TO GET API KEYS

### **Free Services:**
1. **Supabase (PostgreSQL):** https://supabase.com
3. **Upstash (Redis):** https://upstash.com
4. **MaxMind GeoLite2:** https://dev.maxmind.com/geoip/geolite2-free-geoip-database
5. **SendGrid (100 emails/day):** https://sendgrid.com
6. **Mailgun (trial):** https://mailgun.com

### **Cameroon-Specific Payment APIs:**
1. **MTN Mobile Money (Cameroon):**
   - **Contact:** MTN Cameroon Business Services
   - **Location:** MTN Cameroon offices in Buea or Douala
   - **Website:** https://mtn.cm (Business section)
   - **What you need:** Business registration, bank account, merchant application
   - **Cost:** Typically 1-2% per transaction (negotiable based on volume)

2. **Orange Money (Cameroon):**
   - **Contact:** Orange Cameroon Business Services
   - **Location:** Orange Cameroon offices in Buea or Douala
   - **Website:** https://orange.cm (Business section)
   - **What you need:** Business registration, bank account, merchant application
   - **Cost:** Typically 1-2% per transaction (negotiable based on volume)

### **Paid Services (Sign up for free trials):**
1. **Twilio:** https://twilio.com (free $15.50 credit)
2. **Sentry:** https://sentry.io (free tier)
3. **Cloudflare R2:** https://cloudflare.com/products/r2
4. **Flutterwave:** https://flutterwave.com (supports MTN MoMo/Orange Money via their API)

---

## ENVIRONMENT VARIABLES NEEDED

Add these to your `.env.local` file:

```bash
# Email (Gmail SMTP - Free)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# SMS (Twilio - Paid, or leave empty to use console logging)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=

# Payments - Cameroon Mobile Money (Contact MTN/Orange Cameroon for API keys)
# Leave empty to use manual payment entry (FREE)
MTN_MOMO_API_KEY=
MTN_MOMO_API_SECRET=
ORANGE_MONEY_API_KEY=
ORANGE_MONEY_API_SECRET=

# International Payments (Optional - Stripe doesn't support mobile money)
STRIPE_API_KEY=
STRIPE_SECRET_KEY=

# Database (PostgreSQL - Free tier available)
DATABASE_URL=postgres://user:pass@host:5432/dbname

# Redis (Optional - Free tier available)
REDIS_URL=redis://host:6379/0

# AI Copilot (self-hosted Ollama — see docs/OLLAMA_OPERATIONS_AND_UPDATES.md)
OLLAMA_ENDPOINT=http://localhost:11434/api/generate
OLLAMA_MODEL=llama3

# Monitoring (Sentry - Free tier)
SENTRY_DSN=

# Observability (Optional)
OBSERVABILITY_API_KEY=
```

---

## NOTES FOR CAMEROON/BUEA

- **✅ You can run the entire platform for FREE** - No API costs needed
- **✅ MTN Mobile Money and Orange Money processors are ALREADY BUILT-IN** - Just need API keys from MTN/Orange Cameroon
- **❌ Stripe does NOT support MTN MoMo or Orange Money** - Use the built-in processors instead
- **✅ Manual payment entry is FREE** - Parents pay via mobile money, admin records payment (no API fees)
- **✅ WhatsApp deep links are FREE** - Works perfectly for Cameroon (most parents use WhatsApp)
- **✅ Start with free options, add APIs only when volume grows** - Most schools can run entirely free
- **✅ All services marked "Optional" can be disabled** - Platform works without them
- **✅ Free tiers are usually sufficient** for small-medium schools in Cameroon

## CAMEROON-SPECIFIC RECOMMENDATIONS

### **Payment Strategy:**
1. **Phase 1 (Start):** Use Manual Payment Entry (FREE)
   - Parents pay via MTN MoMo/Orange Money app
   - Send confirmation to school via WhatsApp
   - Admin records payment in system
   - **Cost: $0**

2. **Phase 2 (Scale):** Add MTN Mobile Money API
   - Contact MTN Cameroon Business Services
   - Get merchant account and API keys
   - Automated payment confirmation
   - **Cost: 1-2% per transaction**

3. **Phase 3 (Optional):** Add Orange Money API
   - Contact Orange Cameroon Business Services
   - Support both MTN and Orange Money
   - Parents choose their preferred provider
   - **Cost: 1-2% per transaction**

### **Communication Strategy:**
- **WhatsApp Deep Links** (FREE) - Perfect for Cameroon (everyone uses WhatsApp)
- No need for SMS API initially
- Can add Twilio/AfricasTalking later if needed

### **Email Strategy:**
- **Gmail SMTP** (FREE) - 500 emails/day is plenty for most schools
- Upgrade to SendGrid only if hitting limits

**Bottom Line: You can run this platform for $0/month in Cameroon!** 💰
