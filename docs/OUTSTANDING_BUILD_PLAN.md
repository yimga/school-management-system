# Outstanding Work – Build Plan (Sequential Implementation)

**Date:** 2026-02-02  
**Purpose:** Single checklist for all remaining improvements. Implement in order; each phase can be split into smaller PRs.  
**Status:** All phases complete (Phases 1–7 marked Done).

---

## Phase 1 – Quick wins (already partially done / low risk)

| # | Item | Owner / Notes | Status |
|---|------|----------------|--------|
| 1.1 | **Back button** | Already in `templates/admin/submit_line.html` next to Save/Close. Verify on change/detail pages; ensure styling matches “Save and continue editing” (secondary style). | Done |
| 1.2 | **Site Settings breadcrumb** | Model has `verbose_name_plural = "Site Settings"`. If UI still shows “Site Settingss”, find source (Unfold tab/changelist title) and fix. | Done (title in changeform_view) |
| 1.3 | **Analytics Defaults purpose** | Section has real fields (top_students_default_limit, pass_mark, deadline_mode, etc.). Add a short fieldset **description** in SiteSettingsAdmin so purpose is clear (defaults for analytics dashboards, rankings, pass/fail, deadlines). | Done |
| 1.4 | **Theme/UI consistency** | Toggle CSS (red/green) extended; button hierarchy and theme audit checklist in doc. | Done |

---

## Phase 2 – Site Settings redesign (from SITE_SETTINGS_REDESIGN_PLAN.md)

| # | Item | Owner / Notes | Status |
|---|------|----------------|--------|
| 2.1 | **Phase 2.1 – Option B (short term)** | One “Finance Automation” tab with in-tab subsections (collapsible or subheadings). Vertical sidebar in use. | Done |
| 2.2 | **Phase 2.2 – Option A (medium term)** | Vertical sidebar and SETTINGS_NAV_GROUPS in place (General, Portal, Backend & compliance, Reports & grades, Finance Automation, Analytics, Automation, Metadata). | Done |
| 2.3 | **Replace raw JSON** | Summaries (backend_flags_summary, portal_features_help) and Feature Control for audited toggles; descriptions point to Feature Control. Full widget replacement deferred. | Done |
| 2.4 | **Color Picker presets** | Added Gilead Blue, Primary School, University Navy, Campus Green, Sunrise Accent. | Done |
| 2.5 | **Space & layout** | Full-width main; 2-column form rows on wide screens; button hierarchy in submit row (Site Settings change_form). | Done |

---

## Phase 3 – Analytics & empty sections

| # | Item | Owner / Notes | Status |
|---|------|----------------|--------|
| 3.1 | **Analytics Defaults** | Already has fields; add description (see 1.3). If any other section is empty, show a clear “Coming soon” message. | Done |

---

## Phase 4 – WhatsApp integration (deeper)

| # | Item | Owner / Notes | Status |
|---|------|----------------|--------|
| 4.1 | **Parent/staff communications** | UserPreference.notification_channels (Email/SMS/WhatsApp); doc in `docs/WHATSAPP_OPT_IN.md`. | Done |
| 4.2 | **Payment reminders** | WhatsApp as channel; SiteSettings default + UserPreference override via get_notification_channels. | Done |
| 4.3 | **Sharing data (e.g. reports)** | Share via WhatsApp button on Share Report page when enable_whatsapp_parent_portal. | Done |

---

## Phase 5 – Automation (from AUTOMATION_PLAN_FINAL.md)

| # | Item | Owner / Notes | Status |
|---|------|----------------|--------|
| 5.1 | **PaymentReminder multiple days** | JSONField + `get_reminder_days()` / `get_reminder_channels()` with SiteSettings fallback already in model. | Done |
| 5.2 | **Dry-run for all automation** | Payment reminders: `run_payment_reminders(dry_run=True)`, task and mgmt command `--dry-run`. Invoice gen and invoice status already have dry_run. | Done |
| 5.3 | **Admin approval (optional)** | High-risk tasks can require approval; don’t block automation. | Done |
| 5.4 | **Notification channels** | SiteSettings default + UserPreference override via get_notification_channels(). | Done |

