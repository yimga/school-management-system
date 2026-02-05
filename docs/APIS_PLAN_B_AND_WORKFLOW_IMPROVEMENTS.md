# Payment APIs as Must-Have, Other Critical APIs + Plan B, Redis/Celery Deploy, and Workflow Ease-of-Use

**Purpose:** (1) Treat payment APIs as must-have; list other critical APIs and a Plan B for each. (2) How to add Redis and Celery and what to do when you merge to main and deploy. (3) Beyond information tags—other ways to improve workflow and ease of use.

---

## Part 1: Payment APIs = Must-Have; Other Critical APIs and Plan B

### 1.1 Payment APIs (Must-Have)

- **Why must-have:** Fee collection is core; parents pay via mobile money or bank; automation reduces manual recording and errors.
- **What you have:** Webhook endpoint (CSRF-exempt, signature-checked), manual recording as fallback, `PaymentIntegration` model for provider config (MTN MoMo, Orange Money, etc.).
- **Plan B (when provider is down or not configured):**
  - **Manual recording:** Staff create invoice → give parent payment instructions (reference, amount) → parent pays offline → staff record payment in Finance (amount, method, reference). No API call required.
  - **Graceful degradation:** If webhook fails (timeout, 5xx), provider usually retries. You already have idempotency (WebhookLog) to avoid duplicate payments. Log failures and alert; staff can record manually if needed.
- **Action:** Keep payment APIs as must-have for production; document “manual recording” as official Plan B and train staff on it.

### 1.2 Other Critical APIs and Plan B

| API / Service | Why important | Plan B |
|---------------|----------------|--------|
| **Email (SMTP / transactional)** | Password reset, access grants, reminders, receipts. Without it, users can’t recover accounts or get key notifications. | **No real Plan B for password reset.** You must have at least one working email backend in prod. For reminders: if email fails, create **in-app notification** only (user sees it on next login). Optionally log to admin “notification delivery failed” for follow-up. |
| **SMS (Twilio / AfricasTalking)** | Reminders, alerts in regions where email is less used. | **Plan B:** Send same content by **email + in-app notification**. If SMS provider is not configured or send fails, skip SMS and use email + in-app only. No dependency on SMS for core flows. |
| **Payment provider (MoMo, etc.)** | Automated payment confirmation and ledger updates. | **Plan B:** Manual payment recording by staff (already in app). Rely on provider retries for webhooks; if persistent failure, staff records from provider’s dashboard or bank statement. |
| **Database (Postgres)** | All data. | **Plan B:** Backups (scheduled pg_dump or managed backups). Replication/read replicas for scale later. No “alternative” to DB. |
| **Redis** | Cache, sessions, Celery broker. | **Plan B:** For **cache:** fall back to LocMemCache (per-worker, not shared). For **sessions:** keep DB-backed sessions if Redis is down. For **Celery:** if Redis is down, tasks queue up and run when Redis is back, or run tasks synchronously in a “maintenance mode” (not ideal at scale). So Redis is “should-have” with a degraded fallback. |

**Summary:**  
- **Must-have:** Payment APIs (with manual recording as Plan B), Email (no Plan B; required).  
- **Very important:** SMS (Plan B = email + in-app), Redis (Plan B = in-memory cache + DB sessions; Celery can queue until Redis is back).  
- **Plan B overall:** Prefer “degrade gracefully” (e.g. skip SMS, use email + in-app; use manual payment if webhook fails) and document + train staff on manual fallbacks.

---

## Part 2: Redis and Celery—Having It and Deploy When You Merge to Main

### 2.1 What “Having It” Means

- **Redis:** Used for (1) Django cache backend, (2) optional session store, (3) Celery broker.
- **Celery:** Used for (1) sending reminder emails/SMS (deadline, fee), (2) report generation, (3) any heavy or slow work you move off the web process.

### 2.2 Implementation Steps (So You Can Merge and Deploy)

**Step 1: Add dependencies**

In `requirements.txt` add:

```
redis>=5.0.0
celery>=5.3.0
django-celery-results>=2.5.0
django-celery-beat>=2.5.0
django-redis>=5.4.0
```

(Adjust versions to what you prefer; these are typical.)

**Step 2: Django settings**

- **Cache:** You already switch to Redis when `REDIS_URL` is set. Ensure `REDIS_URL` is used for cache `LOCATION` (you have this).
- **Sessions (optional):**  
  - If you want Redis-backed sessions when Redis is available:
    - `SESSION_ENGINE = "django.contrib.sessions.backends.cache"`  
    - `SESSION_CACHE_ALIAS = "default"`  
  - Only after `CACHES["default"]` is Redis (when `REDIS_URL` is set).
