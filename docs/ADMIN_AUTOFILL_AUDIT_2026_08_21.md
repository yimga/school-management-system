# Django admin form-automation audit — 2026-08-21

Audit-first pass over the tenant/operator admin form-automation and auto-fill system,
followed by the expansion it justified. Base commit `e984178bb`.

Everything below was produced by **running** things. Every number has a command
under it that reproduces it.

---

## 0.1 The registration mechanism — and the number that lies

`config/admin.py` defines `BaseRunMyCampusAdminSite(UnfoldAdminSite)` with two live
instances, `tenant_admin_site` (name `tenant_admin`) and `platform_admin_site`
(name `admin`). Its `register()` override rebuilds every incoming admin class:

```python
base_class = type(base_class.__name__, (AdminFormAutomationMixin, base_class), {...})
```

So **automation coverage is 100% by construction** on both sites. No admin class in
`apps/` names the mixin, and it does not need to.

> **A source-inheritance scan reports 0 of 460 and that number is meaningless.**
> It is the first thing this codebase tells you if you ask the wrong question, and
> acting on it would mean adding the mixin to hundreds of source classes that
> already have it. The `_rmc_admin_form_automation` guard exists to make that
> double-application a no-op, which is the tell.

Coverage is therefore **asserted against the live `_registry`**, never searched for
in source:

```bash
python scripts/audit_admin_form_intelligence_contract.py     # 0 findings
```

## 0.2 Per-site inventory

```bash
python scripts/audit_admin_autofill_coverage.py --top 0
```

| | tenant | operator | total |
|---|---:|---:|---:|
| registered models | 281 | 197 | **478** |
| models with a `school` FK | 141 | 64 | 205 |
| editable fields presented on add forms | 2,065 | 1,577 | **3,642** |
| of those, **required** | 949 | 659 | **1,608** |
| inline classes attached | 28 | 2 | **30** |

## 0.3 The auto-fill coverage number

`apps/siteconfig/admin_smart_initials.py` held `INITIAL_BUILDERS` with **exactly one
entry** — `academics.academicyear` — while `get_changeform_initial_data` called
`build_admin_smart_initials(self.model, request)` for **all 478 registrations**.

**The engine was wired to 100% of the platform and the registry answered for 0.2% of
it.** That framing decided the whole shape of the work: this was never an
architecture problem, and an agent that starts by rewriting the registration
mechanism has misread the codebase.

## 0.4 What is guarded, and what only looks guarded

| script | status at base |
|---|---|
| `audit_admin_form_intelligence_contract.py` | **enforced** — `ci.yml:57` + `REQUIRED_GATES` |
| `verify_django_admin_preview_parity.py` | **enforced** — boundaries + pre-push |
| `verify_admin_changelist_render_contract.py` | **enforced** |
| `verify_admin_steering_strip_contract.py` | **enforced** |
| 20 further `audit_*admin*` / `verify_*admin*` scripts | **invoked by nothing** |

Running all 19 runnable ones (`scratchpad/triage_unwired.sh`) produced a result no
one had seen, because nothing ran them:

- **11 pass** in under a second each — real pass/fail gates, reachable only by
  somebody remembering they exist.
- **4 are RED right now** on `main`.
- **2 hang** (`audit_admin_gravity.py`, `verify_admin_manager_shell_aggressive.py`)
  and produce no output within 100s.

The four red ones share one root cause, and it is a design fault rather than a
defect in the admin surface: they assert an **exact** service-worker version and
cache-bust string taken from `var/admin-approval-build-lock.json`
(`sms-v4.06.71-…-2026-08-20`, `?v=20260811-experience-runtime-v172`). CLAUDE.md's
deploy checklist requires bumping `CACHE_VERSION` on **every** wave, so these gates
go red on every wave by construction. That is why they were never wired — wiring
them would redden CI permanently.

`verify_service_worker_version.py` already asks this question correctly (shape +
monotonicity) and **is** wired. The four duplicate it in a form that cannot hold.

> **I did not bump the approval lock to make them green.** The lock records that a
> specific admin build was *approved*; editing it would be asserting an approval
> that nobody gave. That is a decision for whoever owns that sign-off.

## 0.5 The add-form reality check

The brief asked for 12 models. The instrument measures **all 478** by building each
add form exactly the way `ModelAdmin._changeform_view` does, so the sample is the
whole population.

