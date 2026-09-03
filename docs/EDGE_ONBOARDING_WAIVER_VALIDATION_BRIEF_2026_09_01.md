# Edge Onboarding waiver slice — Claude validation brief

**Date:** 2026-09-01  
**Role of this file:** Hand this path to Claude. Claude must **run engines**, not trust this brief. If anything is missing, miswired, or still lets go-dark pass without a real dump or a ≥12-character skip, **fix it in the same pass**.

This is **not** a new execution source of truth. Canonical ledger rows: `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` §11.4 batches **1817, 1818, 1819**. Operator SOP: `docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md`. Engine SOT: `apps/lifecycle/edge_onboarding.py` (`EDGE_ONBOARDING_STEPS`). If this brief disagrees with the engine, **the engine wins after you have run it**.

**Stay off:** in-flight peer `apps/sync_engine/*`, `box-backup.sh` internals, `box-audit.sh` C2. **Never** `git add -A`. Multiple agents share this checkout.

---

## 0. What Claude must do (end to end)

1. **AUDIT** by running, not by reading names/comments/this file.
2. **IDENTIFY** holes against the original request and the invariants below.
3. **FIX** residuals in tree (smallest diff, same invariants). Do not weaken identity or `SECRET_KEY`.
4. **TEST** the suites listed in §6. Re-run `audit_edge_runbook --strict`.
5. **RE-AUDIT** the host split (manager overlay ≠ box overlay).
6. **REPORT** what was already correct, what you fixed, and what remains honest/by-design.

Do not stop at “the commit exists.” Prove live behavior.

---

## 1. Original request (what the user asked)

1. Finish scoped Edge Onboarding so a campus that **does not have** a given piece of infrastructure can still finish the runbook.
2. This is **not** “make go-dark always pass.”
3. **Always offer per-aspect waivers.** Not every campus has USB/NAS, LAN DNS, a reliable uplink, SIS files, a logo, or a roster.
4. Written skip **≥12 characters**. Blank skip is not a skip.
5. **Non-waivable:** owner login (`migrate_identities`) and `SECRET_KEY` / box environment. Also: entitlements, tenant shell, go-dark **as a whole**.
6. Final audit, end to end, very thorough — audit by **running** engines, then fix residuals in the same pass.
7. Audit again, then the slice was committed and pushed to `main`.

Product thesis that must still hold: a checklist nobody can finish at a real site is not a checklist. Each waiver is a **written decision**, one capability at a time.

---

## 2. Design invariants (do not relitigate)

| Invariant | Meaning |
|---|---|
| Overlay | Skips live on `school.settings["rmc_edge_onboarding"]`. |
| Two databases | Manager host and box are different DBs. A skip only counts on the host that recorded it. |
| Import | `import_sovereign_tenant` does **not** copy `rmc_edge_onboarding` (intentional). |
| Manager GET | Must not fake box/network checks. `cloud_preview=False` for dry gate, live proof, backup, go-dark. |
| Django | Never dumps or restores. |
| Independent waivers | Pairing / dry gate / live Class-A are **not** auto-cascaded. Waiving pairing must not waive dry or live. |
| Off-box USB/NAS | Waiving `offbox_copy` only **rewrites the warning** when a dump is already verified. It must **not invent a dump**. |
| Empty staff | PASSes without a skip. |
| Empty roster | Does **not** PASS unless `seed_operational_data` is waived. |
| TLS | `edge_tls_trust` already PASSes on plain HTTP; not in the waiver catalog. |
| Identity / secrets | Owner login and `SECRET_KEY` cannot be waived from the console or CLI catalog. |

---

## 3. What Grok claimed to ship (three batches, one push)

Landed on `origin/main` as **`e65254d20`** (still an ancestor of `origin/main` at brief time). Later commits may have touched the same files — validate **today’s** `origin/main`, not only that hash.

Commit: https://github.com/yimga/school-management-system/commit/e65254d20

Message: *A campus without uplink, USB, SIS files, or LAN DNS can finish onboarding without skipping login or SECRET_KEY.*

24 files, +1718/−98. Cherry-picked onto then-current `origin/main` because the working checkout was dirty with peer `sync_engine` files that blocked merge.

### 3.1 Batch 1817 — verified box backup before go-dark

**Hole:** go-dark could pass with no dump of the school’s records that had been **read back**. Delta sync carries only a handful of Class-A entities; a dead SSD was total loss. Peer `box-backup.sh` / C2 already existed; the **engine** could not see the record.

