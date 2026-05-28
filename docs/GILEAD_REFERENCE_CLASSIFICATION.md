# Gilead reference classification (Phase 12)

**Policy:** Product-facing surfaces use **RunMyCampus** naming. Historical “Gilead” may remain only where listed below.

| Class | Examples | Action |
|-------|-----------|--------|
| **Archive / root_history** | `docs/archive/root_history/*` | **Docs only** — historical context; no runtime impact. |
| **Migrations (historical)** | `0012_seed_default_gilead_school.py`, `0013_link_default_admin_to_gilead.py`, theme/report seed migrations | **Migration only** — do not rewrite shipped migrations; follow-up data migrations if defaults must change in DB. |
| **Operational docs** | `CURRENT_SETUP_AND_GOOD_TO_GO.md`, old setup guides | **Docs only** — update or mark **DEPRECATED** when misleading. |
| **Lint-scoped runtime** | `apps/*`, `templates/*`, `config/*` (excluding `migrations/`, `tests/`, `docs/`, `management/commands/` per `lint_gilead_residue.py`) | **Must be clean** — `python scripts/lint_gilead_residue.py` = **PASS** (includes JSON under `apps/` such as `backlog_unlock_registry.json`). |
| **Management commands** | *(removed)* | Use `python manage.py seed_demo_tenant_users` (optional `--school-slug=` / `--username-prefix=`). |
| **Tests** | `apps/**/tests/**`, top-level `tests/**`, Playwright staging examples | **Test-only** — optional neutralization; not lint-gated. |
| **JSON / YAML fixtures** | `apps/**/fixtures/**` | **Fixture-only** — seed data; not HTTP surfaces; full-tree verifier allowlist path. |
| **Locale catalogs** | `locale/**` (`*.po`; compiled `*.mo` not text-scanned) | **Legacy msgids** — refresh with `sync_i18n_catalog`; product strings still must pass `lint_gilead_residue.py` on runtime paths. |
| **Inventory / audit scripts** | `generate_platform_inventory.py` “gilead” match counts; `.github/workflows/*` steps that run `scripts/verify_gilead_full_tree_classification.py`; tracked `var/**` verifier logs; vendored dictionaries under `static/vendor/**` | **Tooling** — not user-facing; full-repo metric ≠ lint-scoped runtime bar. |

**Single execution source:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (§2.2 Gilead residue purge + §0 for scores).

**Session audit (subordinate):** [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md) — Phase 12 block; does not replace the SOT.

## Corpus hygiene program (PARTIAL — gross corpus vs live bar)

Premium maturity treats **Gilead** as **PARTIAL** until optional corpus shrink is exhausted. Use **three different bars**—do not conflate them:

| Bar | Meaning | Gate |
|-----|---------|------|
| **A. Lint-scoped runtime** | No `gilead` substring on live product paths (apps/templates/config/fixtures/render, etc., per script). | `python scripts/lint_gilead_residue.py` → **PASS** (merge/release). |
| **B. Full-tree buckets** | Every text hit lives in an **allowed path class** (docs, migrations, tests, scripts, CI, `.cursor`, commands, fixtures, locale). | `python scripts/verify_gilead_full_tree_classification.py` → **PASS**. |
| **C. Gross inventory** | Repo-wide count in `docs/generated/platform_inventory.json` / MD. | **Trend only** — not the same as A or B; use for honesty, not “done.” |

**Hygiene phases (sequenced; do not rewrite shipped migrations for branding alone):**

1. **P0 — Live surfaces:** Keep A green; fix any regression immediately.
2. **P1 — Classified corpus:** Keep B green; if a new path class is needed, update **this table** + verifier allowlist in code in one PR.
3. **P2 — Subtractive docs:** Archive or neutralize misleading **operational** rows (rename headings, DEPRECATED banners); prefer subtractive edits. No new master plans—extend SOT §11.4 + autonomous log **A–F** only. *Example (done):* [CURRENT_SETUP_AND_GOOD_TO_GO.md](CURRENT_SETUP_AND_GOOD_TO_GO.md) frames **RunMyCampus** as the product and treats `gilead-school` as historical DB slug/migration context only.
4. **P3 — Historical SQL:** Migrations stay **append-only** unless a **data** migration is product-required; never edit old migration files for cosmetic rename.

**Cadence:** Run A + B on the pre-deploy / phases-3–11 bundle; regen inventory when the release train prescribes `--write`.

**Last A+B record (repo cadence slice):** SOT §11.4 **batch 256** (**2026-03-31**) — `lint_gilead_residue.py` + `verify_gilead_full_tree_classification.py` + `manage.py test` `apps.platform_runtime.tests.test_gilead_full_tree_classification_helpers` + `apps.platform_runtime.tests.test_gilead_residue_lint` **PASS** (`files_with_hit=148` at that run). `verify_doc_plan_density_discipline.py` **PASS**; `generate_platform_inventory.py --write` + `--check` **PASS** after SOT/log/classification updates. *Numbering:* SOT **batch 257** is **Phase B**; **batch 258** is **doc / plan density** cadence slot when present; **batch 259** is **Gilead** **A+B** cadence slot when present — **not** this **A+B** bar until **259** ships.

**When to edit this doc:** Change the table only when you intentionally add or retire a **bucket** of allowed references (new path class or policy). For ordinary content or migration edits that stay within existing classes, keep **`lint_gilead_residue.py`** and **`verify_gilead_full_tree_classification.py`** green; no classification doc update required unless the verifier’s buckets or allowlists change in code.
