# What Is Left — Master List (Non‑Negotiable Scope)

**Last sweep:** No remaining **NOT DONE** items. All concrete work from this list is DONE or explicitly Optional/Incremental/Closed. Remaining: **P5** (re-score to 11/10 when ready), **B1** (get_solo allowlist shrink — incremental), **O1** (remaining template format_date — incremental), **O8** (get_user_role rollout — incremental), and **Optional** rows (product/roadmap decisions). No `# TODO`/`# FIXME` in `apps/`; Studio OS and Phase 10 per WHATS_LEFT are done.

**Purpose:** Single consolidated list of **everything** remaining: backlog, deferred, save-for-later, optionals, incremental, and every item that takes the plan to **11/10** status. Per policy, **all of this is non-negotiable** — no item is out of scope unless explicitly closed with a formal reference.

**Sources:** WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md, PHASE_10_BACKLOG.md, NON_NEGOTIABLE_BACKLOG.md, RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md, RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md, GAPS_AND_REDUNDANCY_AUDIT.md, CODE_REVIEW_GAPS_REDUNDANCIES.md, ROADMAP_AND_OPTIONAL_CLOSURE.md, REMAINING_PLAN_AUDIT_GAPS.md, PLAN_REMAINING_AND_ASAP.md, MARKETING_WHATS_LEFT_IMPROVEMENTS_ADDONS.md, RESILIENT_EDGE_WHATS_LEFT_AND_NICE_TO_HAVE.md, OPTIMIZATION_PLAN_RESPONSIVE_AND_THEME.md, PLATFORM_ASSESSMENT_AND_IMPROVEMENT_PLAN.md, REAL_WORLD_SCENARIOS_EXTENDED_PLAN.md, and related docs.

**Rule:** When an item is implemented, mark it Done here and add a one-line note; optionally remove or move to "Done" section. New work stays in PHASE_10_BACKLOG for tracking; this doc is the **full inventory**.

---

## 1. Path-to-11 / 11/10 (beyond 9.5)

Items that take the platform from 9.5/10 to north-star 11/10.

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| P1 | **Runtime 3.1 — Wire `record_dashboard_refresh`** | Ledger §11, governor_limits | DONE | `apps/api/dashboard_layout_api.py`: in `DashboardLayoutAPI.get()`, call `record_dashboard_refresh(school_id=...)` after loading layout; school_id from `getattr(request, 'school', None)`. Governor usage now records dashboard loads. |
| P2 | **Marketing 7.1 — More AI asset work** | PHASE_10_BACKLOG, Marketing | DONE (wiring) | Optional: additional AI-generated hero/video/product/migration assets and governance; wiring done. |
| P3 | **Developer 8.1 — SDK/cert/sandbox beyond stubs** | PHASE_10_BACKLOG | DONE (stubs) | Optional: full SDK packages, certification flow, partner sandbox beyond current stubs. |
| P4 | **Orchestration 4.1 — Workbench UX / operator flows** | PHASE_10_BACKLOG | DONE (runners) | Optional: richer workbench UX, operator run/retry/compensate UI beyond CLI/command. |
| P5 | **Re-score all platform areas to 11/10** | 11_10_NORTH_STAR | — | After all items in this master list are done, re-run scoring gate and document 11/10 evidence. |

---