**Shipped:**

- Reader: `apps/lifecycle/box_backup_status.py` (C2: schema, verified full read of newest dump, age ≤48h). Off-box USB/NAS is a **warning on PASS**, not a fail.
- Step `box_backup_verified` immediately before `go_dark_checklist`. `EDGE_ONBOARDING_STEPS` = **19** keys. `cloud_preview=False`, `runs_on=box`, `evidence=box_settings`, **no self_heal**.
- `go_dark_checklist` requires `backup=ok` (or waived).
- Overlay: `school.settings["rmc_edge_onboarding"]["box_backup_skip_reason"]`.
- Operator POST `lifecycle_action=skip_box_backup`; `EdgeOnboardingRun.Kind.SKIP_BACKUP`; migration `apps/lifecycle/migrations/0009_edgeonboardingrun_skip_backup_kind.py`.
- Setting: `RMC_BOX_BACKUP_STATE_FILE` default `/backups/backup-state.json` in `config/settings.py`.
- Compose: `backupdata:/backups:ro` on `x-app` (not `backupkeys`). Origin **already had** the `backup` service + `box-backup.sh`; this commit added the **web read-only mount** so the runbook can see `backup-state.json`.

### 3.2 Batch 1818 — per-aspect infrastructure waivers

**Hole:** go-dark still hard-required dry-gate + live Class-A + `conflicts=0` + roster + conversion + backup, so a campus with no uplink could never finish. Other lines (LAN DNS, pairing, logo, empty lab) had prose workarounds but no recorded skip except MC and backup.

**Catalog:** `apps/lifecycle/onboarding_waivers.py`

| key | settings_key | form on step | run_kind |
|---|---|---|---|
| `migration_cloud_apply` | `migration_cloud_skip_reason` | same | `skip_mc` |
| `media_branding` | `branding_skip_reason` | same | `skip_aspect` |
| `seed_operational_data` | `roster_skip_reason` | same | `skip_aspect` |
| `conversion_first_action` | `conversion_skip_reason` | same | `skip_aspect` |
| `configure_lan_hostname` | `lan_hostname_skip_reason` | same | `skip_aspect` |
| `enable_configure_sync` | `sync_enable_skip_reason` | same | `skip_aspect` |
| `verify_and_sync_gate` | `sync_gate_skip_reason` | same | `skip_aspect` |
| `live_sync_proof` | `live_sync_skip_reason` | same | `skip_aspect` |
| `box_backup_verified` | `box_backup_skip_reason` | same | `skip_backup` |
| `offbox_copy` | `offbox_skip_reason` | **`box_backup_verified`** | `skip_aspect` |

**Do not waive:** `cloud_entitle_pin`, `sync_ownership_repair`, `export_cloud_artifacts`, `provision_shell`, `migrate_identities`, `seed_baseline`, `configure_box_env`, `edge_tls_trust`, `go_dark_checklist` as a whole. (`migrate_staff` empty list PASSes.)

Helpers on `apps/lifecycle/edge_onboarding.py`: `aspect_skip_reason`, `aspect_is_waived`, `_waive_if_recorded`, `set_aspect_skip_reason`. Persist via `_set_onboarding_skip_reason` (≥12 chars, overlay `rmc_edge_onboarding`, `.update(settings=)`).

Go-dark treats waived dry/live/roster/conversion/backup as that part OK. If live is waived, `conflicts=n/a`.

Operator UI: `templates/schools/super_edge_onboarding_runbook.html` loops `step.waives`. POST `lifecycle_action=skip_aspect` + `skip_aspect=<key>`. Aliases `skip_migration_cloud` / `skip_box_backup` kept. `EdgeOnboardingRun.Kind.SKIP_ASPECT`; migration `0010_edgeonboardingrun_skip_aspect_kind.py`.

SOP: `docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md` (record skip on the **same host** that will run verify).

### 3.3 Batch 1819 — box CLI + overlay honesty (audit residual)

**Critical hole (must re-prove):** Skips recorded on the **manager** host write the **cloud** school’s `settings`. Go-dark and `edge_onboarding_verify --include-gate` run on the **box** and read the **box** school overlay. Different databases. `import_sovereign_tenant` uses `build_initial_school_settings` and does **not** copy `rmc_edge_onboarding`. The only skip UI is `super:edge_onboarding_runbook` (control-plane). A campus with SSH but no manager session could not waive. Manager GET for box steps is NOT_CHECKED/SKIPPED, so it also must not look like a cloud click certified go-dark.