**961 required fields across the two admin sites arrived empty on every add form**
(579 tenant + 382 operator).

### How much of that is even reducible

Classifying every one of the 925 that remained after the expansion:

| class | count | share |
|---|---:|---:|
| content the human writes (`name`, `title`, `code`, `slug`, `description`…) | 305 | 33% |
| relational choices (`student`, `subject`, `classroom`, `app`…) | ~240 | 26% |
| other CharField (identifiers, keys) | 157 | 17% |
| date/time | 57 | 6% |
| choice with no model default | 51 | 6% |
| number | 48 | 5% |

**Roughly two-thirds is irreducible by pre-fill.** Nobody can derive what a fee
plan is called or which student sat an exam. Chasing the raw 961 downward past this
point means guessing, which rule 1.2 forbids — so the honest ceiling is far below
the headline, and this is stated here rather than discovered later by someone
comparing the number to an expectation nobody set.

---

## What the expansion changed

Same instrument, same shared database (`AppData/Local/RunMyCampus/db_working.sqlite3`,
which every worktree reads), base `e984178bb` vs this branch:

```bash
# before — the FINAL instrument, run against a checkout of the base commit
git worktree add --detach ../wt-adminbase e984178bb
cp scripts/audit_admin_autofill_coverage.py ../wt-adminbase/scripts/
(cd ../wt-adminbase && python scripts/audit_admin_autofill_coverage.py --json var/base-measure.json)
# after
python scripts/audit_admin_autofill_coverage.py --json var/after-measure.json
```

| metric | base | after | Δ |
|---|---:|---:|---:|
| generic field resolvers | 0 | 9 | **+9** |
| models receiving any suggestion | 1 | 68 | **+67** |
| resolver-reachable models | 0 | 123 | **+123** |
| resolver-reachable fields | 0 | 162 | **+162** |
| prefilled fields (tenant / operator) | 716 / 598 | 781 / 611 | +65 / +13 |
| **required-and-empty (both sites)** | **961** | **925** | **−36** |
| models with nothing left to type | 14 | 18 | +4 |
| inline classes carrying any policy | 0 / 30 | **30 / 30** | +30 |

### Read those two rows against each other

162 fields are now reachable by a resolver. Only 36 fewer are actually empty on this
database. **The gap is the measuring tenant, not the code.**

`gilead-school` — the only active school in the dev database — has
`default_region = None`, `country_code = ''`, `currency = ''`,
`default_language = ''`, and **zero** `TeacherProfile` rows. Five of the nine
resolvers therefore cannot fire here at all. Only `academic_year`, `term`,
`timezone` and the actor resolver have anything to resolve against.

```bash
python - <<'PY'   # reproduces the density check
# 141 tenant-scoped models; 0 have >=25 rows, 129 have none, 4 tables are missing
PY
```

**This is the weakest part of the evidence, and it is load-bearing:** the
usage-inference feature (below) is proven by test fixtures only, because not one of
141 tenant-scoped models has the 25 rows it requires before it will say anything.
The measured `−36` is a floor, not the capability.

---

## What was built

### 1. A generic field-resolver layer (`admin_smart_initials.py`)

Nine resolvers matched by **field shape**, not by name: a relational resolver
compares against `_meta.concrete_model` (so the `global_registries.RegionConfig`
proxy resolves through to `siteconfig.RegionConfig` with no alias table), and a
scalar resolver additionally checks `choices` membership and `max_length` before
offering anything.

`academic_year`, `term`, `region`, `teacher`, `country_code`, `currency`,
`timezone`, `language`, and the actor set (`author`, `uploaded_by`, `checked_by`,
`labeled_by`, `raised_by`, `recorded_by`, `submitted_by`, `requested_by`,
`reported_by`, `reviewed_by`, `logged_by`, `actor`).

**`user` is deliberately not resolved.** On `compliance.auditlog` it is the subject
of an audited action; on `apicenter.oauthauthorizationcode` it is the token's
resource owner. On neither is it "whoever opened the form". It appears on 39 models
and filling it would have been the single largest coverage number in this report —
and wrong on most of them.

### 2. Tenant scoping, by extending rather than forking