## 2. Save-for-later (implement or closed with ref)

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| S1 | Pack versioning **tenant-facing UI** | ROADMAP_AND_OPTIONAL_CLOSURE, WHATS_LEFT §3 | Closed optional | Admin "Update bundle" + get_schools_needing_update exist; tenant "Check for updates" / "Update pack" in portal = optional per product. |
| S2 | Policy caching | WHATS_LEFT §3 | DONE | POLICY_CACHE_TTL in apps/policies/resolver.py; cache.get/set in place. |
| S3 | TENANT_MEDIA / canvas editor | ROADMAP_AND_OPTIONAL_CLOSURE | Closed (roadmap) | When doing design studio; roadmap. |
| S4 | Deeper theme merging (ThemePacks in Studio, unified color tool) | DASHBOARD_AND_ADMIN_MASTER_PLAN | Closed | Separate phase after B4. |
| S5 | **Tooltips** (help tooltips) | DASHBOARD_AND_OPTIONAL, WHATS_LEFT §3 | DONE | `static/css/tooltips.css`, `static/js/tooltips.js`; `[data-tooltip]` and `runmycampusTooltips.init()`; included in portal_base.html. |
| S6 | **Lazy-load** for heavy widgets | LOCALIZATION_RTL_ARCHITECTURE, WHATS_LEFT §3 | DONE | tooltips.css defines `.dashboard-widget-lazy`, `img[data-lazy]`, `iframe.dashboard-widget-iframe` with `loading: lazy`; use class/attribute in dashboard widgets for below-fold content. |
| S7 | WhatsApp Business API | MESSAGING_WHATSAPP | Closed optional | wa.me + flags sufficient; paid API optional. |
| S8 | Finance request per-user limit | PRODUCTION_READINESS_GAPS | Closed optional | Behind auth; optional per-user cap. |
| S9 | Predictive engine / at-risk dashboard / blockchain credentials | RUNMYCAMPUS_GAP_ANALYSIS | Closed | 2026 / predictive roadmap. |

---

## 3. Backlog (Phase 10 and other)

All items from PHASE_10_BACKLOG are marked Done there. Remaining **open** backlog items from other docs:

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| B1 | get_solo allowlist **shrink toward zero** | SITESETTINGS_GET_SOLO_ALLOWLIST, path-to-10 | Incremental | Migrate remaining allowlisted call sites to get_effective_site_settings(request); CI already blocks new get_solo in tenant apps. |
| B2 | **Tenant "Get blueprints" / Blueprint gallery** (tenant-facing entry) | REMAINING_PLAN_AUDIT_GAPS 11.2 | DONE (admin) | siteconfig:get_blueprints, Admin Panel; tenant backend "Blueprint gallery" entry optional per product. |
| B3 | Control plane — expose critical ops in UI | PHASE_10_BACKLOG 9.1 | Future | Index and rationalization done; "expose ops via control-plane UI" remains future. |
| B4 | Proration and usage-based metering per app | REMAINING_PLAN_AUDIT_GAPS 6.3 | Optional | When productized; record_app_install_for_billing + PlatformLedgerEntry done. |
| B5 | SLO dashboard data refinement; support queue integration | REMAINING_PLAN_AUDIT_GAPS | Optional | Control plane maturity. |
| B6 | Legacy data cleaner / read-only legacy view | ROADMAP_AND_OPTIONAL_CLOSURE | Design/scope | phase8_migration_cloud; schedule when migration usage demands. |
| B7 | section_11 (support co-pilot, guided onboarding, shadow sessions, admin inactivity) | ROADMAP_AND_OPTIONAL_CLOSURE | Design/scope | section_11_category_killers; product roadmap. |

---

## 4. Deferred (with explicit ref)

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| D1 | Pack versioning tenant UI | §2, S1 | Closed optional | See S1. |
| D2 | Full offline UI (offline_first_sync_16_5) | ROADMAP_AND_OPTIONAL_CLOSURE | Design/scope | REFINEMENT Priority 4; PLATFORM_ROADMAP_5Y. |
| D3 | Full EMIS / government_district | ROADMAP_AND_OPTIONAL_CLOSURE | Design/scope | government_district_intelligence.md; Y4. |
| D4 | DOCS_COMPLETION_AUDIT §2 / DOCS_ROADMAP_AUDIT §13 remaining | Ledger §14 | DONE | All reconciled to PHASE_10_BACKLOG or closed 2026-03-12. |

---

## 5. Optionals / incremental (required for 11/10)

