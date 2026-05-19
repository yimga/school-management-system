# Legacy hash intake — vendor coverage matrix (v3.34.0)

This document records which SIS vendor extractors carry an explicit
"password last set" / "password created" timestamp on their stored
hash row, and which do not. The intake helper
`apps.migration_cloud.services.legacy_hash_intake.store_legacy_hash`
accepts a `legacy_hash_created_at_source` kwarg; when present, the
sunset clock anchors there instead of "now". When absent, the anchor
defaults to `timezone.now()` and the 12-month sunset clock starts at
intake.

**Why this matters.** A hash that has been "stale" at the vendor for
11 months should not get a fresh 12-month grace clock on intake — the
operator who imports it is inheriting near-expired credential equity.
The vendor-provided timestamp lets the sunset task fire on the right
cohort.

## Strictness vocabulary

| Strictness | Meaning |
|---|---|
| **YES (strict)** | Vendor exposes a column whose contract is specifically "password last changed". The value moves only when the user (or admin acting on the user's behalf) changes the password. |
| **PARTIAL (mtime approximation)** | Vendor exposes a row mtime (`updated_at` / `user-modified-time` / `Last_Modified`) that *may* be a password change but could also be a profile-edit / role-flip / contact-info update. We treat this as "best available signal", document the limitation, and surface it in the intake structured log so operators can audit drift. |
| **PARTIAL (per-tenant opt-in)** | Vendor only surfaces the timestamp when the customer has added it to their custom report or has admin-tier API access. We pass `None` for tenants that lack the field. |
| **NO** | Vendor surface does not expose any password-change signal. Intake anchors to `timezone.now()` (12-month clock starts at intake). |
| **NO (write-blocked)** | In addition to NO above, write paths to this vendor are blocked by `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` pending counsel sign-off; the read path is safe-DOM-only. |

## Coverage matrix (v3.34.0)

| Vendor | Verifier slug(s) | Carries "password last set" timestamp? | Field used | Strictness |
|---|---|---|---|---|
| **PowerSchool** | `pbkdf2_sha512` | YES (when present in the user row) | `Users.PasswordChanged` (PostgreSQL/Oracle column) or `Teachers.PasswordChanged`. Sometimes NULL on legacy rows — extractor falls back to `timezone.now()`. | YES (strict) |
| **Blackbaud SKY (OnRecord / OnBoard)** | `bcrypt`, `blackbaud_bcrypt` | PARTIAL (v3.34.0) — uses `user-modified-time` as approximation | `userModifiedTime` / `user-modified-time`; fall back to `createdDate` / `created-date` | PARTIAL (mtime approximation) |
| **Veracross** | `veracross_bcrypt` | PARTIAL (v3.34.0) — only when customer's custom report exposes it | `pwd_last_changed_dt` / `Password_Last_Changed` (per-tenant opt-in); fall back to `Last_Modified` / `Date_Created` | PARTIAL (per-tenant opt-in; mtime fallback) |
| **Alma SIS** | `alma_bcrypt` | YES (v3.34.0) — `SchoolUser.passwordUpdatedAt` exposed in GraphQL schema (promoted from PARTIAL) | `passwordUpdatedAt`; fall back to `updatedAt` then `createdAt` | YES (strict when `passwordUpdatedAt` is non-null; PARTIAL fallback otherwise) |
| **FACTS SIS** | `bcrypt`, `pbkdf2_sha1` | NO (FACTS ASPX surface does not expose password timestamps) | n/a — extractor passes `None`, intake anchors to `timezone.now()`. Read-path safe-DOM only per v3.33.0; **write path counsel-blocked** per `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md`. | NO (write-blocked) |
| **Skyward** | `bcrypt`, `skyward_salted_sha512` | NO (Skyward ASPX surface does not expose password timestamps) | n/a — extractor passes `None`, intake anchors to `timezone.now()`. Read-path safe-DOM only per v3.33.0; **write path counsel-blocked** per `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md`. | NO (write-blocked) |

## How extractors should wire this

```python
from apps.migration_cloud.services.legacy_hash_intake import store_legacy_hash

# PowerSchool example (Users.PasswordChanged available):
store_legacy_hash(
    user=user,
    hash_value=row["password_hash"],
    algorithm="pbkdf2_sha512",
    params_dict={"salt": row["password_salt"], "iterations": 120000},
    source_vendor="powerschool",
    legacy_hash_created_at_source=row.get("password_changed_at"),  # may be None
)

# Blackbaud / Veracross / Alma — read the optional vendor-emitted
# `legacy_hash_created_at` field from the companion bundle row:
store_legacy_hash(
    user=user,
    hash_value=row["hash"],
    algorithm="bcrypt",
    params_dict={},
    source_vendor="blackbaud",
    legacy_hash_created_at_source=row.get("legacy_hash_created_at"),  # may be missing
)

# FACTS / Skyward — no anchor available; omit the kwarg:
store_legacy_hash(
    user=user,
    hash_value=row["hash"],
    algorithm="bcrypt",
    params_dict={},
    source_vendor="facts",
    # legacy_hash_created_at_source omitted — defaults to timezone.now()
)
```

## Defensive behavior

The intake helper applies these coercions in v3.34.0:

* If the vendor returns a NAIVE datetime, the intake helper coerces it
  to aware via `timezone.make_aware`. If that fails (rare — bad tzdata
  on the host), it falls back to `timezone.now()` rather than raising.
* If the vendor returns a value that isn't a `datetime` or an
  ISO-8601 string, intake silently falls back to `timezone.now()`. The
  structured `legacy_hash_intake_stored` log line carries
  `anchor_from_vendor=False` so operators can spot the regression in
  aggregate logs.
* **v3.34.0** — ISO-8601 string anchors from the JSON companion bundle
  are accepted; the helper normalizes trailing "Z" to "+00:00" and
  parses via `datetime.fromisoformat`. Malformed strings fall back to
  `timezone.now()` rather than raising. The structured log includes
  `anchor_parsed_from_string=True` for these.
* **v3.34.0 — future-date clamp** — if the vendor anchor lies more than
  60 seconds in the future (clock skew on the vendor server), the
  helper clamps to `timezone.now()` and emits a structured
  `legacy_hash_intake_anchor_clamped_future` warning carrying the
  observed skew in seconds. NEVER contains hash, salt, or password
  material. The 60-second tolerance avoids noisy warnings for rows
  generated within the same minute as intake.

## Audit log

Every intake call emits a structured `legacy_hash_intake_stored` log
line with:

* `anchor_from_vendor: bool` — caller passed the kwarg
* `anchor_parsed_from_string: bool` — anchor parsed from ISO-8601 (v3.34.0)
* `anchor_clamped_future: bool` — anchor was clamped to now() (v3.34.0)

To survey coverage on a running tenant:

```bash
# Count vendor-anchored vs now()-anchored intakes by source vendor:
grep legacy_hash_intake_stored logs/django.log \
  | jq -r '"\(.source_vendor),\(.anchor_from_vendor)"' \
  | sort | uniq -c

# Survey clock-skew clamps:
grep legacy_hash_intake_anchor_clamped_future logs/django.log \
  | jq -r '"\(.source_vendor),\(.skew_seconds)"' \
  | sort | uniq -c
```

Expected ratios per the matrix above: PowerSchool + Alma should be
majority `True` for active rows; Blackbaud + Veracross will be
`True` only when their PARTIAL paths fire; FACTS / Skyward should be
100 % `False`.

## See also

* `docs/SECURITY_KEYS.md` — encryption keys + automated rotation
* `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` — counsel docket
  for FACTS / Skyward write-path unblocking (new in v3.34.0)
* `apps/migration_cloud/services/legacy_hash_intake.py` — canonical
  write site
* `apps/accounts/legacy_hashes/sunset_task.py` — 12-month sunset FSM