- **Celery:**  
  - In `config/settings.py` add:
    - `CELERY_BROKER_URL = os.getenv("REDIS_URL", "")`
    - `CELERY_RESULT_BACKEND = "django-db"` (or `redis` if you prefer; django-db is simpler and uses Postgres you already have)
    - `CELERY_ACCEPT_CONTENT = ["json"]`
    - `CELERY_TASK_SERIALIZER = "json"`
  - Create `config/celery.py` that loads Django and sets the Celery app; in `config/__init__.py` import it so Celery is loaded on Django startup.
  - Create a few tasks (e.g. in `apps/analytics/tasks.py` or `apps/evals/tasks.py`): e.g. `send_deadline_reminder`, `send_finance_reminder`, `generate_report_pdf`. Move the current “send reminder” logic into these tasks; in views/cron call `task.delay(...)` instead of doing the work in the request.
  - Optional: use **django-celery-beat** for scheduled tasks (e.g. “every day at 8am send deadline reminders”). Configure in Django admin or in settings.

**Step 3: Merge to main**

- Commit the above: `requirements.txt`, settings changes, `config/celery.py`, `config/__init__.py`, new task modules, and any view changes that call `task.delay()`.
- Merge to main as usual (PR, review, merge).

**Step 4: Deploy (after merge to main)**

On the **production server** (or your host’s config):

1. **Environment variables**
   - `REDIS_URL` = your Redis connection string (e.g. `redis://localhost:6379/0` or the host’s Redis URL).
   - Keep existing: `DATABASE_URL`, `SECRET_KEY`, `ALLOWED_HOSTS`, etc.

2. **Redis**
   - Ensure Redis is running (e.g. `redis-server` or managed Redis from your host). If using a managed service (e.g. Redis Cloud, Railway Redis), set `REDIS_URL` to their URL.

3. **Install dependencies**
   - Same as any deploy: e.g. `pip install -r requirements.txt` (or your image/build step).

4. **Run Celery worker**
   - You must run at least one Celery worker process so queued tasks run. Example:
     - `celery -A config worker -l info`
   - Run it as a separate process (systemd service, supervisor, or your host’s “worker” process type). It must stay running like the web server.

5. **Run Celery beat (if you use scheduled tasks)**
   - If you use django-celery-beat for cron-like tasks:
     - `celery -A config beat -l info`
   - Or run a single process that does both: `celery -A config worker -B -l info` (worker + beat in one). Run as a separate process from the web app.

6. **Migrations**
   - `python manage.py migrate` (django-celery-results and django-celery-beat add tables).

7. **Health**
   - Web app health endpoint (e.g. `/healthz/`) can stay as-is. Optionally add a check that Redis is reachable (e.g. `cache.set("health", 1, 10)` and `cache.get("health")`) and that Celery can connect (e.g. send a no-op task and wait for result with timeout). Start simple: just ensure Redis and worker are running.

**Summary:**  
- **Merge:** Add Redis/Celery code and dependencies to the repo; merge to main.  
- **Deploy:** Set `REDIS_URL`, run Redis, run `celery -A config worker` (and optionally beat), run migrations. No change to how you “merge to main”—only to what runs in production (web + Redis + Celery worker).

---

## Part 3: Beyond Information Tags—Other Ways to Improve Workflow and Ease of Use

Besides **information tags** (tooltips, inline help, section descriptions), you can improve workflows and ease of use in these ways:

### 3.1 Onboarding and First-Time Hints

- **Short “first time” tips:** On first login (or first visit to a key page), show a dismissible card: e.g. “Here you can link your child using the invite code from the school” (parent); “Submit marks here; they go for approval before report cards” (teacher). Store “dismissed” in user preference or session so you don’t show again.
- **Progress indicators:** For multi-step flows (e.g. claim invite → link child → view dashboard), show steps 1–2–3 and “You are here” so users know how far they are and what’s next.
- **Empty states:** When a list is empty (e.g. no linked children, no invoices), show a clear message and one primary action: “No children linked yet. Add one using your invite code.” with a button to the right page.

### 3.2 Defaults and Shortcuts

