# Powerhouse Plan — Verification Checklist

Verified on codebase to confirm each plan item is implemented.

## I. Architecture & multi-tenancy
- [x] **Nested / multi-campus:** `School.hierarchy_path`, `get_descendants`/`get_ancestors`, `Campus` in `apps/schools/models.py`
- [x] **Per-tenant quotas:** `TenantQuotaLimit`, `TenantApiUsage`, `_check_tenant_quota_limit`, `throttle_tenant_request` in `apps/api/rate_limit.py`; `/super/usage/` in `super_urls.py` and `super_views.super_usage`

## II / XI / XII. Academics, vocational, migration
- [x] **Rollover:** `RolloverProposal`/`RolloverProposalItem` in accounts; `prepare_rollover_proposal`/`apply_rollover_proposal` tasks; `rollover_queue`, `rollover_proposal_detail` views and URLs
- [x] **Migration wizard:** `migration_wizard` view, `accounts:migration_wizard` URL, `accounts/migration_wizard.html`
- [x] **Employer portal:** `EmployerProfile`, `employer_dashboard`, `employer_student_transcript` in people; employer_views, portal URLs
- [x] **Dual transcript:** `StudentProfile.transcript_track`, `dual_transcript`/`transcript_track` in reports context, employer transcript template
- [x] **LMS scaffold:** `apps/academics/lms_attendance.py` — `LmsAttendanceProvider`, `LmsAttendanceRecord`, `get_lms_attendance_provider`

## IV. Compliance & localization
- [x] **MoE export:** `build_regulatory_export` in reports/services; `regulatory_export` view with POST, `reports/regulatory_export.html` with Run export form and `export_result`
- [x] **GDPR:** `mask_pii_for_region` in compliance/privacy.py; `purge_compliance_data` with `--region`; `docs/COMPLIANCE_RETENTION.md`

## V. Parent wallet
- [x] **Wallet UI:** `parent_wallet` view, `portal:parent_wallet` URL, `templates/parent/wallet.html`; sidebar "Wallet" in `partials/portal_sidebar.html`; `ParentWallet`, `WalletTransaction` in finance

## VI. Communication
- [x] **WhatsApp:** `WhatsAppProvider`, `send_whatsapp` in communication/channels.py; `OutboundMessageQueue`, `FeedItem` in admin; `process_outbound_message_queue` task in communication/tasks.py
- [x] **Push:** `PushProvider`, `send_push` in channels.py; `MobileDevice.push_token`, MobileDeviceViewSet
- [x] **Feed:** `FeedItem` model; `parent_feed`, `teacher_feed` views; `parent/feed.html`, `teacher/feed.html`; sidebar Feed links (parent + teacher)

## VII. Conflict & CDN
- [x] **Conflict:** Evals `resolve_offline_conflict_view`, `evals/resolve_offline_conflict.html`; `docs/CONFLICT_RESOLUTION.md`
- [x] **CDN:** `docs/DEPLOY_CHECKLIST.md` section "CDN / edge (Plan VII)"

## VIII. Blockchain
- [x] **Credentials:** `ReportDocumentHash.on_chain_status`, `blockchain_tx_id` in reports/models + migration 0011; `apps/reports/credential_verifier.py` (CredentialVerifier, verify_credential_hash, get_credential_verifier)

## X. Billing
- [x] **Trial & dashboard:** `School.trial_end_date` (migration 0018); `billing_dashboard` view, `super:billing_dashboard` → `/super/billing/`; `docs/BILLING_STRIPE.md`

## XVI. Alumni, inventory, transport, tours, analytics
- [x] **Alumni:** `alumni_list` view, `accounts:backend_alumni_list` → `/backend/alumni/`; `backend_student_list` filters by `status=ALUMNI` via `?status=ALUMNI`
- [x] **Inventory:** `InventoryItem`, `Route`, `Stop`, `Bus` in schools/models.py + migration 0019; admin in schools/admin.py
- [x] **Tours:** `TourStep` in siteconfig/models.py + migration 0108; TourStepAdmin in siteconfig/admin.py
- [x] **Analytics:** `FeatureUsageEvent` in siteconfig; `track_event()` in `siteconfig/feature_usage.py`; FeatureUsageEventAdmin

## XVII. Adaptive
- [x] **Scaffold:** `apps/academics/adaptive_scaffold.py` — `get_leaderboard`, `award_badge_for_achievement` (uses people.Badge/BadgeType)

---

**Result:** All plan items verified present in codebase. Status document `POWERHOUSE_PLAN_STATUS.md` is accurate.