---

## Phase 6 – Payment processing & fraud

| # | Item | Owner / Notes | Status |
|---|------|----------------|--------|
| 6.1 | **Cash/bank receipt verification** | Documented in `docs/PAYMENT_VERIFICATION_AND_FRAUD.md`. | Done |
| 6.2 | **Falsification / fraud** | Documented (fraud detection, manual review, notifications). | Done |
| 6.3 | **Finance notifications** | Documented; suspicious receipts notify finance; optional parent notification on apply. | Done |

---

## Phase 7 – Full automation module (all modules)

| # | Item | Owner / Notes | Status |
|---|------|----------------|--------|
| 7.1 | **Audit per module** | What can/cannot be automated; admin’s role; guardrails. See AUTOMATION_ALL_MODULES_WORKFLOW.md (implementation status table added). | Done |
| 7.2 | **Single “Automation” UI** | One place for schedules, dry-run, Automation Hub at /accounts/workflow/automation/. | Done |

---

## Implementation order (recommended)

1. **Phase 1** – Finish quick wins (Back button check, breadcrumb, Analytics Defaults description, theme audit).
2. **Phase 2.1** – Site Settings Option B (fewer tabs, one Finance Automation tab with subsections).
3. **Phase 3** – Any remaining “empty section” messaging.
4. **Phase 2.2–2.5** – Site Settings vertical sidebar, JSON→widgets, presets, layout.
5. **Phase 5** – Automation (PaymentReminder JSONField, dry-run, approval, channels).
6. **Phase 4** – WhatsApp (opt-in, payment reminders, report sharing).
7. **Phase 6** – Payment/fraud documentation and notifications.
8. **Phase 7** – Full automation module and UI.

---

## Theme audit checklist (Phase 1.4)

Use this when auditing a screen for theme/UI consistency:

- [ ] **Toggles:** ON = green (#16a34a), OFF = red in admin/Site Settings (#dc2626), grey elsewhere. `toggle-colors.css` covers admin, change-form, changelist, app-siteconfig, backend (portal-backend-*, data-dashboard-page), #content.
- [ ] **Buttons:** Primary = solid (e.g. Save); secondary = bordered (Back, Save and continue editing); danger = red (Delete). Use design-system variables or explicit hex for danger.
- [ ] **Full-width:** Dashboard and list pages use full width where intended; no unnecessary max-width on main content.
- [ ] **Dropdowns:** Consistent padding, border-radius, and focus ring; no cramped or unstyled native selects.
- [ ] **Header/footer:** Same visibility and branding across admin vs backend; no duplicate or missing header/footer on key pages.

---

## Reference docs

- **Site Settings:** `docs/SITE_SETTINGS_REDESIGN_PLAN.md`
- **Automation:** `docs/AUTOMATION_PLAN_FINAL.md`, `docs/AUTOMATION_ALL_MODULES_WORKFLOW.md`
- **Audits:** `docs/APPS_AUDIT_REPORT.md`, `docs/MODULE_AUDIT_GAPS_REDUNDANCIES_SECURITY.md`
- **Theme:** `docs/THEME_AND_COLOR_GAPS_DETAILED_AUDIT.md`, `docs/THEME_CANONICAL_TOKENS.md`
- **WhatsApp / notifications:** `docs/WHATSAPP_OPT_IN.md`

---

## Error follow-ups (if they recur)

- **`NameError: render_to_string`** – Already imported in `apps/siteconfig/admin.py`; if it reappears, ensure no circular import or overridden module.
- **`SyntaxError: unmatched '}'` in dashboard_layout_api.py** – Current file is clean; if seen again, re-check the exact line (e.g. list/dict literal).
- **`TypeError: cannot use 'dict' as a set element`** (migrate) – Related to PaymentProofUpload/is_suspicious index. Ensure Meta.indexes reference only model fields and no dict/set misuse in migration.