- **Sensible defaults:** Pre-fill forms where possible (e.g. current term, current academic year, “Pending” for new request). Reduces clicks and errors.
- **“Last used” or “Suggested”:** e.g. “Last payment method: MTN MoMo”; “Suggested deadline: end of term.” Helps repeat actions.
- **Quick actions:** On dashboard cards, one primary button (e.g. “View fees”, “Submit marks”, “Request access”) so the next step is obvious.
- **Keyboard / shortcuts (optional):** For power users (staff/admin), add a few shortcuts (e.g. “Go to dashboard”, “Search”) and a small “?” or “Shortcuts” link that lists them.

### 3.3 Clear Feedback and Errors

- **Success messages:** After a critical action (invite claimed, payment recorded, grades submitted), show a clear success message at the top and, if useful, a “What’s next” (e.g. “You can now view fees in Finance.”).
- **Error messages in plain language:** Instead of “Invalid input”, show “Please enter the 6-digit invite code from the school email/SMS.” Use `form.errors` and field-specific messages.
- **Validation on blur:** Where helpful, validate fields on blur (e.g. invite code format) so users fix before submit. Don’t overdo it; use for important fields.

### 3.4 Navigation and Finding Things

- **Breadcrumbs:** You have breadcrumbs; keep them consistent so users always know “where I am” (e.g. Dashboard > Finance > Invoices).
- **Global search:** If you have search (e.g. students, invoices), make it easy to reach (e.g. in header) and show recent or suggested results. Helps staff find records fast.
- **Dashboard “sections” and titles:** Clear section titles (e.g. “Fees and payments”, “Your children”, “Deadlines”) so parents and teachers know what each block is for. You’ve improved this with high-contrast and polish; keep titles consistent.

### 3.5 Reducing Friction in Critical Flows

- **Fewer steps:** Combine steps where possible (e.g. “Request finance access” in one screen with reason, instead of multiple pages). Pre-fill what you know (user, children).
- **Save drafts (where it makes sense):** For long forms (e.g. bulk grade entry), allow “Save draft” so users don’t lose work. Optional.
- **Confirmation only when destructive:** Use “Are you sure?” only for irreversible actions (e.g. delete, final submit). For normal submit, a success message is enough.

### 3.6 Role-Based “Landing” and Menus

- **Post-login landing:** You already route by role (parent → parent dashboard, teacher → teacher dashboard, staff → backend). Keep it; optionally let users set a “default start page” (e.g. Finance, Workflow) in preferences so frequent users land where they need.
- **Sidebar/menu:** Show only items the user can access. You have role-based menus; keep them short and grouped (e.g. “Finance”, “Academic”, “Settings”) so names are predictable.

### 3.7 Mobile and Small Screens

- **Responsive tables and forms:** You have mobile-friendly CSS; ensure key flows (claim invite, request access, view fees, submit marks) work on phone (stacked forms, tap-friendly buttons, no horizontal scroll for critical content).
- **Primary action visible:** On mobile, put the main button (e.g. “Request access”, “Submit”) fixed or clearly visible so users don’t have to scroll to find it.

### 3.8 Summary: Workflow Improvements Beyond Tags

| Area | Idea | Example |
|------|------|--------|
| Onboarding | First-time hints, progress steps, empty states | “Link your child with the invite code” card on first parent login. |
| Defaults & shortcuts | Sensible defaults, quick actions, optional shortcuts | Default “Pending” on new request; “View fees” button on dashboard. |
| Feedback | Success message + “What’s next”; plain-language errors | “Payment recorded. Receipt sent by email.” |
| Navigation | Breadcrumbs, search, clear section titles | Dashboard > Finance > Invoices; header search. |
| Friction | Fewer steps, save draft, confirm only when destructive | Single “Request finance access” screen; no confirm on normal submit. |
| Role-based | Default start page, minimal sidebar | Preference: “Start in Finance”. |
| Mobile | Responsive critical flows, primary action visible | Stacked form on phone; “Submit” always in view. |

You can phase these: start with **information tags** and **clear success/error messages** and **empty states**, then add **first-time hints** and **defaults/quick actions**, then **onboarding steps** and **shortcuts** if you want.

---

## Part 4: Quick Reference

- **Payment APIs:** Must-have; Plan B = manual recording + provider retries; document and train staff.
- **Other critical:** Email = must (no Plan B); SMS = Plan B email + in-app; Redis = Plan B in-memory cache + DB sessions.
- **Redis + Celery:** Add deps, settings, `config/celery.py`, tasks; merge to main. Deploy: set `REDIS_URL`, run Redis, run `celery -A config worker` (and beat if needed), migrate.
- **Workflow beyond tags:** First-time hints, progress/empty states, defaults and quick actions, clear success/errors, breadcrumbs and search, fewer steps, role-based landing and menus, mobile-friendly critical flows.
