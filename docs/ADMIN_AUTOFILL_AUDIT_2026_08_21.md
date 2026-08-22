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
- **2 produce no output within 100s** (`audit_admin_gravity.py`,
  `verify_admin_manager_shell_aggressive.py`).

> **This last line was wrong and is corrected below.** Neither hangs. `audit_admin_gravity`
> completes in 18–24s; the 100s timeout hit a cold filesystem cache while eighteen
> other scripts ran in the same loop. `verify_admin_manager_shell_aggressive` takes
> 454s because it is a bundle runner spawning fifteen subprocesses. Recording the
> mistake rather than editing it away: "timed out once under load" is not "hangs",
> and the difference decided whether they could be wired.

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

All four are now green — see "The deferrals, closed" below. The lock was still not
edited; the *gates* were, to assert an invariant instead of a snapshot.

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

## The deferrals, closed

Everything the first pass deferred was worked to a conclusion. Two of the four
"findings" turned out to be wrong about the world, which is recorded here rather
than quietly corrected.

### The four red gates: one root cause, one design fault

All four asserted an **exact** service-worker version (three read it from
`var/admin-approval-build-lock.json`, one kept a private copy nine days staler), while
the deploy checklist requires bumping `CACHE_VERSION` every wave. They reddened on
every wave *by construction*, which is why nobody had wired them.

Replaced with the invariant they were reaching for — **the shipped service worker is
at least the approved build's** — in one shared reader, `scripts/admin_build_lock.py`,
so the lock now has a single consumer instead of three drifting ones.

- `audit_django_admin_miss_nothing.py` → PASS
- `sweep_django_admin_platformwide_layout.py` → PASS (also stopped keeping its own copy of the lock)
- `audit_admin_os_cross_wave.py` → PASS (94 OK / 0 FAIL)
- `verify_admin_tenant_change_form_product_links.py` → PASS

The last one was a genuine gap, not a pin: 33 of 34 `change_form.html` templates carry
a product escape link and the **base** template — the one every model on both sites
actually renders — did not. Added to its command band.

The cross-wave gate also wanted a CSS seal that existed in no stylesheet. The v22
build demonstrably shipped (its cache-bust is live in `base_site.html`, its
`data-rmc-admin-approval-build` attribute is in the rendered shell, and the wired
`verify_django_admin_preview_parity` gate — which checks that same lock's
`visible_proofs` — is green), so the seal was written where the v22 rules live, and
the gate now searches the admin stylesheet family rather than one hardcoded file.

**The approval lock was still not edited.** It records that a build was *approved*;
making a gate green by rewriting it would assert an approval nobody gave.

### The two "hangs" were not hangs

- `audit_admin_gravity.py` completes in **18–24s, exit 0**. The earlier verdict came
  from a 100s timeout that landed on a cold filesystem cache while eighteen other
  scripts ran in the same loop. "Timed out once" is not "hangs", and it should not
  have been reported as one.
- `verify_admin_manager_shell_aggressive.py` takes **454s** because it is a *bundle
  runner* — fifteen sub-checks, each spawning a subprocess with `timeout=300`. It was
  red for the same exact-pin reason as the others and now passes.

All 16 are wired, placed by cost so none gets skipped: <1s to pre-push and the
boundaries workflow, 6–32s to the workflow only, Django-dependent to `ci.yml`, and the
454s bundle to its own job with a 20-minute timeout. **76 required gates, 0 un-wired.**

### `finance/tasks.py` — fixed

`_auto_generate_fee_invoices_body` resolved the academic year with an unscoped
`get_current_academic_year()` and only then worked out which school it was billing.
The year is not cosmetic: it selects the fee plans to invoice and the billing period
the run is deduplicated on. School is now resolved first and passed to both resolvers.

Five tests in `apps/finance/tests/test_invoice_year_is_scoped_to_school_2026_08_21.py`;
two of them fail against the previous ordering. The sibling `_auto_copy_fee_plans_body`
was deliberately left alone — it has no school to scope by and its markers say it runs
inside a tenant schema.

### The test that never finished — and the defect underneath it

`test_admin_model_outcomes.py` did not complete in nine minutes. That was not a slow
test; it was a slow **product**.