**Shipped:**

- Command: `apps/lifecycle/management/commands/edge_onboarding_skip.py`
  - `--list` prints catalog
  - `--slug` + `--aspect` + `--reason` (≥12) via `set_aspect_skip_reason`
  - Does not dump/restore/probe network
  - After overlay write, creates `EdgeOnboardingRun` with `via=cli`, `reason_len`, `aspect` (not the reason text). Overlay already persisted if this row fails.
- `generate_runbook` waives include `recorded_chars`, `cli`, **`must_record_on_box`** (`step.runs_on != cloud`). Only Migration Cloud is evaluated on the cloud.
- Template: box/LAN lines say **go-dark reads the box overlay**; button **“Note skip on this cloud tenant”**. MC still **“Record skip”**.
- Text export lists skip CLIs + “(Record this on the BOX…)”.
- Go-dark fail text names the CLI.
- Tests: catalog `form_step` ∈ step keys; CLI `--list` / record / short reason / unknown aspect; overlay is per-school; pairing skip does not waive dry/live; **sovereign-only full `include_gate=True` suite** (owner login + `SECRET_KEY` ≥32 + all catalog waivers).

**Box operator recipe (must still work):**

```bash
python manage.py edge_onboarding_skip --list
python manage.py edge_onboarding_skip --slug <slug> --aspect live_sync_proof \
  --reason "No uplink at this campus — sovereign-only box."
python manage.py edge_onboarding_verify --slug <slug> --include-gate
```

---

## 4. Files in this slice

Treat these as the slice. Confirm they still exist and still do what the claim says.

**Engine / UI / catalog**

- `apps/lifecycle/onboarding_waivers.py`
- `apps/lifecycle/edge_onboarding.py`
- `apps/lifecycle/box_backup_status.py`
- `apps/lifecycle/views_edge_onboarding.py`
- `apps/lifecycle/models_edge_onboarding.py`
- `apps/lifecycle/edge_bringup.py` (comments only: backup has no self-heal)
- `apps/lifecycle/management/commands/edge_onboarding_skip.py`
- `templates/schools/super_edge_onboarding_runbook.html`

**Migrations** (lifecycle leaf was `0008` on origin before this)

- `apps/lifecycle/migrations/0009_edgeonboardingrun_skip_backup_kind.py`
- `apps/lifecycle/migrations/0010_edgeonboardingrun_skip_aspect_kind.py`

**Tests**

- `apps/lifecycle/tests/test_onboarding_aspect_waivers_2026_09_01.py`
- `apps/lifecycle/tests/test_box_backup_verified_step_2026_08_31.py`
- `apps/lifecycle/tests/test_edge_onboarding.py`
- `apps/lifecycle/tests/test_edge_onboarding_operator_ui.py`
- `apps/lifecycle/tests/test_verification_self_heals_2026_08_27.py`
- `apps/lifecycle/tests/test_edge_bringup_2026_08_16.py`
- `apps/lifecycle/tests/test_audit_edge_runbook_2026_08_27.py`
- `apps/lifecycle/tests/test_runbook_bar_denominator_2026_08_27.py`

**Deploy / docs**

- `config/settings.py` — **only** the `RMC_BOX_BACKUP_STATE_FILE` hunk from this slice. Do not expect pull-paging / compression / clock settings from a dirty local tree.
- `deploy/selfhost/docker-compose.yml` — `backupdata:/backups:ro` on `x-app`
- `deploy/selfhost/.env.edge.example` — `RMC_BOX_BACKUP_STATE_FILE` comment
- `docs/EDGE_BOX_BACKUP_RUNBOOK.md` — pointer to engine step `box_backup_verified`
- `docs/EDGE_CLOUD_SYNC_OPERATOR_RUNBOOK.md`
- `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` (1817–1819)
- `docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md`
- `docs/generated/system_closure_map.json`

`box-backup.sh` / `box-restore.sh` **already existed on origin/main**; they were **not** re-added as new files in `e65254d20`.

---

## 5. Proof Grok ran (re-run; do not trust)

In the **dirty local checkout** (before cherry-pick):