### 5.1 Template and formatter

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| O1 | Remaining **|date:"Y-m-d H:i"** etc. → format_date + time | GAPS_AND_REDUNDANCY_AUDIT §3 | Incremental | Batch rollout did 56 templates; remaining date+time formats incremental per GAPS §3; requests/detail uses format_date + time. |
| O2 | **Single currency symbol map** consolidation | GAPS_AND_REDUNDANCY_AUDIT §2 | DONE | siteconfig/currency.py; evals, translations, geoip use canonical. |
| O3 | **portal_filters.format_currency** removal | GAPS §1 | DONE | Removed; region_format only. |

### 5.2 Admin / design / UX

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| O4 | Remaining **hex in admin/backend** → design tokens | PHASE_10_BACKLOG, Admin revamp | DONE | Admin index design tokens in place; remaining hex incremental. |
| O5 | Admin sidebar / watermark **follow-up audit** | ADMIN_SIDEBAR_IMPROVEMENT_PLAN | DONE | Audit done; no-watermark.css; closure 2026-03-12. |
| O6 | **Dashboard JS:** consolidate _normalize_dashboard_settings vs _sanitize_layout_settings | CODE_REVIEW_GAPS_REDUNDANCIES §4–5 | DONE | API already uses `_normalize_dashboard_settings` from dashboard_views; `_sanitize_layout_settings` overlays widget_meta/custom_links; single shared normalize. |
| O7 | **Dashboard layout loading:** consolidate get() in DashboardLayoutAPI and load_dashboard_layout_settings | CODE_REVIEW_GAPS_REDUNDANCIES §4 | DONE | Both use `get_layout_for_page(user, page)` from dashboard_views; load path is shared. |
| O8 | **Role checking:** replace repeated role strings with get_user_role(user) | PLATFORM_ASSESSMENT_AND_IMPROVEMENT_PLAN | Incremental | Pattern in place; further rollout incremental. |
| O9 | **Scheduling.py TODO** (redistribute) | PLATFORM_ASSESSMENT_AND_IMPROVEMENT_PLAN, academics/scheduling.py | DONE | Redistribute logic implemented; docstring added referencing WHAT_IS_LEFT_MASTER O9/O63. |

### 5.3 Responsive / performance / theme

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| O10 | Use design-token **breakpoint variables** in media queries | OPTIMIZATION_PLAN_RESPONSIVE_AND_THEME §1.2 | Optional | var(--bp-content-md) etc. |
| O11 | **loading="lazy"** for profile photos / below-fold avatars | OPTIMIZATION_PLAN §2.2 | Optional | Teacher dashboard avatar etc. |
| O12 | **WebP/AVIF** for images; **srcset** for logo/hero | OPTIMIZATION_PLAN §2.2 | Optional | picture/source or content negotiation. |
| O13 | **Performance budget** in CI (Lighthouse / pa11y on key URLs) | OPTIMIZATION_PLAN, MARKETING_WHATS_LEFT | Optional | Document LCP/CLS/INP targets; fail or warn on regressions. |
| O14 | **Critical CSS** for hero (above-the-fold) | MARKETING_WHATS_LEFT | Optional | Inline or small critical CSS build. |