`apps/automation/helpers.py::get_current_academic_year()` queried **all** schools.
It gained an optional `school=` parameter (default `None`, so every existing caller
is unchanged) and the admin builders always pass it. Forking a second resolver
would have tripped `scan_config_resolver_fragmentation`; more to the point, the
platform should have one answer to "what year is it".

> **Defect found, not fixed:** `apps/finance/tasks.py:1027` calls
> `get_current_academic_year()` **before** resolving `school` on line 1035, then
> generates invoices for that school using the globally-resolved year. In a
> multi-school deployment it can bill school B against school A's calendar. The fix
> is now available (pass `school=`) but reordering money-generating code is outside
> this brief's scope and wants its own test.

### 3. Usage-derived field visibility (`admin_field_usage.py`)

3,642 fields are presented; 1,608 are required. The remaining ~2,000 are read on
every add form forever. This counts, per model **and per school**, how many existing
records actually carry each optional value — and hides the ones that are always
empty.

Four guards, each load-bearing: a 25-row sample floor; **the person's own choice
switches inference off entirely** for that surface; optional fields only; and every
inferred field rides in the contract tagged with its reason and row count, so the UI
says "your school has never used this" instead of pretending someone chose it.

### 4. Cross-field consistency, server-side

A `Term` belongs to exactly one `AcademicYear`, so selecting both and having them
disagree is unambiguously wrong — 13 registered models carry that pair.
`RELATION_CONTAINMENT_PAIRS` is an explicit list and **not** a generic "child has an
FK to parent" rule: `student` and `classroom` are related that way too, and a
student sitting an exam in another room is legal. A generic rule would reject real
data, which is worse than not checking.

No JavaScript mirror: a second copy of the rule in the browser is a second thing
that can disagree with the database, and it is not the copy that decides whether the
row saves.

### 5. Inline formsets — done, not deferred

30 inline classes were attached across the two sites and **none** carried any of the
policy: system-evidence fields were editable there, and tenant ownership was posted
from the client. `AdminInlineAutomationMixin` now applies the same rules, injected at
registration exactly like the ModelAdmin one, and `save_formset` binds `school` from
the resolved request. **30/30.**

---

## Sealing

| where | what |
|---|---|
| `audit_admin_form_intelligence_contract.py` | extended to cover inlines + inferred-hidden disjointness. **Mutation-proved:** disabling inline injection produces 30 findings, exit 1. |
| `audit_admin_autofill_coverage.py` | new coverage ratchet. **Mutation-proved:** deleting the `academic_year` resolver reports `resolver_reachable_models 90 -> 78`, exit 1. |
| `ci.yml` + `pre_push_boundary_check.py` + `REQUIRED_GATES` + this table | all four, or none — a gate wired into some of them reports green from the place nobody reads. |
| 10 previously-unwired admin gates | wired into `architectural-boundaries.yml`, pre-push, and `REQUIRED_GATES`. 67 required gates checked, 0 un-wired. |

**The ratchet deliberately does not guard the headline numbers.** `prefilled`,
`builder_hits` and `required_empty` depend on the database, and `ci.yml` seeds a
single empty school — a ratchet on them would either fail permanently or be
re-baselined to a number that proves nothing. It guards
`resolver_reachable_models/_fields`, `builder_models`, `registered_models` and
`models_with_errors`, which come from model metadata and read the same everywhere.

---

## Not done — stated plainly

- **The four red admin gates are still red.** Diagnosed, not fixed: they need their
  exact-version pins replaced with the monotonic check `verify_service_worker_version.py`
  already performs, or the approval lock re-signed by its owner.
- **Two admin scripts hang** and were not wired or investigated further.
- **`verify_admin_tenant_change_form_product_links.py`** wants a product URL tag in
  `templates/admin/change_form.html`. Real and current; adding one is a UX decision.
- **`finance/tasks.py` cross-tenant year resolution** — reported above, not fixed.
- **Usage inference is unproven outside tests** on this database, for the reason in
  §0.5. It wants a run against a populated tenant before anyone trusts the feature
  in production.
- **The dev database is missing 4 tenant-scoped tables** (`schoolops_vendor` among
  them), so those models were skipped by every data-dependent measurement here.
- **Operator-side gain is ~nil** (−1 field). The operator site has no
  `request.school`, so tenant-state resolvers have nothing to resolve against unless
  a `?school=` parameter is present. This is structural, not an oversight.