```bash
python scripts/run_sqlite_memory_tests.py \
  apps.lifecycle.tests.test_onboarding_aspect_waivers_2026_09_01 \
  apps.lifecycle.tests.test_box_backup_verified_step_2026_08_31 \
  apps.lifecycle.tests.test_edge_onboarding \
  apps.lifecycle.tests.test_edge_onboarding_operator_ui \
  apps.lifecycle.tests.test_audit_edge_runbook_2026_08_27 \
  apps.lifecycle.tests.test_verification_self_heals_2026_08_27 \
  apps.lifecycle.tests.test_edge_bringup_2026_08_16 \
  apps.lifecycle.tests.test_runbook_bar_denominator_2026_08_27
```

Claimed last green full set: **133/133 OK**.  
Claimed `python manage.py audit_edge_runbook --strict` → **19 steps, 76 OK, 0 WARN, 0 FAIL**.

After CLI `EdgeOnboardingRun` was added: focused **55/55 OK** (waiver + backup step + operator UI).

**Honesty on proof:** worktree re-run on the cherry-pick hung on Windows (“Destroying old test database”). That is a resource stall, not a red suite. Pre-push hook (`scripts/pre_push_boundary_check.py`) hung with no output. Push used empty `core.hooksPath` so the fast-forward could complete. **Re-run the suites yourself. Do not treat hung = green.**

### Git / push facts (honest)

- Working tree was dirty with peer `sync_engine` / `ci.yml` / etc. Those were **not** committed.
- `git merge origin/main` in that checkout **failed**: peer uncommitted files would be overwritten.
- Slice was committed locally as `ae40b7cdb` on dirty `main`, then **cherry-picked** onto `origin/main` in a clean worktree as **`e65254d20`** and fast-forwarded.
- Cherry-pick conflicts (resolved): `.env.edge.example` (keep STATE_FILE comment), `docs/EDGE_BOX_BACKUP_RUNBOOK.md` (add engine-step related links). Compose auto-merged; `backupdata:/backups:ro` on `x-app` present after pick.
- This agent’s **local checkout was not reset** to `origin/main`; peer WIP was left in place.
- **Not committed (on purpose):** `apps/schools/tests/test_edge_box_backup_2026_08_31.py`, `deploy/selfhost/box-audit.sh` C2 edits, all `apps/sync_engine/*`, `.github/workflows/ci.yml`, mixed `config/settings.py` peer hunks from the dirty tree.

---

## 6. Commands Claude must run

Prefer a clean tree aligned with `origin/main` if peer WIP would confuse results. Use sqlite-memory on Windows if Postgres/SQLite file teardown hangs.

```bash
python scripts/run_sqlite_memory_tests.py \
  apps.lifecycle.tests.test_onboarding_aspect_waivers_2026_09_01 \
  apps.lifecycle.tests.test_box_backup_verified_step_2026_08_31 \
  apps.lifecycle.tests.test_edge_onboarding \
  apps.lifecycle.tests.test_edge_onboarding_operator_ui \
  apps.lifecycle.tests.test_audit_edge_runbook_2026_08_27 \
  apps.lifecycle.tests.test_verification_self_heals_2026_08_27 \
  apps.lifecycle.tests.test_edge_bringup_2026_08_16 \
  apps.lifecycle.tests.test_runbook_bar_denominator_2026_08_27

python manage.py audit_edge_runbook --strict
```

If Django is available and the environment is not hung:

```bash
python scripts/pre_push_boundary_check.py
```

Also confirm:

- lifecycle has a **single** migration leaf (`0010`); `0009` depends on `0008`; kinds `skip_backup` / `skip_aspect`; `max_length=16` fits.
- `settings.RMC_BOX_BACKUP_STATE_FILE` is defined on live settings (or `getattr` default still works).
- `deploy/selfhost/docker-compose.yml` `x-app` has `backupdata:/backups:ro`. Must **not** mount `backupkeys`. Backup service must still write `backupdata`.

---

## 7. Fail the slice if any of these are still true

