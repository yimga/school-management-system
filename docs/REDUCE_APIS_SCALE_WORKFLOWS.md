# Reduce API Dependency, Scale in Prod, and Improve Workflows

**Purpose:** (1) Minimize reliance on external APIs; (2) implement scale/readiness with Postgres in prod; (3) improve workflows and add information tags (help/tooltips) where they matter.

---

## Part 1: Reducing Dependence on External APIs

### 1.1 Strategy: Prefer Built‑In or Optional External Services

| Area | Current dependency | Remedy (reduce or remove) |
|------|---------------------|---------------------------|
| **Email** | SMTP or SendGrid/Mailgun | **Keep one channel.** Use Django’s built-in SMTP (any provider: Gmail, your host’s SMTP, or a single transactional API). No need for multiple email APIs. In dev, `EMAIL_BACKEND = console` logs to console; in prod, set one `EMAIL_HOST` + credentials. |
| **SMS** | Twilio / AfricasTalking | **Make SMS optional.** Use **in-app notifications + email** as the default. Send SMS only when (a) user has opted in and (b) SMS provider is configured. If no SMS config, skip SMS and use email + dashboard notifications only. No “dependency” on SMS for core flows. |
| **Payments** | MTN MoMo, Orange Money, etc. | **Support “manual recording” as first-class.** Parents can pay offline; staff record payment in Finance. Payment provider webhooks are **optional** for automation. Go live without any payment API; add one provider later when needed. |
| **Weather** | Open-Meteo | **Optional widget.** If you don’t want the dependency, hide or remove the admin weather widget. No impact on core features. |
| **GeoIP** | MaxMind GeoLite2 | **Optional.** Use only for “nice to have” (e.g. country in audit). If you disable or remove it, compliance still works; you just don’t get country. |
| **AI Copilot** | LLM API | **Feature flag.** Already gated; if key is not set, feature is off. No dependency when disabled. |

### 1.2 Concrete Changes to “Not Depend on a Lot of APIs”

1. **Email only for critical path**  
   - Password reset, key notifications (e.g. finance access granted), and optional reminder emails use **one** SMTP backend.  
   - No need for a second “marketing” or “transactional” API unless you later want it.

2. **SMS optional and fallback to email**  
   - In code paths that send SMS (reminders, alerts):  
     - If SMS provider is not configured or send fails → **send same content by email** (and/or create an in-app notification).  
   - Document: “SMS is optional; email and in-app notifications are the default.”

3. **Payment: manual first, provider later**  
   - Finance: staff can create invoices and **record payments manually** (amount, method, reference).  
   - No payment API required for go-live.  
   - When you add a provider (e.g. MoMo), keep manual recording so you never “depend” on the API for core operation.

4. **Remove or hide optional widgets**  
   - Admin dashboard weather: hide via feature flag or template condition if you don’t want Open-Meteo.  
   - Same idea for any other non-critical external call.

5. **Central “notification channel” in settings**  
   - Site settings: “Notification delivery” = **Email only** | **Email + SMS (if configured)**.  
   - If “Email only”, all reminder/alert code paths use email + in-app only; SMS is never called.

**Result:** You can run production with **one SMTP config** and **no** SMS, **no** payment provider, **no** weather, **no** AI. Add APIs only when you choose to.

---

## Part 2: Scale and Readiness (You Have Postgres in Prod)

### 2.1 Already in Place

- **PostgreSQL** in prod (you confirmed).  
- **`CONN_MAX_AGE = 600`** in settings (connection reuse).  
- **WhiteNoise** for static files.  
- **Security:** HTTPS, secure cookies, CSRF, webhook signature checks where used.

### 2.2 What to Implement Next (in order)

**Step 1: Redis for cache (and optionally sessions)**

- **Why:** Reduces DB load for repeated reads (e.g. site settings, dashboard data, rate limits). At 40k–100k users, in-memory cache is not shared across workers.
- **How:**  
  - In prod, set `REDIS_URL` (e.g. `redis://localhost:6379/0` or your host’s Redis URL).  
  - Add `django-redis` to `requirements.txt` if not present; settings already switch to Redis when `REDIS_URL` is set.  
  - Optional but recommended: use Redis for sessions so multiple app instances share session store:
    - `SESSION_ENGINE = "django.contrib.sessions.backends.cache"`  
    - `SESSION_CACHE_ALIAS = "default"`  
    - (with `default` backed by Redis).