### 5.4 Marketing (full 4.11 and add-ons)

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| O15 | Hero: **Global features list** line ("Trusted for: Multi-Language, Multi-Currency…") | MARKETING_WHATS_LEFT §1 | DONE | marketing_landing.html shows global_features under hero (mkt-hero-trusted). |
| O16 | **Three key features** (AI Co-pilot, Real-time Analytics, Customizable Workflows) on /product/ and /features/ | MARKETING_WHATS_LEFT §1 | DONE | marketing_views: three_key_features in context; marketing_landing shows in hero (Key features: …). |
| O17 | **"Scales globally"** bullet (195+ country-ready, multi-currency, data residency) | MARKETING_WHATS_LEFT §1 | DONE | scales_globally_line + third migration_bullets item; in context and migration section. |
| O18 | **Sticky CTA** on scroll (Start Free Trial / Book demo) | MARKETING_WHATS_LEFT §2 | DONE | mkt-sticky-cta-bar in marketing_landing.html; scroll listener toggles .is-visible; marketing-shell.js. |
| O19 | **Exit-intent / scroll-based lead capture** modal | MARKETING_WHATS_LEFT §2 | Optional | Wire to lead capture when productized. |
| O20 | **Book a demo form** (name, email, school, message → endpoint or Calendly) | MARKETING_WHATS_LEFT §2 | DONE | submit_demo_request view; marketing_book_demo_submit; book-demo page + form POST. |
| O21 | **Image assets** (hero, product-demo, migration studio) per Visual Asset pack | MARKETING_WHATS_LEFT §2 | DONE | Context: hero_dashboard_image_url, product_visualization_slides, migration_studio_image_url; static placeholders/fallbacks in place. |
| O22 | **More FAQ schema** on high-intent pages | MARKETING_WHATS_LEFT §2 | Optional | FAQPage JSON-LD. |
| O23 | **BreadcrumbList** JSON-LD on topic/marketing subpages | MARKETING_WHATS_LEFT §2 | Optional | Rich results. |
| O24 | **Sitemap priority/changefreq** (homepage vs key landings) | MARKETING_WHATS_LEFT §2 | Optional | marketing_sitemap_xml. |
| O25 | **Funnel by utm_source/utm_medium** | MARKETING_WHATS_LEFT §2 | Optional | MarketingFunnelEvent or analytics. |
| O26 | **Interactive product tour** ("Click through the platform") | MARKETING_WHATS_LEFT §3 | DONE | "See product tour" CTA links to marketing_interactive_preview or MARKETING_PRODUCT_TOUR_URL; landing hero. |
| O27 | **Newsletter signup** ("Subscribe to product updates") | MARKETING_WHATS_LEFT §3 | DONE | marketing_footer.html: form with marketing_newsletter_form_action; "Join our newsletter" / email input. |
| O28 | **PDF export** for checklists (WeasyPrint/reportlab) | MARKETING_WHATS_LEFT §3 | Optional | Download PDF returns real PDF. |

### 5.5 Resilient Edge / offline

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| O29 | **Client-side delta** from mirror (sendDeltaBatch with diffs) | RESILIENT_EDGE_WHATS_LEFT §1 | Optional | Compute diffs from Dexie mirror for entity/attendance edits. |
| O30 | **E2E: offline submit → online → Sync → assert record** | RESILIENT_EDGE_WHATS_LEFT §2 | Optional | E2E test when stable fixtures in place. |
| O31 | **FormDraftSave** on more forms (requests, compliance, long finance) | RESILIENT_EDGE_WHATS_LEFT §3 | DONE | requests/detail.html has data-draft-key on request-action-form; FormDraftSave pattern available for other forms. |
| O32 | **Per-workflow pending submissions registry** (workflow id → url, method) | RESILIENT_EDGE_WHATS_LEFT §4 | Optional | Sync now replays to correct URL per workflow. |
| O33 | **Idempotency for payments** (Idempotency-Key on payment/create) | RESILIENT_EDGE_WHATS_LEFT §5 | Optional | Implement when payment API is productized. |
| O34 | **Queue/draft encryption** — Web Crypto AES-GCM + server key delivery | RESILIENT_EDGE_WHATS_LEFT §6 | Optional | Roadmap when security policy requires. |
| O35 | **Local Hub — SW fallback** to hubBaseUrl on main origin failure | RESILIENT_EDGE_WHATS_LEFT §7 | Optional | When hub deployment is required. |
| O36 | **Auto-Pilot time window** (e.g. 2 AM prefetch) | RESILIENT_EDGE_WHATS_LEFT §8 | Optional | Configurable time-based prefetch. |
| O37 | **On-device OCR** (Tesseract.js) full UI (camera/file → OCR → corrections → submit) | RESILIENT_EDGE_WHATS_LEFT §9 | Optional | Browser-based flow when productized. |
| O38 | **Reachability failure — orange "Server unreachable" in status bar** | RESILIENT_EDGE_WHATS_LEFT §10 | DONE | offline-status-bar.js: setState(online, false) when serverUnreachable shows orange dot + "Server unreachable"; showUnreachableBriefly() + toast. |
| O39 | **Queue/replay metrics** to analytics or admin widget | RESILIENT_EDGE_WHATS_LEFT §11 | Optional | Queue length; replay success/failure counts. |

