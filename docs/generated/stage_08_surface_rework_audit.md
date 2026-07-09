# Stage 08 Surface Rework Audit

- Total findings: 180
- Critical: 0
- High: 0
- Medium: 0
- Low: 180

## Findings

### LOW - css_width_cap_review
- Path: `static/css/admin-200x-shell-overlay.css:95`
- Evidence: `body[data-rmc-admin-shell="1"][data-rmc-nav-bridge-host="manager"] .dashboard-header .dashboard-subtitle { max-width: 720px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-200x-shell-overlay.css:393`
- Evidence: `-html="unfold"] body[data-rmc-admin-shell="1"][data-rmc-nav-bridge-host="manager"] .dashboard-header .dashboard-subtitle { max-width: 720px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-color-preview.css:68`
- Evidence: `.theme-pack-filter-row .form-control { max-width: 360px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-components.css:93`
- Evidence: `.hero-subtitle { max-width: 420px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-components.css:606`
- Evidence: `.modal { max-width: 600px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-manager-shell.css:399`
- Evidence: `Pin all instances    to the same corner and hide every sibling after the first. */ body.admin-manager-shell .lx-notebook { max-width: 360px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-manager-shell.css:409`
- Evidence: `(✎) OR click here. Single source of truth. */ body.admin-manager-shell .lx-notebook[data-rmc-notebook-state="minimized"] { max-width: 220px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-manager-shell.css:780`
- Evidence: `html:not([data-rmc-admin-density="comfortable"]) body.admin-manager-shell .cp-hero__lede { max-width: 72ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-platform-catalog.css:33`
- Evidence: `.rmc-admin-catalog-search-wrap input[type="search"] { max-width: 32rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-sidebar-polish.css:404`
- Evidence: `body.admin-sidebar-compact #nav-sidebar { max-width: 4.5rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-sidebar-polish.css:410`
- Evidence: `body.admin-sidebar-compact .admin-sidebar-column .fixed.w-\[288px\] { max-width: 4.5rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/admin-sidebar-scroll.css:21`
- Evidence: `fied-page)) .admin-sidebar-column, #page:not(.admin-cp-unified-page):not(:has(.admin-cp-unified-page)) > div:first-child { max-width: 288px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/auth-login-canvas.css:323`
- Evidence: `.rmc-auth-immersive__hero-marquee-item span { max-width: 36ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/auth-login-canvas.css:374`
- Evidence: `.rmc-auth-immersive__slide strong { max-width: 32ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/backend-dashboard-v2.css:30`
- Evidence: `body[data-dashboard-page="backend"] #portalHeader .topbar-search.header-search-container { max-width: 540px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/backend-dashboard-v2.css:961`
- Evidence: `.backend-role-home-sub { max-width: 56rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/badge-verify.css:18`
- Evidence: `.badge-verify-card { max-width: 28rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/control-plane-ultra.css:123`
- Evidence: `ile only; desktop gets proper width (no "mobile strip" on large screens) */ body.control-plane-shell .cp-login-container { max-width: 480px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/control-plane-ultra.css:188`
- Evidence: `layout is not a narrow strip */ body.control-plane-shell .manager-login-card, body.control-plane-shell .admin-login-card { max-width: 420px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/cp_operator_hub.css:65`
- Evidence: `.cp-operator-hub .cpoh-sub { max-width: 46rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/dashboard-responsive.css:19`
- Evidence: `hboard-card, .metrics-section, .chart-section, .admin-page, .parent-dashboard, .teacher-dashboard, .compliance-dashboard { max-width: 1600px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-system-phase2-enforcement.css:146`
- Evidence: `.ds-empty__body { max-width: 32rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-system-phase2-enforcement.css:240`
- Evidence: `(.btn) > .form-select, [role="search"].d-flex:has(.btn) > .form-control, [role="search"].d-flex:has(.btn) > .form-select { max-width: 28rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-tokens.css:1636`
- Evidence: `ax-width, breathable padding */ .wizard-container, [data-shell-page="onboarding-wizard"], [data-rmc-onboarding-page="1"] { max-width: 880px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-tokens.css:1714`
- Evidence: `.wizard-step-label { max-width: 11ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-tokens.css:1757`
- Evidence: `.wizard-step-description { max-width: 60ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-tokens.css:1808`
- Evidence: `nboarding-wizard"] h1 + .text-muted, [data-rmc-onboarding-page="1"] h1 + .text-muted, .wizard-container h1 + .text-muted { max-width: 60ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-tokens.css:2424`
- Evidence: `.admin-login-card { max-width: 420px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-tokens.css:2668`
- Evidence: `/* ----- CONFIRM DIALOG (bespoke .confirm-dialog pattern) ----- */ .confirm-dialog, [data-rmc-confirm-dialog] { max-width: 440px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-tokens.css:4269`
- Evidence: `.rmc-kbd-cheatsheet__filter { max-width: 20rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-tokens.css:4547`
- Evidence: `.rmc-mapping__explain p { max-width: 28rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/design-tokens.css:5001`
- Evidence: `.rmc-empty-state__body { max-width: 32rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/hub-premium.css:47`
- Evidence: `.hub-page .hub-copy { max-width: 52ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/lux-workspace.css:328`
- Evidence: `.rmc-lux-intro__summary { max-width: 56ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/lux-workspace.css:1304`
- Evidence: `.rmc-lux-error__panel { max-width: 480px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/manager-control-plane.css:87`
- Evidence: `.cp-hero-copy { max-width: 62rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/manager-control-plane.css:1171`
- Evidence: `.cp-sidebar-col.cp-sidebar-compact { max-width: 4rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/manager-control-plane.css:1217`
- Evidence: `.cp-keyboard-help-panel { max-width: 400px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/manager-login.css:69`
- Evidence: `.manager-login-card,   .admin-login-card { max-width: 440px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/manager-login.css:76`
- Evidence: `.manager-login-card,   .admin-login-card { max-width: 460px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/marketing-home.css:844`
- Evidence: `.rmc-mkt-sticky-cta__inner { max-width: 64rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/marketing-static-bundle.css:45`
- Evidence: `.detail-headline { max-width: 24ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/marketing-static-bundle.css:49`
- Evidence: `.detail-subheadline { max-width: 68ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/micro-feedback.css:70`
- Evidence: `.glass-tooltip.teacher-hover-bubble { max-width: 280px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/next-action-strip.css:101`
- Evidence: `.rmc-nas-chip-desc { max-width: 42ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/onboarding-migration.css:242`
- Evidence: `doff page (.omig-handoff)    ───────────────────────────────────────────────────────────────────────── */  .omig-handoff { max-width: 760px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/org-chart.css:18`
- Evidence: `.org-chart-card { max-width: 140px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/owner-console.css:9`
- Evidence: `e in light    AND dark themes automatically.    ============================================================ */  .rmc-oc { max-width: 1200px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/owner-first-login.css:27`
- Evidence: `.rmc-ofl-card { max-width: 520px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/patterns.css:137`
- Evidence: `/* main content area */ [data-rmc-aesthetic="v2"] main.main { max-width: 1400px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/patterns.css:844`
- Evidence: `======================================================================== */ [data-rmc-aesthetic="v2"] .report-card-paper { max-width: 820px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/patterns.css:1062`
- Evidence: `[data-rmc-aesthetic="v2"] .login-brand-side h1 { max-width: 520px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/patterns.css:1068`
- Evidence: `[data-rmc-aesthetic="v2"] .login-brand-side p { max-width: 480px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/patterns.css:1075`
- Evidence: `[data-rmc-aesthetic="v2"] .login-brand-side .testimonial { max-width: 420px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/patterns.css:1095`
- Evidence: `[data-rmc-aesthetic="v2"] .login-form { max-width: 380px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/patterns.css:1463`
- Evidence: `e-archetype="role-home"] > .container-lg, [data-rmc-aesthetic="v2"] [data-page-archetype="role-home"] > .container-fluid { max-width: 1400px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/patterns.css:1691`
- Evidence: `[data-rmc-aesthetic="v2"] .rmc-empty-state .rmc-empty-message { max-width: 480px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-base-bundle.css:220`
- Evidence: `.error-container { max-width: 600px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-base-bundle.css:300`
- Evidence: `main { max-width: 38rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-base-bundle.css:343`
- Evidence: `main { max-width: 38rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-base-bundle.css:498`
- Evidence: `main { max-width: 480px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-base-bundle.css:525`
- Evidence: `p { max-width: 32rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-control-plane-bundle.css:73`
- Evidence: `/* Preview wrapper */   .theme-experience-preview-wrap { max-width: 1120px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-portal-bundle.css:1970`
- Evidence: `/* ========== templates/parent/link_child_wizard.html ========== */ .wizard-container { max-width: 600px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-portal-bundle.css:2162`
- Evidence: `/* ========== templates/parent/results.html ========== */ .results-page { max-width: 56rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-portal-bundle.css:2322`
- Evidence: `e.html ========== */ /* block 1 */ /* KB article: clean layout, avoid jammed text */   .kb-article-page .article-content { max-width: 72ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-portal-bundle.css:2659`
- Evidence: `/* Preview wrapper */   .theme-experience-preview-wrap { max-width: 1120px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-portal-bundle.css:2691`
- Evidence: `/* ========== templates/student/onboarding_wizard.html ========== */ .wizard-container { max-width: 700px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/phase2-portal-bundle.css:2855`
- Evidence: `/* ========== templates/teacher/onboarding_wizard.html ========== */ .wizard-container { max-width: 600px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/platform-high-end.css:319`
- Evidence: `[data-dashboard-page] .dashboard-subtitle, [data-dashboard-page] .section-title, .cp-hero-copy { max-width: 60ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-base-shell.css:157`
- Evidence: `.topbar-search.header-search-container { max-width: 520px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-base-shell.css:585`
- Evidence: `.topbar-search.header-search-container { max-width: 390px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-base-shell.css:732`
- Evidence: `#portalHeader .topbar-search.header-search-container { max-width: 460px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-base-shell.css:761`
- Evidence: `#portalHeader .topbar-lang-btn { max-width: 112px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-base-shell.css:766`
- Evidence: `#portalHeader .topbar-lang-btn > span { max-width: 68px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-base-shell.css:773`
- Evidence: `#portalHeader .topbar-username { max-width: 96px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-ui-components.css:892`
- Evidence: `.dashboard-empty-message { max-width: 400px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-ui-components.css:898`
- Evidence: `.dashboard-empty-purpose { max-width: 400px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-ui-components.css:1310`
- Evidence: `/* --- from templates/components/global_search.html --- */ .global-search { max-width: 400px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-ui-components.css:2084`
- Evidence: `/* block 2 */ /* Toast notification styles */ .notification-toast { max-width: 400px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/portal-ui-components.css:2528`
- Evidence: `.toast-notification { max-width: 420px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-account-surface.css:346`
- Evidence: `.rmc-account-mfa-qr-wrap img { max-width: 15rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-admin-changelist-live.css:152`
- Evidence: `body.admin-manager-shell.change-list #result_list th, body.admin-manager-shell.change-list #result_list td { max-width: 24rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-admin-changelist-live.css:172`
- Evidence: `.change-list #result_list td.action-checkbox, body.admin-manager-shell.change-list #result_list td.action-checkbox input { max-width: 2.75rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-admin-mirror.css:708`
- Evidence: `ger-login-civic` chrome.    ============================================================ */ .rmc-admin-mirror-civic-form { max-width: 480px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-admin-v1-200x.css:313`
- Evidence: `.cp-hero__lede { max-width: 720px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-admin-v1-200x.css:535`
- Evidence: `.cp-section__search { max-width: 420px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-admin-v1-200x.css:1328`
- Evidence: `.cp-empty__hint { max-width: 360px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-analytics-viz.css:138`
- Evidence: `.rmc-viz-tooltip { max-width: 14rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-assist-dock.css:403`
- Evidence: `/* ===== v4.00.93 Wave C — power chip landings + prefs UI ================== */  .rmc-assist-power { max-width: 720px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-back-to-top.css:306`
- Evidence: `-back-to-top:hover .rmc-back-to-top__caption,   .back-to-top-btn.rmc-back-to-top:focus-visible .rmc-back-to-top__caption { max-width: 8rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-backend-admin-bento.css:97`
- Evidence: `.rmc-admin-zone-intro__text { max-width: 62ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-civic-footer.css:44`
- Evidence: `.rmc-civic-footer__inner { max-width: 1280px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-civic-footer.css:249`
- Evidence: `                    */ /* ------------------------------------------------------------------ */ .rmc-civic-footer__legal { max-width: 1100px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:1744`
- Evidence: `.feature-cat-tab__label { max-width: 12ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:1831`
- Evidence: `lve  * to the dark CP palette by default; portal shell tokens reflow automatically. */ .rmc-page--migration-cloud-intake { max-width: 86rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:3071`
- Evidence: `.rmc-mc-customer-page { max-width: 80rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:3434`
- Evidence: `/* schoolops/operator/meal_plan_analytics page-specific modifiers */ .rmc-page--operator-meal-plan-analytics { max-width: 80rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:3644`
- Evidence: `.rmc-lede--sm { max-width: 60ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:3703`
- Evidence: `.rmc-os-page__inner { max-width: 80rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:3713`
- Evidence: `.rmc-page--canonical-template-picker, .rmc-page--migration-connector { max-width: 80rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:3905`
- Evidence: `tivate, .rmc-page--migration-cloud-command-center, .rmc-page--operator-audit-dashboard, .rmc-page--operator-dsar-runbook { max-width: 80rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:4081`
- Evidence: `-operator-tokens, .rmc-page--operator-webhook-audit, .rmc-page--operator-webhooks, .rmc-page--operator-webhook-subscribe { max-width: 80rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:4276`
- Evidence: `.rmc-page--maa-v2-promotion, .rmc-page--migration-cloud-health { max-width: 80rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-class-grammar.css:5982`
- Evidence: `ontext.mfa_nudge_context on every shell    when a required user is let through instead of hard-walled. */ .rmc-mfa-nudge { max-width: 64rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cockpit-skin-v8.css:471`
- Evidence: `.rmc-empty-state__desc { max-width: 42ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cool-apple-polish.css:385`
- Evidence: `y outside the manager platform header. */ .cp-navbar:not([data-rmc-shell-header="control-plane"]) .cp-topbar-search-wrap { max-width: 520px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-copilot-rail.css:43`
- Evidence: `.rmc-copilot-rail__context-tenant { max-width: 140px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-200x.css:577`
- Evidence: `.lx-world-lab__note { max-width: 920px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-200x.css:755`
- Evidence: `.lx-world__glass-dock-metric { max-width: 12rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-200x.css:1615`
- Evidence: `.lx-world__holo-cell-spark { max-width: 34px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-200x.css:2062`
- Evidence: `.lx-world__void-zone--mr { max-width: 160px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-200x.css:2063`
- Evidence: `.lx-world__void-zone--bl { max-width: 240px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-200x.css:2064`
- Evidence: `.lx-world__void-zone--br { max-width: 190px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-200x.css:3551`
- Evidence: `.lx-copilot__empty-lede { max-width: 28ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-200x.css:3732`
- Evidence: `tate: collapse to a slim title-only pill, retain ability to expand. */ .lx-notebook[data-rmc-notebook-state="minimized"] { max-width: 240px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-200x.css:4589`
- Evidence: `.rmc-cp-landing-mode__tabs { max-width: 28rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-globe-landing-frame-fit.css:137`
- Evidence: `-main="control-plane"] .cp-layout[data-rmc-cp-globe-landing="1"] .rmc-globe-deck-v2__globe-cell .lx-world__void-zone--mr { max-width: 150px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-globe-landing-frame-fit.css:141`
- Evidence: `-main="control-plane"] .cp-layout[data-rmc-cp-globe-landing="1"] .rmc-globe-deck-v2__globe-cell .lx-world__void-zone--br { max-width: 175px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-header-200x.css:84`
- Evidence: `.cp-header__row--utility .rmc-platform-header__command { max-width: 560px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-header-200x.css:784`
- Evidence: `body.admin-manager-shell .cp-header__row--utility .cp-brand, body.control-plane-shell .cp-header__row--utility .cp-brand { max-width: 320px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-header-200x.css:814`
- Evidence: `--utility .rmc-platform-header__command, body.admin-manager-shell .cp-header__row--utility .rmc-platform-header__command { max-width: 280px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-stacked-header.css:116`
- Evidence: `.rmc-wfp-header-slot .rmc-wfp-inline__copy { max-width: 9rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-cp-stacked-header.css:131`
- Evidence: `.rmc-wfp-header-slot .rmc-wfp-bar { max-width: 9rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-email-civic.css:59`
- Evidence: `.rmc-email__container { max-width: 600px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-isomorphic-grid.css:352`
- Evidence: `.rmc-iso-panel-empty__message { max-width: 28rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-list-bulk-select.css:116`
- Evidence: ` — shown on surfaces without the copilot    rail, so the bulk action is useful everywhere. */ .rmc-copilot-answer-dialog { max-width: 36rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-long-page-grammar.css:259`
- Evidence: `/* Campus / school workspace switcher (multi-tenant header). */ .rmc-campus-switcher__select { max-width: 14rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-long-page-grammar.css:484`
- Evidence: `.rmc-empty__message, .dashboard-empty-message { max-width: 36ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-nav-sidebar.css:358`
- Evidence: `/* Named CP / operator grid primitives — reflow when sidebar is wide or rail-narrow */ @container rmc-shell-canvas ( { max-width: 720px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-nav-sidebar.css:386`
- Evidence: `@container rmc-shell-canvas (min-width: 721px) and ( { max-width: 1080px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-notification-corner.css:24`
- Evidence: `.rmc-corner-notification { max-width: 420px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-operational-center-frame.css:223`
- Evidence: `body.portal-body-with-layout, body.manager-portal-bridge)    :is(#main-content, .portal-page-body)    .cp-steering__copy { max-width: 72ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-operator-tools-tray.css:369`
- Evidence: `.rmc-operator-tools__tray-empty-lede, .rmc-operator-tools__panel-empty-lede { max-width: 22rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-page-personality.css:277`
- Evidence: ` row. Domain-tinted top border.    ============================================================ */  .rmc-hover-inspector { max-width: 320px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-pagination-grammar.css:149`
- Evidence: `.rmc-pagination__count { max-width: 24rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-platform-chrome-layout.css:101`
- Evidence: `.cp-navbar .cp-topbar-bell__badge, [data-rmc-platform-header="manager"] .cp-topbar-bell__badge { max-width: 2.1rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-platform-inner-pages.css:142`
- Evidence: `.rmc-section-nav--horizontal .rmc-section-nav__list a { max-width: 14rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-platform-vertical-compact.css:203`
- Evidence: `body[data-rmc-notebook-footer-dock="1"] .rmc-footer-notebook-anchor .lx-notebook[data-rmc-notebook-state="minimized"] { max-width: 280px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-setup-surface.css:93`
- Evidence: `.rmc-setup-surface__lede { max-width: 56ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-setup-surface.css:481`
- Evidence: `.rmc-launch-ceremony__lede { max-width: 42ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-signup-v2.css:31`
- Evidence: `.rmc-signup-type-card { max-width: 140px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-signup-v2.css:95`
- Evidence: `.rmc-signup-type-cards--language .rmc-signup-type-card { max-width: 220px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-signup-v2.css:147`
- Evidence: `.rmc-signup-done__card { max-width: 560px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-signup-v2.css:341`
- Evidence: `/* Multi-select hint text under the field label. */ .rmc-signup-field__help { max-width: 72ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-tenant-activation-surfaces.css:58`
- Evidence: `/* Teacher — refer an incident form */ .rmc-discipline-refer { max-width: 640px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-tenant-canvas-100x.css:532`
- Evidence: `.tp-section__lede { max-width: 64ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-tenant-dashboard-v2.css:938`
- Evidence: `.tp-empty__hint { max-width: 360px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-tenant-header-100x.css:91`
- Evidence: `body.portal-body-with-layout:not(.control-plane-shell) #preview-header-brand { max-width: 240px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-tenant-header-100x.css:114`
- Evidence: `body.portal-body-with-layout:not(.control-plane-shell) #portalHeader .topbar-search { max-width: 560px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-tenant-header-100x.css:403`
- Evidence: `#portalHeader #preview-header-brand { max-width: 280px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-tenant-header-100x.css:531`
- Evidence: `#portalHeader .topbar-search.header-search-container { max-width: 345px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-tenant-header-100x.css:554`
- Evidence: `#portalHeader .topbar-search.header-search-container { max-width: 260px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-tenant-performance.css:47`
- Evidence: `.rmc-tperf__bar-fill { max-width: 48px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-trust-pillars.css:346`
- Evidence: `.lx-trust-pillars__time { max-width: 9.5rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-user-preferences.css:48`
- Evidence: `.rmc-prefs-locale__lead { max-width: 52ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-wizard.css:81`
- Evidence: `.rmc-wizard-grid { max-width: 1280px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-wizard.css:142`
- Evidence: `.rmc-wizard-stepper__bar { max-width: 48px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/rmc-world-class-experience.css:49`
- Evidence: `.rmc-wcx-hero__copy { max-width: 64ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/root-base-shell.css:30`
- Evidence: `:root { max-width: 1320px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/setup-studio-onboarding.css:66`
- Evidence: `.setup-studio-subtitle { max-width: 44rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/site-settings-preview.css:67`
- Evidence: `.preview-device { max-width: 940px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/site-settings-preview.css:131`
- Evidence: `.preview-device[data-preview-mode="desktop"] { max-width: 940px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/site-settings-preview.css:142`
- Evidence: `.preview-device[data-preview-mode="tablet"] { max-width: 680px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/site-settings-preview.css:153`
- Evidence: `.preview-device[data-preview-mode="mobile"] { max-width: 360px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/statement-header.css:106`
- Evidence: `.statement-logo img, .navbar-brand img, .brand-logo img, .header-logo img { max-width: 160px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/statement-header.css:175`
- Evidence: `.statement-header .navbar-brand,   #portalHeader .navbar-brand,   .statement-logo,   .header-logo { max-width: 200px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/studio-command-deck.css:21`
- Evidence: `.studio-command-deck__lede { max-width: 42rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/studio-mode-hero.css:23`
- Evidence: `.studio-mode-hero__purpose { max-width: 42rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/studio-operator-toolbar.css:27`
- Evidence: `.studio-operator-toolbar__select { max-width: 24rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/studio-shell-layout.css:225`
- Evidence: `d a 3-row band). One row now.    Reusable via templates/studio_os/partials/studio_command_pill.html. */ .studio-cmd-pill { max-width: 22rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/teacher-dashboard-modern.css:839`
- Evidence: `.org-chart-card { max-width: 140px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/tenant-command-workspace.css:150`
- Evidence: `.rmc-command-header p { max-width: 80ch }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/tenant-studio-day1.css:26`
- Evidence: `.rmc-day1-act-header { max-width: 42rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/tenant-studio-day1.css:154`
- Evidence: `vation tokens as the brand-reveal frame  * above so the two compositions read as one surface.  */  .rmc-day1-logo-upload { max-width: 36rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/tenant-studio-day1.css:507`
- Evidence: `/* ----- Act 3: lock-in ----- */  .rmc-day1-lock-summary { max-width: 36rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/tenant-studio-wizard.css:59`
- Evidence: `.tenant-studio-wizard .tenant-studio-form-card { max-width: 42rem }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/tooltips.css:21`
- Evidence: `[data-tooltip]::after { max-width: 280px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/tooltips.css:48`
- Evidence: `.runmycampus-tooltip-bubble { max-width: 280px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.

### LOW - css_width_cap_review
- Path: `static/css/ultra-luxury-ui-system.css:237`
- Evidence: `body.dashboard-page-parent .parent-dashboard .container-lg { max-width: 1200px }`
- Recommendation: Confirm this cap is not applied to Studio, admin, tenant configuration, or preview work surfaces.
