# SDK 1.0.0 Graduation Runbook (Wave 9 Agent N, v3.58.x)

**One-page operator runbook** for graduating the webhook-verifier SDKs
from `1.0.0-rc.1` to `1.0.0`.

Owner: founder / SDK maintainer.
Status: SHOVEL-READY (Wave 9, 2026-05-22). The actual graduation runs
on or after **2026-08-17** (90 days from the 1.0.0-rc.1 ship date of
2026-05-19). Until then this runbook describes the planned procedure.

---

## 0. Background

* Packages shipped at v3.38.0 (2026-05-19):
  * `runmycampus-webhook-verifier` (PyPI) — `1.0.0-rc.1`
  * `@runmycampus/webhook-verifier` (npm) — `1.0.0-rc.1`
* 90-day field-test window — graduation date: **2026-08-17**.
* Public-API surface frozen in `STABILITY.md` per package — graduation
  does NOT change any exported names; only the version string + the
  `Development Status` classifier (PyPI) + the npm dist-tag flip.
* Auto-reminder: `.github/workflows/sdk-1-0-0-graduation-reminder.yml`
  opens a GitHub issue daily at 09:00 UTC starting 2026-08-17 if
  the package version is still `1.0.0-rc.1`.

---

## 1. Pre-graduation checklist

All must hold before running the graduation script.

### 1.1. Field-test feedback reviewed

* Search closed issues tagged `webhook-verifier` for the period
  2026-05-19 → today. Confirm none are deferred.
* Read the #webhooks-feedback channel; confirm no subscriber has
  reported wire-format drift or signature-verification mismatches.

### 1.2. No critical bugs open

* `gh issue list --label webhook-verifier --label critical --state open`
  must return zero rows.
* Internal QA verifier runs against the canonical-cases.json fixture
  pass on both languages.

### 1.3. Both packages green in CI on `main`

* `release-webhook-verifier-py.yml` last green for `main`.
* `release-webhook-verifier-js.yml` last green for `main`.
* `architectural-boundaries.yml` baseline 0 on all gates.

### 1.4. STABILITY.md files match published artifacts

* `packages/runmycampus-webhook-verifier-py/STABILITY.md` lists 23
  Python names + 6 types.
* `packages/runmycampus-webhook-verifier-js/STABILITY.md` lists 23 JS
  values + 6 types.
* Confirm any export changes that landed between 1.0.0-rc.1 and today
  are reflected. (If exports changed, you must NOT graduate to 1.0.0
  — bump to 1.1.0 instead, since per semver the public surface should
  be additive only between RC and GA.)

### 1.5. LEGACY_HEADER_DEPRECATION_DATE alignment

* Python: search for `LEGACY_HEADER_DEPRECATION_DATE` constant — must
  be `2026-08-18`.
* JS: same.
* Docs: `docs/WEBHOOK_VERIFICATION.md` references the same date.

### 1.6. Today's date >= 2026-08-17

If you must graduate earlier (emergency bug fix forcing a major
re-cut), set `RMC_SDK_GRADUATION_OVERRIDE_DATE_CHECK=1` and document
the reason in the commit message + a new CHANGELOG note. Do not
override casually; the field-test window exists for a reason.

---

## 2. Graduation procedure

### 2.1. Dry-run the script

```
cd beta/school-management-system
python scripts/graduate_sdk_1_0_0.py
```

The script prints the 6 planned edits (3 Python + 3 JS):

* `pyproject.toml` — version
* `src/runmycampus_webhook_verifier/__init__.py` — `__version__`
* `CHANGELOG.md` — prepend `[1.0.0]` entry
* `package.json` — version
* `src/index.ts` — `VERSION`
* `CHANGELOG.md` — prepend `[1.0.0]` entry

### 2.2. Apply

```
python scripts/graduate_sdk_1_0_0.py --apply
```

The script writes all 6 files. If any single write fails (very rare —
unwritable filesystem, etc.), it exits with code 2 and the partial
state must be manually `git restore`d. Re-running after restore is
safe (idempotent on already-graduated state — refuses with a
`already graduated` message).