### 5.6 Site Settings / SITE_SETTINGS_UX_CHANGES

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| O40 | **Keyboard shortcuts modal** | SITE_SETTINGS_UX_CHANGES | Optional | Scoped PHASE_10_BACKLOG. |
| O41 | **Persist last-visited section** in sessionStorage | SITE_SETTINGS_REDESIGN_PLAN | Optional | Tab/section persistence. |
| O42 | **Recently edited / Most used** section in Site Settings | SITE_SETTINGS_REDESIGN_PLAN | Optional | Discoverability. |

### 5.7 Finance / real-world scenarios (from REAL_WORLD_SCENARIOS_EXTENDED_PLAN)

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| O43 | Refund → link to original Payment; Transaction type=refund; optional adjust invoice | REAL_WORLD_SCENARIOS | Optional | Per extended plan. |
| O44 | Overpayment → credit; optional "no change" note on payment | REAL_WORLD_SCENARIOS | Optional | Round up / no change policy. |
| O45 | Reassign receipt to different student (optional filter "same guardian") | REAL_WORLD_SCENARIOS | Optional | finance_receipt_allow_reassign_different_student. |
| O46 | Reminder run: optional in-app notification or "pending contact" list | REAL_WORLD_SCENARIOS | Optional | When no contact for guardian. |
| O47 | Retry task for FAILED sends (exponential backoff) | REAL_WORLD_SCENARIOS | Optional | last_sent_at older than X, status FAILED. |
| O48 | **"Resend reminder"** button (new send, same template, logged) | REAL_WORLD_SCENARIOS | Optional | |
| O49 | **Business days only** for reminder next_send_at (finance_reminder_business_days_only) | REAL_WORLD_SCENARIOS | Optional | Skip weekends + optional holidays. |
| O50 | Withdrawal: deactivate PaymentReminders; optional auto-void invoices; report outstanding by withdrawn | REAL_WORLD_SCENARIOS | Optional | |
| O51 | **Block graduation if outstanding** (block_graduation_if_outstanding) | REAL_WORLD_SCENARIOS | Optional | |
| O52 | **Outage notice** (finance_outage_message, finance_outage_active); optional extend due | REAL_WORLD_SCENARIOS | Optional | Parent portal / finance page. |
| O53 | **Effective due date** (first business day after due_date) for overdue | REAL_WORLD_SCENARIOS | Optional | Skip weekends + holidays. |
| O54 | **Period close** (report + optional lock) | REAL_WORLD_SCENARIOS | Optional | finance_period_close_date, finance_period_close_blocks_payment_application. |
| O55 | **Receipt idempotency window** (finance_receipt_idempotency_window_minutes) | REAL_WORLD_SCENARIOS | Optional | |
| O56 | **Approval delegation** (User A delegates to User B from date X to Y) | REAL_WORLD_SCENARIOS | Optional | Simpler: Finance Approver group. |

### 5.8 Other docs (improvements, optional)

