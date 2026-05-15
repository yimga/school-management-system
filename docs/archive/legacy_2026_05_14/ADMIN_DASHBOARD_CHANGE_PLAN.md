# Plan to Change the /admin Dashboard

Focused plan for changing the admin dashboard shown at **/admin/** (and **/admin/dashboard/**).  
**Template:** `templates/admin/admin_dashboard.html`  
**View:** `config/admin.py` → `GileadAdminSite.index()`

---

## How this ties in with the sidebar

- **Dashboard plan (this doc)** = the **main content** of the /admin page (KPIs, layout, quick actions, data). You keep the dashboard **look** you like.
- **Sidebar restructure** = the **left-hand navigation** (apps, models, grouping, order, extra links). That is a **separate** change.

See **`docs/ADMIN_SIDEBAR_RESTRUCTURE_PLAN.md`** for:
- How sidebar restructure fits with this plan (dashboard = content; sidebar = nav).
- Current sidebar structure (data, template, JS, CSS).
- Options for restructure (categories vs flat, order, layout, extra items).
- Phased implementation (data → template → CSS/JS → RBAC/docs).

You can do **sidebar restructure first** (new plan) and **dashboard content changes** (this plan) in parallel or after; they touch different files.

---

## 1. Current state (what you have)

| Area | What’s there |
|------|----------------|
| **Header** | Logo, “Administration Dashboard” title, subtitle, theme toggle (Dark/Light). |
| **Preview card** | Shown when SiteSettings has preview; toggle preview, clear, open customizer; primary/accent chips. |
| **KPI cards** | Total Users (with Admins/Students/Teachers breakdown), Database & App Stats (connection, health, storage, tables, last backup), System Health (100%, status, uptime). All use design tokens and BEM (e.g. `.admin-stat`, `.admin-stat--success`). |
| **Active users / Security** | Sample user cards (Admin, Teacher, Parent) with “End Session” buttons; Security/Compliance 24h (alerts, denials); failed logins by role; sessions summary. |
| **Calendar** | Month navigation, grid, “Today” date, weather widget, daily quote. |
| **Quick links** | Manage Users, All Models, API Health, Site Config, **Backend Console** (CTA). |
| **System info table** | Django/Python/DB/theme versions, server time. |
| **Data** | Real: `total_users`, `admin_count`, `student_count`, `teacher_count`, `active_sessions`, `sessions_24h`, `security_alerts_24h`, `access_denials_24h`, `failed_logins_by_role`, `finance_inbox_*`, `preview_data`. Permission-gated (RBAC). Placeholder/sample: user cards, some DB stats (e.g. “~450 MB”, “28 tables”). |

---

## 2. Goals (what “change” can mean)

- **Content:** More real data, fewer placeholders; add/remove sections.
- **Layout:** Reorder or resize sections; grid vs list; sidebar vs single column.
- **UX:** Quick actions, better navigation, clearer hierarchy.
- **Look:** Align with design system; optional new “skin” (e.g. compact, card-heavy).
- **Performance:** Lazy-load non-critical bits; keep first paint fast.

---

## 3. Phased plan to change the dashboard

### Phase A: Clarify and wire data (1–2 days)

**Goal:** Every number and label on the dashboard is either real or explicitly “sample”.

| Step | Task | Where | Deliverable |
|------|------|--------|-------------|
| A.1 | List all current placeholders | `admin_dashboard.html`, `config/admin.py` | Short list: e.g. “~450 MB”, “28”, “24/7”, sample user cards. |
| A.2 | Replace or label placeholders | View + template | Either wire real values (e.g. storage from DB or env) or show “Sample” / hide section when no data. |
| A.3 | Optional: Add 1–2 KPIs from your domain | `config/admin.py` index(), template | e.g. “Pending approvals”, “Overdue invoices” (with permission check). |
| A.4 | Document which context vars are required | `docs/ADMIN_UI.md` or this doc | So future changes don’t break the dashboard. |

**Outcome:** Dashboard is trustworthy; no confusion between real and sample data.

---

### Phase B: Layout and structure (2–3 days)

**Goal:** Layout matches how you want to use the dashboard (e.g. KPIs first, then actions, then detail).

| Step | Task | Where | Deliverable |
|------|------|--------|-------------|
| B.1 | Define sections and order | — | e.g. 1) Alerts/Preview 2) KPIs 3) Quick actions 4) Active users / Security 5) Calendar 6) System info. |
| B.2 | Implement section order and optional IDs | `admin_dashboard.html` | Sections in desired order; add `id` or `data-section` for deep-links or JS. |
| B.3 | Make layout responsive (if not already) | `admin_dashboard.html`, `admin-dashboard.css`, `dashboard-responsive.css` | Grid that stacks on small screens; no horizontal scroll; touch-friendly. |
| B.4 | Optional: Two-column layout (e.g. KPIs left, calendar + links right) | HTML + CSS | Clear breakpoint (e.g. 992px); same content, different arrangement. |

**Outcome:** Predictable, responsive layout; easy to add/remove sections later.

---

### Phase C: Quick actions and navigation (1–2 days)

**Goal:** One place for “do this next” and “go there”.

| Step | Task | Where | Deliverable |
|------|------|--------|-------------|
| C.1 | Add a “Quick actions” strip | `admin_dashboard.html`, view | 3–5 buttons (e.g. Add user, Add student, Site settings, Backend console). |
| C.2 | Permission-check each action | `config/admin.py` (context) or template | Use `user.has_perm` / `user.is_superuser`; hide or disable if no access. |
| C.3 | Optional: “Back to list” or “Back to dashboard” on other admin pages | `base_site.html` or breadcrumb partial | Single, consistent back link. |
| C.4 | Optional: Shortcuts (e.g. “/admin/” in nav) | `base_site.html`, sidebar | Obvious way back to dashboard from list/change views. |

**Outcome:** Less clicking to reach common tasks; actions respect RBAC.

---

### Phase D: Visual refresh (1–2 days)

**Goal:** Dashboard looks consistent with the rest of admin and design system.

| Step | Task | Where | Deliverable |
|------|------|--------|-------------|
| D.1 | Move any remaining inline styles to CSS | `admin_dashboard.html` | Use classes from `admin-dashboard.css` / `admin_theme.css`; no `style=` for colors/spacing. |
| D.2 | Use design tokens for all surfaces and text | `admin_dashboard.html`, CSS | `--color-bg-light`, `--color-text-primary`, `--color-border`, etc.; support dark/light from existing theme. |
| D.3 | Optional: Card style (e.g. shadow, radius) from design system | `admin-dashboard.css` | Reuse `--shadow-md`, `--radius-lg` for KPI and user cards. |
| D.4 | Optional: “Compact” mode (smaller padding, smaller type) | CSS class + toggle or user pref | Class `.dashboard--compact`; toggle in header or via SiteSettings/DashboardUserPreference. |

**Outcome:** One visual language; theme and compact options if desired.

---

### Phase E: Optional extras (as needed)

| Step | Task | Where | Deliverable |
|------|------|--------|-------------|
| E.1 | Recent activity (last 5–10 edited objects) | New query in view, template partial | Permission-filtered; link to each object’s change page. |
| E.2 | Lazy-load calendar/weather | `admin_dashboard.html`, JS | Load calendar/weather after first paint or on expand. |
| E.3 | Dashboard widget order (user preference) | Model or cookie, JS | User can reorder sections; state saved per user. |
| E.4 | Replace sample user cards with real “active sessions” | View: real sessions + user info; template | List real logged-in users (with permission); “End session” only if you implement the action. |

**Outcome:** Richer dashboard without blocking initial load.

---

## 4. Suggested order

1. **Phase A** – Data clarity (quick; high trust).
2. **Phase B** – Layout (foundation for everything else).
3. **Phase C** – Quick actions (high impact for daily use).
4. **Phase D** – Visual refresh (polish).
5. **Phase E** – Pick only what you need.

---

## 5. Key files

| Purpose | File |
|--------|------|
| Dashboard view and context | `config/admin.py` → `GileadAdminSite.index()` |
| Dashboard template | `templates/admin/admin_dashboard.html` |
| Dashboard-specific CSS | `static/css/admin-dashboard.css` |
| Responsive / shared layout | `static/css/dashboard-responsive.css` |
| Design tokens | `static/css/design-tokens.css`, `static/css/design-system-unified.css` |
| Base admin shell | `templates/admin/base_site.html` |
| RBAC / permissions | Same view; `can_see_user_stats`, `can_see_sessions`, etc. |

---

## 6. Checklist before you start

- [ ] Decide which dashboard is canonical: only `admin_dashboard.html` at /admin/, or also use/retire `templates/admin/index.html` (app-cards layout).
- [ ] Confirm URL: /admin/ and /admin/dashboard/ both show this dashboard (current setup).
- [ ] Back up or branch before big layout changes.
- [ ] Test as non-superuser so RBAC and permission-gated KPIs still behave.

---

## 7. Success criteria

- **Data:** No misleading placeholders; new KPIs are permission-checked.
- **Layout:** Sections in a clear order; responsive; optional two-column.
- **Actions:** Quick actions strip with correct permissions.
- **Visual:** Tokens and classes only; no inline theme-dependent styles.
- **Docs:** This plan and `ADMIN_UI.md` updated after changes.

Use this as the working plan to change the /admin dashboard; do Phase A first, then B → C → D, and add E items only if needed.