One tenant admin changelist (`/admin/accounts/user/`) issued **8,944 queries**, and
**8,275 of them were the same SELECT** against `platform_runtime_runtimedefaults`.
Tracing the callers put 8,118 of them behind `SiteSettings.__getattr__`, which
consults RuntimeDefaults for every behavioural field Phase B moved off that table —
and `owned_payload()` loops those fields, making it quadratic. A single changelist
cost ~53 seconds of server time. The operator site was ~100× faster for the same work.

`RuntimeDefaults.get_singleton()` is now memoized in-process, invalidated two ways so
it cannot serve something this process has superseded: a version counter bumped by
`save()`/`delete()`, and a short TTL for writes from other processes. A schema-drift
`None` is deliberately **not** memoized, so migrations landing do not leave the
platform degraded for the life of the process.

| | before | after |
|---|---:|---:|
| queries, one tenant changelist | 8,944 | **1,286** |
| `test_admin_model_outcomes.py` | never finished (>9 min) | **10 passed, 567s** |

Sealed by `apps/platform_runtime/tests/test_runtime_defaults_singleton_cache_2026_08_21.py`,
which asserts the invalidation paths as well as the speed — a cache that cannot be
invalidated trades a performance bug for a correctness one, and the admin's own
edit-then-re-read flow is exactly where that would surface.

### The four `apps/automation` failures — fixed

All four were fixtures that had fallen behind the product, not product defects:

1. **MFA.** `RequireMFAMiddleware` augments tenant-configured roles with a platform
   baseline that always requires MFA for privileged roles. It gates twice — no
   confirmed device redirects to `/mfa/setup/`, a device without a verified session
   redirects to `/mfa/verify/` — and `force_login()` establishes neither. The fixtures
   modelled an operator who cannot exist.
2. **School binding.** `test_studio_simulation_engine_lists_catalog_when_school_bound`
   never bound its user to a school. `User` has no `school` column at all; the binding
   is a `SchoolMembership` row. Added inside that one test, because sibling tests in
   the same class deliberately exercise the unbound user.

`apps/automation/tests`: **132 passed, 0 failed** (was 4 failed / 128 passed).

### Operator-side: two real signals, and a live 500 found on the way

The "operator gain is structural, ~nil" conclusion was two-thirds right and one-third
not looking hard enough.

1. **Django already carries the school.** An operator who filters a changelist to one
   school and clicks Add sends `?_changelist_filters=school__id__exact=…`. That is the
   operator's own immediately preceding input, not a guess, and reading it makes every
   tenant-state resolver work on the operator site. A `school` resolver was added for
   the 34 operator models that require it (guarded so it can never fire on the tenant
   site, where `school` is excluded from the form by policy).
2. **An event recorded now happened now** — for a tight allowlist of names meaning
   "when the recorded thing took place". This is a convention rather than derived
   state, so every one carries a note into the field's help text. Future-facing names
   (`expires_at`, `starts_at`, `due_at`, `scheduled_at`) are excluded: defaulting those
   to now is wrong, not merely unhelpful.

| operator | before | after |
|---|---:|---:|
| context-free request | 382 required-and-empty | 379 |
| **arriving from a filtered changelist** | 382 | **345** |
| models receiving a suggestion | 0 | **74** |
| resolver-reachable models / fields | 0 / 0 | **88 / 108** |

**A live 500, found by a test written for something else.** `School`'s primary key is a
UUID, so `School.objects.filter(pk=<not-a-uuid>)` *raises* rather than matching
nothing. `_request_school` passed the query string straight in, so
`?school=anything-not-a-uuid` on **any admin add form on either site** was a 500 — on
`origin/main`, before this work. Now guarded.

Two measurement artifacts were also corrected rather than reported as wins:
`builder_hits` had counted `_changelist_filters` itself as a "suggestion" (Django
copies every query key into `initial`), and `resolver_reachable` had counted the
tenant-site `school` field that policy excludes from the form.

## Still open

- **Usage inference remains unproven on real data.** Not one of 141 tenant-scoped
  models has the 25 rows it requires in this database, so it is proven by fixtures
  only. It wants a run against a populated tenant before anyone trusts it.
- **The dev database is missing 4 tenant-scoped tables** (`schoolops_vendor` among
  them); those models are skipped by every data-dependent measurement here.
- **`test_admin_model_outcomes.py` still takes 567s.** 478 full admin page renders is
  inherently heavy; the pathological part is gone, the bulk is not.
- **~64% of the remaining required-and-empty fields are irreducible by pre-fill** —
  content a human writes, or a relational choice only they can make.
