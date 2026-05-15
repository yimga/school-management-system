# Improvement work → Main: deploy readiness

This checklist confirms that **everything from the improvement work** (report block by debt, arrears carry-forward, GCE export, ITC/ATC, Site Settings/Feature Control, etc.) is **properly wired on main** and will deploy without issues.

---

## 1. What was implemented (all on main)

| Area | What | Wired / integrated |
|------|------|--------------------|
| **Report block by debt** | `student_has_financial_clearance()` in reports; block term/annual PDF/CSV and share when fees owed | `apps/reports/services.py`, `views.py`; `backend_feature_flags.block_report_download_if_outstanding_balance` (default True) |
| **Report block by returns** | `student_has_outstanding_returns()`; block when unreturned resources | Same views; flag `block_report_download_if_outstanding_returns` (default False) |
| **Arrears carry-forward** | `carry_forward_arrears()` in finance; rollover checkbox creates opening-balance invoices | `apps/finance/services.py`; `apps/accounts/views.py` (rollover_year); flag `carry_forward_arrears_on_rollover` |
| **GCE export** | DATE_OF_BIRTH DD/MM/YYYY, CIN, EXAM_TYPE, MOMO_TRANS_ID, specialty_code in candidates.csv | `apps/accounts/views_certification.py` |
| **ITC/ATC pass rule** | `PromotionRule.use_technical_promotion_rule`; Subject.Category.RELATED; 5 subjects, 2 Professional + 1 Related | `apps/reports/models.py`, `services.py`; `apps/academics/models.py` (Subject.RELATED) |
| **Form 4 GCE block** | `Classroom.gce_eligible`; bulk-add candidates only shows GCE-eligible classes | `apps/academics/models.py`; `apps/accounts/views_certification.py` (form queryset) |
| **Feature Control** | New backend flags in panel: block report (debt/returns), carry forward arrears | `apps/siteconfig/views_feature_control.py` (FEATURE_CATEGORIES, _get_site_features, _apply_form_to_site) |
| **Site Settings** | Context processors, middleware, breadcrumbs, customizer, feature control URLs | `config/settings.py` (TEMPLATES, MIDDLEWARE); `config/urls.py`; `apps/siteconfig/` |

---

## 2. Migrations (must apply on deploy)

These migrations exist and must run on first deploy after merge:

- **reports:** `0007_promotionrule_use_technical_promotion_rule.py`
- **academics:** `0020_classroom_gce_eligible.py`
- **siteconfig:** no new migration for the new backend flags (they live in JSON `backend_feature_flags` with defaults in code)

**Action:** Release Command (or build) runs `python manage.py migrate --noinput` so these apply.

---

## 3. Settings and config (no change required)

- **backend_feature_flags** defaults are in `apps/siteconfig/models.default_backend_feature_flags()` (block_report_download_if_outstanding_balance, carry_forward_arrears_on_rollover, etc.). No env vars needed; admins can toggle in Feature Control.
- **Context processors** and **middleware** for siteconfig are already in `config/settings.py`.
- **URLs:** `siteconfig/` included in `config/urls.py`; feature-control, customizer, preferences all resolve.

---

## 4. Deployment checklist (Render / production)

- [ ] **Branch:** Deploy from **main** (all improvement work merged).
- [ ] **Environment:** `DATABASE_URL` (Postgres), `ADMIN_PASSWORD` (for seed_render_users), `SECRET_KEY`, `ALLOWED_HOSTS`.
- [ ] **Release Command:**  
  `.venv/bin/python manage.py migrate --noinput && .venv/bin/python manage.py seed_render_users`  
  (Or equivalent so migrate runs before the app starts and users exist.)
- [ ] **Build:** `build.sh` runs migrate + collectstatic. If Render runs migrate at build time without DATABASE_URL, migrate may fail at build; in that case rely on **Release Command** for migrate and keep build to install + collectstatic only if needed.
- [ ] **Smoke test (CI):** `.github/workflows/smoke.yml` runs on push/PR to main; 17 URL tests including `siteconfig:feature_control_panel`. No DB required.
- [ ] **After deploy:** Log in, open `/admin/`, `/siteconfig/feature-control/`, `/authentication/backend/`, rollover and report-download flows; confirm no 500s.

---

## 5. Quick verification (local or CI)

```bash
python manage.py check
python manage.py test apps.accounts.tests.test_smoke_urls -v 1
```

If the DB is available:

```bash
python manage.py migrate --noinput
python manage.py seed_render_users   # or ensure_superuser + create_teacher_parent_accounts
```

---

## 6. Docs that reference this work

- **test_finding.md** — GAP-001/GAP-002 and “What’s missing” table updated to “Yes” for implemented items.
- **docs/SITE_SETTINGS_AND_SYSTEM_CONFIG_WIRING.md** — How SiteSettings and Feature Control are wired.
- **docs/MAIN_BRANCH_HEALTH.md** — Overall main-branch health and smoke test.
- **docs/CREDENTIALS_AND_RESTORE.md** — Restore users after deploy; use seed_render_users on Render.

---

**Summary:** All improvement work is implemented and wired on main. New migrations (reports 0007, academics 0020) are in the tree and will apply when migrate runs. Feature Control and Site Settings are integrated; smoke tests include feature-control URL. Deploy from main with migrate + seed_render_users in Release Command and the usual env vars — no extra config is required for the new features to work.
