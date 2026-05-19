# Upstream Dependency Watch Protocol

**Owner:** Founder / on-call SRE.
**Last updated:** v3.34.0, 2026-05-18.

This document catalogues the third-party Python / JS dependencies
RunMyCampus is **watching for specific version events** that unblock
internal work. For each entry the protocol is the same:

1. A watch script lives at `scripts/check_<dep>_compat.py`.
2. A Celery beat entry polls the script on a defined cadence.
3. The script writes structured audit-trail JSON to
   `var/upstream-watch/<dep>-<timestamp>.json`.
4. When the script detects the watched event, the Celery task emits
   a notification (currently `mail_admins`; future enhancement:
   Slack / PagerDuty integration).
5. The operator runs a **manual verification** step before bumping
   the dependency in `requirements.txt` — watches never auto-upgrade.

Watches always exit 0 (they are NOT CI gates). They are pollers with
audit trails.

---

## 1. `django-cryptography` — Django 5 compatibility

### Watch script
`scripts/check_django_cryptography_compat.py`

### Beat schedule
`upstream-watch-django-cryptography` in `config/settings.py::CELERY_BEAT_SCHEDULE`:

```python
"upstream-watch-django-cryptography": {
    "task": "accounts.watch_django_cryptography_upstream",
    "schedule": _celery_crontab(hour=5, minute=0, day_of_week=1),  # Mondays 05:00 UTC
}
```

Lazy-guarded behind `CELERY_BEAT_ENABLED` (env var, default `"1"`).
Dev / CI lanes can disable by setting `CELERY_BEAT_ENABLED=0` —
upstream polling is silent in that case.

### Notification recipient
`mail_admins()` — recipients come from `settings.ADMINS`. Production
populates this from `ADMINS_EMAILS` env var.

### Current status (2026-05-18)
* **Pinned compatibility baseline:** `1.2.0` (predicted)
* **Known incompatible ceiling:** `1.1.0`
* **Reason for the watch:** Upstream `django-cryptography` 1.x
  imports `django.utils.baseconv`, removed in Django 5. Our
  `apps/accounts/legacy_hashes/encryption.py` reports the
  `internal_fernet_shim` backend until upstream lands a Django-5
  compatible release.

### Promotion procedure when compat lands
1. Receive the `mail_admins` email titled
   `"[RunMyCampus] django-cryptography Django-5 compat candidate"`.
2. Open the audit JSON at the path the email cites
   (`var/upstream-watch/django-cryptography-*.json`).
3. Pull the candidate version into a test environment:
   ```bash
   python -m venv .venv-test
   .venv-test/bin/pip install django-cryptography==<version>
   .venv-test/bin/python manage.py test apps.accounts
   ```
4. Run the full encryption round-trip suite:
   `apps/accounts/legacy_hashes/tests/test_encryption.py`.
5. If green, follow `docs/SECURITY_KEYS.md` §
   "Internal Fernet Shim Migration Plan" — re-encrypt existing
   ciphertexts under the upstream backend on next write
   (transparent decrypt under shim still works).
6. Open a PR bumping `requirements.txt`:
   `django-cryptography==<version>`.
7. After merge + deploy, the
   `apps/accounts/legacy_hashes/encryption.py::current_backend_name()`
   helper starts returning `"django_cryptography_1_2_plus"` instead
   of `"internal_fernet_shim"`.

---

## 2. `pynacl` — libsodium 1.0.19+ (informational)

### Watch script
None yet — the PyNaCl + libsodium combo we ship today
(`pynacl>=1.5,<2.0`) is **fully functional**; we are not blocked by
any upstream behaviour. This entry exists so a future watch can be
added without re-discovering the dependency.

### Why watch?
libsodium has periodically broken back-compat at the C-API layer
in the past. If libsodium 1.0.20+ ships a change that PyNaCl 2.x
takes a year to absorb, we want to know.

### Current status
* **Pinned range:** `>=1.5,<2.0`
* **Trigger to convert this to a real watch:** PyNaCl 2.0 release
  candidate appears on PyPI. At that point add
  `scripts/check_pynacl_compat.py` modeled on the
  django-cryptography watch.

### Promotion procedure (when watch is created)
Same shape as § 1: candidate-release email → test env install →
test suite → PR.

---

## 3. `drf-spectacular` — DRF 3.16 compat (informational)

### Watch script
None yet. drf-spectacular tracks DRF releases closely and we have
no blocker today.

### Why watch?
We rely on `@extend_schema` annotations across the
`apps/migration_cloud/api/` viewsets (zero-tolerance
`scan_drf_schema_coverage` gate). If a DRF 3.16 release breaks the
decorator semantics our coverage gate will trip CI immediately —
but we'd rather not be surprised.

### Current status
* **Pinned range:** see `requirements.txt`.
* **Trigger to convert this to a real watch:** DRF 3.16 release
  candidate on PyPI.

### Promotion procedure (when watch is created)
Same shape as § 1.

---

## Adding a new upstream watch

When a new dependency lands on the watch list:

1. Add a section above (use the § 1 template).
2. Create `scripts/check_<dep>_compat.py` modeled on
   `check_django_cryptography_compat.py`. Stdlib-only HTTP; bounded
   redirects + timeout + size cap; write audit JSON to
   `var/upstream-watch/<dep>-<timestamp>.json`.
3. Add a Celery beat entry behind `CELERY_BEAT_ENABLED`.
4. Add a Celery task in `apps/accounts/tasks.py` that runs the
   script and emails on the trigger event.
5. Add a test in `apps/accounts/tests/test_upstream_watch_*.py`
   asserting the audit JSON shape (the watch itself can be skipped
   over PyPI; the test verifies the local code paths).

---

## Audit retention

Audit JSON files under `var/upstream-watch/` are retained
indefinitely by default. A future enhancement could prune entries
older than 90 days, but the JSON is small (a few KB per run) and
the history is useful for "when did we first see version X?"
questions.