### 2.3. Commit

```
git add -A
git commit -m "Graduate webhook-verifier SDKs from 1.0.0-rc.1 to 1.0.0"
```

### 2.4. Tag and push (this is what publishes)

```
git tag webhook-verifier-py-v1.0.0
git tag webhook-verifier-js-v1.0.0
git push --tags
```

The tag pushes trigger `release-webhook-verifier-py.yml` and
`release-webhook-verifier-js.yml`. Both workflows:

* gate on `confirm="publish"` for `workflow_dispatch` invocations;
  tag-triggered runs auto-approve;
* run the test suite on every supported language version;
* build the artifact;
* publish to PyPI (OIDC trusted publishing) / npm (provenance true).

### 2.5. Verify on PyPI + npm

* `pip install runmycampus-webhook-verifier==1.0.0` — succeeds.
* `npm view @runmycampus/webhook-verifier@1.0.0` — present.

### 2.6. Close the auto-opened reminder issue

If the daily workflow opened a graduation-reminder issue, close it
manually with the link to the published artifact.

---

## 3. Post-graduation tasks

### 3.1. Announcement

* Developer blog post: "Webhook Verifier SDK 1.0 — GA".
* Slack #webhooks-feedback channel announcement.
* Re-send the graduation note to the customer integrators mailing
  list.

### 3.2. Deprecate 0.x docs

Search `docs/` and `packages/*/README.md` for any `0.x` or `0.1.0`
or `0.2.0` references. Mark them deprecated with a pointer to the
1.0.0 docs.

### 3.3. Update `STABILITY.md` post-GA wording

Each file has a sentence "release candidate for 1.0.0". Update to
"Stable. Public surface frozen at 1.0.0."

### 3.4. Future: 2.0 planning

The `LEGACY_HEADER_DEPRECATION_DATE = 2026-08-18` is the planned
moment to flip the `accept_legacy=True` default to `False`. That flip
is a breaking change → it lands as **2.0.0**, not as a 1.x patch.

---

## 4. Rollback (if a critical bug surfaces post-publish)

PyPI does NOT allow republishing the same version. Rollback path:

* Yank the broken version from PyPI: `pip install twine && twine ... ` — or via
  the PyPI web UI under "Manage releases".
* Tag a new version `1.0.1` with the fix.
* npm: deprecate the broken version via `npm deprecate
  @runmycampus/webhook-verifier@1.0.0 "<reason>"` and publish `1.0.1`.
* Email customers who downloaded the broken version (PyPI provides
  download stats; npm provides similar).
* Note: rollback is a `1.0.1` patch, NOT a return to `1.0.0-rc.1`.
  Going back to RC is a semver violation.

---

## 5. Files referenced by this runbook

* `packages/runmycampus-webhook-verifier-py/pyproject.toml` —
  version source for Python.
* `packages/runmycampus-webhook-verifier-py/src/runmycampus_webhook_verifier/__init__.py`
  — `__version__` constant.
* `packages/runmycampus-webhook-verifier-js/package.json` — version
  source for JS.
* `packages/runmycampus-webhook-verifier-js/src/index.ts` —
  `VERSION` constant.
* Both `CHANGELOG.md` files — release history.
* Both `STABILITY.md` files — public-API surface SOT.
* `scripts/graduate_sdk_1_0_0.py` — the graduation script (Wave 9 Agent N).
* `.github/workflows/sdk-1-0-0-graduation-reminder.yml` — daily
  reminder workflow (Wave 9 Agent N).
* `.github/workflows/release-webhook-verifier-py.yml` — PyPI publish
  workflow.
* `.github/workflows/release-webhook-verifier-js.yml` — npm publish
  workflow.

---

## 6. Why a runbook + a script + a workflow

The runbook is the operator-facing playbook (this file). The script
mechanizes the textual edits so a tired engineer at 11pm can run one
command instead of hand-editing 6 files. The workflow is the
fail-safe — even if everyone forgets the graduation date,
`sdk-1-0-0-graduation-reminder.yml` opens an issue on the GA date
and refreshes it daily until the package is graduated.