- **Check:** After deploy, run a few requests and confirm cache is used (e.g. logs or Redis CLI).

**Step 2: Background tasks (Celery + Redis)**

- **Why:** Reminders (deadline, fee), report generation, and bulk operations should not run in the request. Prevents timeouts and keeps the app responsive.
- **How:**  
  - Install: `celery`, `django-celery-results` (or `django-celery-beat` if you want cron-like tasks).  
  - Add a `celery.py` in config and wire it to Django settings.  
  - Use Redis as broker: `CELERY_BROKER_URL = os.getenv("REDIS_URL")`.  
  - Move “send reminder” (email/SMS) and “generate report” into Celery tasks; call them with `task.delay()` from views.  
  - Run a Celery worker (and optionally beat) on the same host or a separate worker host.
- **Scope:** Start with 2–3 tasks: e.g. `send_deadline_reminder`, `send_finance_reminder`, `generate_report_pdf`. Expand later.

**Step 3: Media files (object storage) – when needed**

- **Why:** At scale, local `media/` on the app server is a single point of failure and doesn’t scale across instances.
- **How:** When you outgrow local disk, use `django-storages` with S3 (or R2, etc.). Set `DEFAULT_FILE_STORAGE` and bucket env vars; keep static on WhiteNoise or CDN.
- **When:** Can be Phase 2 after Redis + Celery if you already have enough disk and a single instance.

**Step 4: Production checklist (with Postgres)**

- `DEBUG=0`, `SECRET_KEY` set, `ALLOWED_HOSTS` set.  
- `DATABASE_URL` → Postgres.  
- `REDIS_URL` set and cache (and optionally sessions) using Redis.  
- One SMTP backend configured (`EMAIL_HOST`, etc.).  
- Celery worker (and beat if using scheduled tasks) running.  
- `manage.py check --deploy` clean; migrations applied; `collectstatic` run.  
- Health checks: `/healthz/` or `/api/health/` for load balancer.

**Summary (scale):** With Postgres already in prod, add **Redis** (cache + optional sessions), then **Celery + Redis** for background work. Add object storage when you need to scale media. That covers “scale and readiness” without depending on many external APIs.

---

## Part 3: Workflow Improvements and Information Tags

### 3.1 What “Information Tags” Means Here

- **Tooltips:** Short hint on hover/focus (e.g. “?” icon next to a label).  
- **Inline help:** One line below a field or section (“e.g. Enter the invoice reference from the bank.”).  
- **Section descriptions:** Short text above a card/section (“Use this to request access to your child’s fee information.”).  
- **First-time or contextual hints:** Optional “Got it” dismissible tip for key screens (e.g. parent dashboard, finance request).

All of these are “information tags” in the sense of **extra, contextual information** so users know what to do and why.

### 3.2 Where to Add Them (and How to Decide)

**Rule of thumb:** Add help where (a) the action is **critical** (e.g. claim invite, request finance access, submit grades), (b) support gets **repeated questions**, or (c) the field is **ambiguous** (e.g. “Reference”, “Payment code”).

**By role:**

| Role | Where tags help | Example |
|------|------------------|--------|
| **Parent** | Claim invite page, link-child step, “Request finance access”, dashboard sections (Fees, Performance), contact form. | “Paste the invite code from the email/SMS from the school.” “Request access to view and pay fees for your linked children.” |
| **Teacher** | Marks entry, submit-for-approval, deadlines list, attendance. | “Marks are sent for approval before they appear on report cards.” “This is the deadline for submitting grades for this subject.” |
| **Staff (Finance)** | Create invoice, record payment (manual), webhook config (if used). | “You can record payments manually if the parent paid by bank or mobile money.” |
| **Admin** | Feature flags, RBAC, site config, dashboard layout. | “When enabled, parents can request access to the finance module from their dashboard.” |

