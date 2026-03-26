# Cameroon/Buea Setup Guide - School Management Platform

## Quick Answer: Can You Run This Platform for FREE? ✅ YES!

**You can run the entire platform for $0/month with free alternatives for everything.**

---

## Payment Methods in Cameroon

### ❌ **Stripe Does NOT Support MTN Mobile Money or Orange Money**

Stripe only supports credit/debit cards and bank transfers. It does NOT integrate with:
- MTN Mobile Money (MoMo)
- Orange Money
- Other African mobile money services

### ✅ **Your Platform ALREADY Has MTN MoMo & Orange Money Built-In!**

The platform already includes processors for:
- ✅ **MTN Mobile Money** (`MTNMobileMoneyProcessor`)
- ✅ **Orange Money** (`OrangeMoneyProcessor`)

These are ready to use once you get API keys from MTN/Orange Cameroon.

---

## FREE Setup for Buea, Cameroon

### **1. Payments: Manual Entry (FREE)** ✅ **RECOMMENDED**

**How it works:**
1. School generates invoice with payment code
2. Parent pays via MTN Mobile Money or Orange Money app (on their phone)
3. Parent sends payment confirmation (screenshot/receipt) via WhatsApp
4. School admin records payment in Finance module
5. Payment is marked as paid automatically

**Cost:** $0 (no API fees)
**Setup:** No API keys needed
**Status:** ✅ Already implemented

**When to upgrade:** Add MTN/Orange Money API when you have 100+ payments/month and want automation.

---

### **2. Email: Gmail SMTP (FREE)**

**Setup:**
- Use a Gmail account
- Enable 2-factor authentication
- Generate an "App Password"
- Configure in `.env.local`:
  ```
  EMAIL_HOST=smtp.gmail.com
  EMAIL_PORT=587
  EMAIL_USE_TLS=True
  EMAIL_HOST_USER=your-school@gmail.com
  EMAIL_HOST_PASSWORD=your-app-password
  ```

**Cost:** $0
**Limits:** 500 emails/day (plenty for most schools)

---

### **3. SMS/Communication: WhatsApp Deep Links (FREE)**

**Already implemented!** Parents click WhatsApp buttons to message the school.

**Cost:** $0
**Setup:** Already done
**Status:** ✅ Working

---

### **4. Database: SQLite (FREE) or PostgreSQL Free Tier**

**Development:** SQLite (free, built-in)
**Production:** PostgreSQL on Supabase (500MB free)

**Cost:** $0

---

### **5. Everything Else: FREE**

- **Cache:** LocMemCache (free, built-in)
- **AI Copilot:** Google Gemini free tier (60 requests/min) or disable
- **Monitoring:** Prometheus (free, already integrated)
- **Static Files:** WhiteNoise (free, already configured)
- **GeoIP:** MaxMind GeoLite2 (free, already integrated)

---

## When to Add Paid Services

### **Add MTN Mobile Money API When:**
- You have 100+ payments/month
- You want automated payment confirmation
- You want to reduce manual work

**How to get MTN MoMo API:**
1. Contact MTN Cameroon Business Services
2. Visit MTN Cameroon office in Buea or Douala
3. Apply for merchant account
4. Get API keys (typically 1-2% per transaction fee)

**Cost:** 1-2% per transaction (no monthly fee)

### **Add Orange Money API When:**
- Many parents use Orange Money
- You want to support both MTN and Orange

**How to get Orange Money API:**
1. Contact Orange Cameroon Business Services
2. Visit Orange Cameroon office in Buea or Douala
3. Apply for merchant account
4. Get API keys (typically 1-2% per transaction fee)

**Cost:** 1-2% per transaction (no monthly fee)

---

## Free Alternatives Summary

| Service | Paid Option | Free Alternative | Status |
|---------|-------------|------------------|--------|
| **Payments** | MTN MoMo API (1-2% fee) | Manual Entry | ✅ FREE |
| **Email** | SendGrid ($20/month) | Gmail SMTP | ✅ FREE |
| **SMS** | Twilio (~$0.0075/SMS) | WhatsApp Deep Links | ✅ FREE |
| **Database** | PostgreSQL ($5/month) | SQLite or Supabase free | ✅ FREE |
| **Cache** | Redis ($5/month) | LocMemCache | ✅ FREE |
| **AI** | OpenAI ($0.002/token) | Self-hosted Ollama | ✅ FREE (your infra) |
| **Monitoring** | Sentry ($26/month) | Prometheus (free) | ✅ FREE |
| **Static Files** | Cloudflare R2 | WhiteNoise | ✅ FREE |

