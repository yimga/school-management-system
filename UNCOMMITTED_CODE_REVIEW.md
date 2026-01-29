# Uncommitted Code Review — Branch `backend_vs_frontend`

Review of **modified** (staged/unstaged) and **untracked** files. One bug was fixed.

---

## Summary

- **32 modified files** — ~2,267 insertions, ~1,237 deletions  
- **Many untracked files** — docs, migrations, new app code, templates  
- **One fix applied:** `organized_sidebar` and `sidebar_categories` were passed to the backend dashboard template but never defined in the view (would cause `NameError`). The view now imports and uses `sidebar_organizer` to set them.

---

## Modified Files — What’s Addressed

### Accounts & Backend Dashboard
- **`apps/accounts/views.py`**
  - Notifications: wired to `Notification` model with filters (unread/read), counts, and list.
  - Backend dashboard: `_safe_reverse`, `_item()`, role/permission-gated `available_sidebar_items` (Messages, Notifications, Groups, Report Builder, Report Library, Certification, Document Library, Signatures, Customizer, KB, etc.).
  - Certification stats on backend when GCE is enabled.
  - Workflow center with steps (Year setup → Onboarding → Marks → Publish reports → Communication → Certification → Settings).
  - **Fix:** `organized_sidebar` and `sidebar_categories` are now computed via `sidebar_organizer` and passed to the template (avoids `NameError`).
- **`apps/accounts/urls.py`** — Certification routes added (sessions, bulk-add, override, export).
- **`templates/accounts/backend_dashboard.html`** — Uses `organized_sidebar` / `sidebar_categories` for grouped sidebar; certification stats; Messages/Report Builder in header.
- **`templates/accounts/notifications.html`** — Full UI: extends `portal_base`, stats cards (total/unread/read), filters, notification list.
- **`templates/accounts/profile.html`** — Minor tweaks (e.g. profile link).

### Portal Sidebar & Navigation
- **`templates/partials/portal_sidebar.html`**
  - My Profile → `accounts:user_profile` (no longer admin change URL).
  - Notifications → `accounts:user_notifications` (was `#`).
  - Messages link added under Account; Communication section by role (Teacher/Parent/Admin) with Messages, Message Groups, Announcements, Contact School.
  - Workflow Center link for staff/admin.
  - Report Card Builder → `siteconfig:reportcard_builder` (custom UI, not admin).
  - Help Center link.
  - Portal Tools “Messaging” → `accounts:user_messages` (was `portal:portal_feature 'messaging'`).

### Dashboards (Payroll, EMIS, Compliance)
- **`apps/payroll/views.py`** — Dashboard passes `allow_custom_layout`, `dashboard_settings`, `dashboard_layout_url`, `available_sidebar_items`, `widget_meta_json`.
- **`emis/views.py`** — Same dashboard customizer context for EMIS.
- **`apps/compliance/views.py`** — Same for compliance + `available_sidebar_items` (Audit, Data Access, Permissions, Integrity, Anomalies).
- **`templates/payroll/dashboard.html`**, **`templates/emis/dashboard.html`** — Customizer UI and layout wrapper added where applicable.

### Portal & Documents
- **`apps/portal/urls.py`** — Document library backend routes (`document_library_manage`, `document_upload`, edit/delete/download), signature routes (manage, create, parent sign).
- **`apps/portal/views.py`** — Parent dashboard: certification stats when GCE enabled; `signature_stats`; document/signature integration.
- **`apps/portal/admin.py`** — KB/FAQ admin registration.
- **`apps/portal/models.py`** / **`apps/portal/models_kb.py`** — Model/field changes for documents/KB.
- **`templates/portal/feature_page.html`**, **`templates/portal/kb_home.html`** — Small updates.

### KB & FAQ
- **`apps/portal/management/commands/import_docs_to_kb.py`** — Operator Manual categories, doc mapping, `--include-root`, Unicode-safe output (e.g. `[OK]` instead of ✓).
- **`apps/portal/management/commands/seed_faqs.py`** — Large reduction (duplicate `Command` / generic FAQs removed; single curated FAQ command kept).

### Other
- **`apps/academics/admin.py`**, **`apps/academics/models.py`** — Certification/GCE-related admin and models.
- **`apps/evals/views.py`** — Extra context (e.g. for dashboard/certification).
- **`apps/siteconfig/models.py`** — Small field/default changes.
- **`static/css/admin_sidebar_enhanced.css`**, **`static/css/dashboard-layout-controls.css`** — Sidebar/layout styling.
- **`templates/base.html`**, **`templates/portal_base.html`**, **`templates/components/user_dropdown.html`** — Minor fixes/links.
- **`templates/parent/dashboard.html`**, **`templates/teacher/dashboard.html`** — Certification stats, layout/alignment.

---

## Untracked Files (Already Implemented)

- **Docs:** Workflow docs (Year setup, Onboarding, Marks, Report cards, GCE, Communication, Finance), FAQs, DB recovery, dashboard/certification integration.
- **Certification:** `views_certification.py`, `services_certification.py`, export command, migrations, templates (certification_home, session_detail, bulk_add).
- **Documents & Signatures:** `views_documents.py`, `forms_documents.py`, portal migrations, templates (document_library_manage, document_upload, signature_*).
- **Backend people UI:** `apps/people/views_backend.py`, `forms_backend.py`, `templates/people/`.
- **Sidebar:** `apps/accounts/sidebar_organizer.py` (used by backend dashboard after the fix above).
- **Recovery:** `recover_database` management command.
- **CSS:** `ui-alignment-improvements.css`.
- **Summaries:** Various COMPLETE/SUMMARY/AUDIT markdown files.

---

## Bug Fixed in This Review

- **Backend dashboard crash:** The template used `organized_sidebar` and `sidebar_categories`, but the view never defined them. **Fix:** In `apps/accounts/views.py`, after building `available_sidebar_items`, the code now does:
  - `from .sidebar_organizer import organize_sidebar_items, get_sidebar_category_labels`
  - `organized_sidebar = organize_sidebar_items(available_sidebar_items, request.user)`
  - `sidebar_categories = get_sidebar_category_labels()`
  So the backend dashboard no longer raises a `NameError` when rendering the organized sidebar.

---

## Recommendation

- **Commit the fix** in `apps/accounts/views.py` (sidebar organizer usage) with the rest of your backend dashboard/sidebar changes.
- **Stage and commit** the other modified and new files when you’re ready; the uncommitted set is consistent with the “already addressed” work (notifications, messaging links, report builder link, dashboard customizers, workflow center, certification, documents/signatures, KB/FAQ, sidebar organization).