**How to know where they’re needed:**

1. **Critical path review:** List the 5–10 flows that must work for the school (e.g. parent claim invite → link child → view dashboard; teacher enter marks → submit → approval; staff create invoice → record payment). Add one short sentence of help at the **entry point** of each flow (page or first field).  
2. **Support tickets:** If you get repeated “how do I…?” for a screen, add a tooltip or one-line help there.  
3. **Ambiguous labels:** Any label that could mean two things (e.g. “Reference”, “Code”, “Status”) gets a tooltip or placeholder.  
4. **Optional:** Short “How this works” link that opens a modal or help page for that section.

**Where *not* to add tags:**

- Obvious actions (“Save”, “Cancel”, “Log out”).  
- Every single field (only where it reduces confusion or support load).  
- Long paragraphs (keep to one short sentence or bullet list).

### 3.3 Implementation Approach

1. **Bootstrap tooltips (you already have Bootstrap):**  
   - Add a small `?` or `i` icon next to the label; `data-bs-toggle="tooltip"` and `title="…"`.  
   - Use for short hints (one sentence).

2. **Inline help in forms:**  
   - Use `help_text` on Django form fields; render in the template as `<p class="form-text text-muted">…</p>` (or your design system’s helper class).  
   - Use for “what to enter” or “where to find this value”.

3. **Section descriptions:**  
   - Above the card or section: `<p class="text-muted small mb-2">…</p>`.  
   - Use for “what this section is for” (e.g. parent finance, teacher deadlines).

4. **Accessibility:**  
   - Associate help with the field: `aria-describedby="id_of_help_text"` on the input, `id` on the help element.  
   - For icon-only tooltips, add `aria-label="Explanation: …"` or visible “More info” text for screen readers.

5. **Optional: “Help” or “?” in navbar/header:**  
   - Link to a simple “Help” page that lists: Claim invite, Link child, Request finance access, Submit grades, etc.  
   - Reduces need for tags on every screen if users know where to look.

**Priority order for tags:**

1. Parent: claim invite, link child, “Request finance access”, dashboard section titles.  
2. Teacher: marks entry (submit for approval), deadlines.  
3. Staff: manual record payment, create invoice.  
4. Admin: feature flags that affect parents/teachers (e.g. finance access, invite flow).

---

## Part 4: Summary Checklist

**Reduce API dependency**

- [ ] Use one SMTP backend; no requirement for multiple email APIs.  
- [ ] Make SMS optional; fallback to email + in-app notifications when SMS not configured or fails.  
- [ ] Treat payment providers as optional; manual payment recording is first-class.  
- [ ] Hide or remove optional widgets (e.g. weather) if you don’t want their API.  
- [ ] Add site setting: “Notifications: Email only” vs “Email + SMS (if configured)”.

**Scale and readiness (prod has Postgres)**

- [ ] Set `REDIS_URL` in prod; confirm cache (and optionally sessions) use Redis.  
- [ ] Add `django-redis` to requirements if using Redis.  
- [ ] Introduce Celery + Redis; move reminder and report tasks to Celery.  
- [ ] Run Celery worker (and beat if needed) in prod.  
- [ ] When needed, add object storage for media (e.g. django-storages + S3/R2).  
- [ ] Run production checklist: DEBUG, SECRET_KEY, ALLOWED_HOSTS, health checks, `check --deploy`.

**Workflows and information tags**

- [ ] Add tooltips or inline help on critical-path entry points (claim invite, link child, request finance, submit grades, record payment).  
- [ ] Add section descriptions for parent dashboard (Fees, Performance) and teacher dashboard (Deadlines, Marks).  
- [ ] Use support tickets and “ambiguous label” review to add tags where questions repeat.  
- [ ] Prefer one short sentence per tag; use `aria-describedby` / `aria-label` for accessibility.  
- [ ] Optional: add a “Help” page linked from header listing main flows.

This gives you: **fewer external API dependencies**, **concrete scale steps with Postgres already in prod**, and **a clear way to improve workflows and decide where information tags are needed**.