**Total Cost: $0/month** 💰

---

## Default Buea/Cameroon configuration

The platform ships with **defaults appropriate for Buea, Cameroon**. Set these in `.env.local` (or `.env`) so server-side dates, currency, and region behaviour are correct:

| Variable       | Buea/Cameroon value   | Purpose |
|----------------|------------------------|--------|
| `REGION_CODE`  | `CMR`                  | ISO region: drives currency (XAF), grading (0–20), date format, compliance. |
| `TIME_ZONE`    | `Africa/Douala`        | IANA timezone for "today", report dates, and server-side datetime. |

**For other regions/countries:** set `REGION_CODE` to the ISO code (e.g. `NGA` for Nigeria, `USA` for United States) and `TIME_ZONE` to the school’s IANA zone (e.g. `Africa/Lagos`, `America/New_York`). Ensure the corresponding region exists in **Region config** (admin or seed) so currency and grading scale apply correctly.

---

## Environment Variables for Cameroon

Add to `.env.local`:

```bash
# Region & locale (Buea/Cameroon - RECOMMENDED for this guide)
REGION_CODE=CMR
TIME_ZONE=Africa/Douala

# Email (Gmail - FREE)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-school@gmail.com
EMAIL_HOST_PASSWORD=your-gmail-app-password

# Payments - Leave empty to use manual entry (FREE)
# Add these only when you get API keys from MTN/Orange Cameroon
MTN_MOMO_API_KEY=
MTN_MOMO_API_SECRET=
ORANGE_MONEY_API_KEY=
ORANGE_MONEY_API_SECRET=

# Database (SQLite for dev, or PostgreSQL free tier)
DATABASE_URL=  # Leave empty for SQLite, or use Supabase free tier

# AI Copilot (Optional - self-hosted Ollama; see docs/OLLAMA_OPERATIONS_AND_UPDATES.md)
OLLAMA_ENDPOINT=http://localhost:11434/api/generate
OLLAMA_MODEL=llama3

# Everything else can be left empty - platform works without them!
```

---

## Contact Information for Cameroon

### **MTN Mobile Money Business Services:**
- **Website:** https://mtn.cm (Business section)
- **Office:** MTN Cameroon offices in Buea or Douala
- **What to ask:** "I need a merchant account for MTN Mobile Money API integration"

### **Orange Money Business Services:**
- **Website:** https://orange.cm (Business section)
- **Office:** Orange Cameroon offices in Buea or Douala
- **What to ask:** "I need a merchant account for Orange Money API integration"

---

## Bottom Line

✅ **You can run this platform for $0/month**
✅ **MTN MoMo and Orange Money are already built-in** (just need API keys)
❌ **Stripe does NOT work with mobile money** (use built-in processors instead)
✅ **Manual payment entry works perfectly** (no API needed)
✅ **Everything has a free alternative**

**Start free, add APIs only when you need automation!**

---

## Buea/SMS Guideline Checklist

For schools in Buea and the Southwest region, the platform has been audited against local challenges (unstable internet, power cuts, overcrowded classes, manual admission, security). See the full mapping in **[BUEA_SMS_GUIDELINE_AUDIT.md](BUEA_SMS_GUIDELINE_AUDIT.md)**.

| Challenge | Addressed in this platform |
|-----------|----------------------------|
| **Unstable internet** | Service Worker (PWA) + offline sync for marks; sync API for mobile. Enable "Offline Mode" in Feature Control. |
| **Power cuts** | Theme/layout saved in browser; optional draft recovery for long forms. Use PWA on phones/tablets. |
| **Large classes / bulk data** | Bulk attendance API; bulk grade CSV import; bulk student/guardian import; bulk letters; bulk finance access. |
| **Manual admission / ghost students** | Online student onboarding wizard (`/portal/student/onboarding/`); admission number validation and duplicate check; guardian invite/claim. |
| **Fee tracking / Mobile Money** | MTN MoMo & Orange Money (manual or API); payment codes; reminders with bank/MoMo instructions. |
| **Unauthorized grade edits** | Role-based access; grade approval workflow; server-side validation; audit logs (GradeAudit, AuditLog). |
| **Config portability** | All settings via environment variables (no hardcoded credentials). See `.env.example`. |

To confirm everything is enabled for your site: turn on **Offline Mode** in Feature Control if teachers use tablets in low-connectivity areas; configure **payment instructions** (bank/MoMo numbers) in Site Settings so fee reminders include them.