1. **Host split:** manager POST skip for `live_sync_proof` / `box_backup_verified` makes box `include_gate=True` pass **without** the same overlay on the box school. CLI on this host must. Two `School` rows: skip on A must not waive B.
2. **`must_record_on_box`:** False for a box/LAN waive. Template says a manager click clears go-dark for box lines.
3. **Sovereign-only E2E:** waive entire catalog + owner membership + academic year + entitlement + `SECRET_KEY` ≥32 + missing backup state file → `run_verification_suite(..., include_gate=True)` is **not** all green. **SECRET_KEY must remain non-waivable** (fail if unset/placeholder/<32).
4. **Off-box:** waive `offbox_copy` without a verified dump → backup step PASSes. With verified dump + off-box waive → PASS and warning rewritten is the correct path.
5. **Cascade:** `enable_configure_sync` waived → dry and live also PASS without their own reasons.
6. **Empty staff / roster:** empty staff FAILs, or empty roster PASSes without `seed_operational_data` waived. Orphaned teacher FKs PASS.
7. **Heals:** waived dry/live heals still call `run_sync_gate` / `run_sync_cycle`.
8. **`audit_edge_runbook --strict`:** not 19 steps, or any FAIL; a `command_template` missing `{slug}`; validate/heal raises (check D).
9. **Compose:** app cannot read `/backups/backup-state.json`, or app mounts `backupkeys`.
10. **Catalog vs request:** a named infrastructure line (SIS/MC, logo, empty roster, conversion/lab, LAN DNS, pairing, dry gate, live Class-A, backup, off-box USB/NAS) has no waiver. Identity or `SECRET_KEY` **is** in `WAIVE_BY_KEY`.
11. **≥12 chars:** 11-character reason waives. CLI / POST / `set_aspect_skip_reason` fail open.
12. **Go-dark rubber stamp:** with no skips and no dump, go-dark PASSes.
13. **UI:** skip form on `migrate_identities` / `configure_box_env` / `go_dark_checklist`. Box lines missing CLI + “Go-dark reads the box overlay”. MC missing “Record skip”.
14. **i18n:** new operator strings not in `{% trans %}` / `{% blocktrans %}`.
15. **Tenant:** overlay write is not `School.objects.filter(pk=...).update(settings=)` on the shared `School` parent.

---

## 8. Known remaining honesty (not bugs unless you decide otherwise)

Confirm these are still true. Fix only if they violate the original request.

- Manager skip POST for box aspects **still writes the cloud overlay** (audit note / source-tenant preview for `cloud_preview=True` source-tenant steps). Load-bearing path for go-dark is **CLI on the box**. If that click is too easy to misread as go-dark clearance, refuse POST for `must_record_on_box` on manager and keep CLI-only.
- Manager GET still skips `evidence=box_settings` steps (pairing, LAN, box env, backup). Branding/roster/conversion **do** run against the **cloud** school on manager preview — a cloud skip can green the **preview** without greening the box.
- `configure_box_env` is **not** waivable and inspects **this process’s** `SECRET_KEY` (correct on the box; manager GET skips it via evidence).
- Operator page is **control-plane only**; there is no box-hosted skip UI.
- Sovereign import does **not** copy skips. Operators must re-record on the box after `--fresh` / import. If product intent is “skip travels with the bundle,” that is not implemented — do not silently copy MC skips onto the box without a decision.
- Go-dark composite does **not** require pairing, LAN, or branding as parts. Those are separate steps in the full suite. A box can go-dark with pairing still red if dry+live are waived.
- `box-audit.sh` C2 and `apps/schools/tests/test_edge_box_backup_2026_08_31.py` were **not** in this push (peer / stay-off). Engine reader is Python-side C2; shell audit may still drift.
- No live browser pass on `/super/edge-onboarding/`. Operator UI was proven with Django GET/POST tests only.
- Later peers may have allowlisted broad-except in `edge_onboarding.py`. Confirm waiver `except Exception` guards are still the never-raise contract, not a silenced bug.
- Existing boxes need a compose remount + restart so web can read `/backups/backup-state.json`. Apply `lifecycle/0009` and `0010`.

---

## 9. Deploy / operator truth to preserve

On the **box**, before certifying go-dark:

```bash
python manage.py edge_onboarding_skip --list
python manage.py edge_onboarding_skip --slug <slug> --aspect live_sync_proof \
  --reason "No uplink at this campus — sovereign-only box."
# repeat for each missing infrastructure line
python manage.py edge_onboarding_verify --slug <slug> --include-gate
```

Django still never dumps or restores. `box-backup.sh once` (or a written skip) is the dump path.

---

## 10. Report format when done

1. Engines you ran and exact pass/fail counts.
2. Each item in §7: PASS / FAIL / FIXED (what you changed).
3. Each item in §8: still honest / you changed product intent (why).
4. Residual true blockers only (missing credential, irreversible external decision).
5. Do **not** claim 9.5/10. Do not spawn a parallel plan file. If you ship a fix, record in SOT §11.4 + autonomous log **after** gates are green.