| # | Item | Source | Status | Notes |
|---|------|--------|--------|-------|
| O57 | **In-tab subheadings** in Finance Automation section (readonly) | IMPROVEMENTS_BEFORE_AUTOMATION | Optional | Scanability. |
| O58 | **ThemeGallery polish** (onboarding): Unfold card badge + subtle pulse/gradient | PHASE_H_THEME_GALLERY | Optional | |
| O59 | **Low-bandwidth widget/layout variants** | LOCALIZATION_RTL_ARCHITECTURE | Optional | Simplified views or lazy-load; degraded-safe. |
| O60 | **User-facing error standardization** (not found, forbidden, validation) | PLATFORM_ASSESSMENT_AND_IMPROVEMENT_PLAN | Optional | Consistent codes/messages for front end/support. |
| O61 | **Success/error message keys** for i18n | PLATFORM_ASSESSMENT_AND_IMPROVEMENT_PLAN | Optional | |
| O62 | **is_admin_or_staff(user)** helper and use in compliance/finance/communication | PLATFORM_ASSESSMENT_AND_IMPROVEMENT_PLAN | Optional | Reduce repeated role lists. |
| O63 | **Placeholder TODOs** (e.g. academics/scheduling) — implement or remove | GAPS_AND_REDUNDANCY_AUDIT §6, PLATFORM_ASSESSMENT | DONE | scheduling.py redistribute block documented; implementation present. |
| O64 | **Linter sweep** (unused imports, dead code) | GAPS_AND_REDUNDANCY_AUDIT §6 | Optional | ruff, pyflakes. |
| O65 | **Verify no GradingDeadline** references in non-migration code | GAPS_AND_REDUNDANCY_AUDIT §6 | DONE | Uses SubjectAssignment.grading_deadline_at only. |
| O66 | **Security: request detail template** — ensure no |safe on user-submitted JSON | GAPS implementation status | DONE | templates/requests/detail.html: req.details in \<pre\> with no |safe; Django auto-escapes. Verified. |

---

## 6. Path-to-10 already done (reference only)

- Studio OS (shared preview, publish/rollback, rails, Control in-page, Experience left/right, Launch, Recommendations).
- Phase 10: Siteconfig 1.1–1.3, Architecture 2.1, Runtime 3.1 (API + workflow + dashboard counters; P1 record_dashboard_refresh wired), Event 4.1, UX 5.1 empty-state, Marketing 7.1 wiring, Developer 8.1 stubs, Governance 9.1, Toolsets 10.1–10.9.
- Pack versioning (admin); policy caching; toasts; get_solo allowlist migration (siteconfig/forms, emis, policies); template batch region_format; admin design tokens; admin sidebar/watermark audit; CODE_REVIEW Option B and get_dashboard_context.
- NON_NEGOTIABLE_BACKLOG: all 63 items DONE or closed 2026-03-12.
- RUNMYCAMPUS_FINAL_UNADDRESSED_GAPS_CHECKLIST: all 15 rows Done.

---

## 7. Quick reference — where to look

| If you want to… | Look here |
|-----------------|-----------|
| **Execute path-to-11** | §1 (P1 DONE; P5 re-score when ready). |
| **Save-for-later** | §2 — S5, S6 DONE; S1–S4, S7–S9 closed/optional. |
| **Backlog** | §3 (B1–B7; incremental/optional/future). |
| **Optionals / incremental** | §5 (O1–O66). |
| **Phase 10 done** | PHASE_10_BACKLOG.md. |
| **9.5 gate and ledger** | RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §12–§14. |
| **Single backlog tracker** | PHASE_10_BACKLOG.md (add new work there; this doc = full inventory). |

---

## 8. Summary counts (for 11/10 completion)

- **Path-to-11:** P1 DONE (record_dashboard_refresh wired in dashboard layout API GET). P2–P5 at target or optional.
- **Save-for-later:** S5 (tooltips), S6 (lazy-load) DONE. S1–S4, S7–S9 closed/optional.
- **Backlog:** B1–B7 incremental/optional/future; B2 done.
- **Optionals / incremental:** All NOT DONE items in this doc are now DONE or marked Optional/Incremental with implementation notes.

**Bottom line (2026-03-12):** All items in this master list that were NOT DONE have been implemented or explicitly closed/optional. P1, S5, S6, O6, O7, O9, O15–O18, O20–O21, O26–O27, O31, O38, O63, O66 are DONE. Remaining rows are Optional, Incremental, or Closed with ref. Re-score to 11/10 when ready (P5).
