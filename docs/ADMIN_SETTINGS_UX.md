# Admin & Settings UX (Phase 6)

## Logical buckets (Phase 6.1)

Site Settings are grouped into five buckets so non-technical admins can find configurations quickly:

| Bucket | Contents |
|--------|----------|
| **Academics** | Reports (publish & grades), Analytics Defaults (pass mark, deadlines, top students). |
| **Finance** | Finance Automation (invoices, reminders, receipt verification, payment instructions). |
| **System** | Feature toggles, Portal & content, Backend orchestration & limits, Compliance & payroll, Automation, Metadata. |
| **Branding & experience** | At a glance, Branding, Preview & draft, Company details, Login/header/layout, Theme & experience, Footer. |
| **Notifications** | Notifications & analytics (guardian notifications, parent welcome email). |

Use **Search** at the top of Site Settings to jump to a section by keyword (e.g. "invoice", "theme", "finance").

## User permissions / RBAC discoverability (Phase 6.2)

- **From the admin dashboard:** Use the **User permissions** link in the header to open the Users list. Use **Site Settings** → **System** → **Backend Orchestration & Limits** for "User permissions (who can do what)" with links to Users and Groups.
- **Who can do what:** Manage users and roles via **Configuration** → **Accounts** → **Users** and **Authentication** → **Groups**. Backend Orchestration controls which roles can use Entity Console, Import, and API schema.

## Consistency (Phase 6.5)

- Site Settings use clear section headings, grouped fields, and inline tooltips for high-impact toggles (Phase 6.4).
- For other admin list/detail pages: use clear headings, group related fields, and add help text or tooltips where options are non-obvious so the whole admin feels intuitive.
