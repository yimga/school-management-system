<!--
  RunMyCampus — THIRD-PARTY NOTICES
  Copyright (C) 2026 RunMyCampus.
  This NOTICE file accompanies the AGPL-3.0-or-later platform (see LICENSE).
  It records third-party code and DATA whose licenses require attribution
  to be carried with the software. It is not exhaustive of all dependencies
  (the overwhelming majority are MIT/BSD/Apache and need no notice) — it
  lists the items where an explicit attribution or license statement is
  legally required when this software, or the data it bundles, is redistributed.
-->

# Third-Party Notices

RunMyCampus depends on open-source software and open data sets. The bulk of the
dependency tree is permissively licensed (MIT / BSD / Apache-2.0 / ISC / PSF)
and carries its own license text in each package; see
[`docs/OPEN_SOURCE_POSTURE_AUDIT_2026_06_03.md`](docs/OPEN_SOURCE_POSTURE_AUDIT_2026_06_03.md)
for the full posture review.

This file records the dependencies whose licenses **require an attribution or
notice to travel with the product** — namely one MIT code dependency whose
package metadata historically lacked a license declaration, and two bundled
**open-data** sets (geographic data) that are attribution-licensed.

---

## Code

### json-logic (Python)

- **Package:** `json-logic` (PyPI), pinned `json-logic>=0.6.0`; resolved in this
  environment to **0.6.3**.
- **License:** **MIT** — confirmed from the installed wheel metadata
  (`json_logic-0.6.3.dist-info/METADATA`: `License: MIT`,
  `Classifier: License :: OSI Approved :: MIT License`).
- **Upstream:** [nadirizr/json-logic-py](https://github.com/nadirizr/json-logic-py),
  a Python port of [jwadhams/json-logic-js](https://github.com/jwadhams/json-logic-js)
  (also MIT).
- **Used by:** the Nuance Engine — safe, per-school JSON-Logic rule execution
  (see `requirements.txt`, "Nuance Engine (Section 7)").

> Note: the OSS posture audit (2026-06-03) flagged this dependency's license as
> "UNKNOWN" because earlier releases on the `>=0.6.0` range shipped with blank
> license metadata. The installed release (0.6.3) declares MIT explicitly, so the
> dependency is confirmed MIT — **no replacement is required.** If the resolved
> version is ever pinned lower, re-confirm the metadata of that exact version.

---

## Data

The following packages bundle geographic **data sets** (not just code). The code
that reads them is permissively licensed, but the **data** is attribution-licensed
and the attribution below must be retained wherever this product (or that data) is
redistributed or exposed in a network service.

### GeoLite2 (via `geoip2`)

- **Package:** `geoip2>=5.0` (MaxMind's reader library, Apache-2.0 code). **No
  GeoLite2 database is bundled in this repo.** The former `maxminddb-geolite2==2018.703`
  pin (which shipped a 2018-vintage GeoLite2 DB) was **removed** during the
  open-source-first audit: nothing imported it, the snapshot was ~8 years stale,
  and dropping it eliminates the licensing ambiguity below.
- **Data license (if you supply your own DB):** MaxMind relicensed GeoLite2 on
  **30 December 2019**. Snapshots **before** that date were
  **Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)**; **current**
  GeoLite2 databases are distributed only under the **MaxMind GeoLite2 End User
  License Agreement** (free account + license key required, and the EULA
  requires deleting databases within 30 days of a new release). If you enable
  geo-IP by pointing `GEOIP_PATH` at a freshly downloaded GeoLite2/GeoIP2 file,
  that EULA — and the attribution below — applies.
- **Required attribution (when a MaxMind DB is in use):**

  > This product includes GeoLite2 data created by MaxMind, available from
  > https://www.maxmind.com.

- **Used by:** optional IP→country resolution for compliance access control
  (`apps/compliance/access_control.py`, `apps/accounts/security_audit.py`). This
  path is **disabled by default** — it activates only when `GEOIP_PATH` is
  configured; on the default deployment (e.g. Render) it returns `None` and
  callers fall back.

### GeoNames (via `geonamescache`)

- **Package:** `geonamescache>=2.0.0` (bundles a snapshot of GeoNames data).
- **Data license:** the GeoNames database is licensed under
  **Creative Commons Attribution 4.0 International (CC BY 4.0)**.
- **Required attribution:**

  > This product includes data from GeoNames (https://www.geonames.org/),
  > licensed under Creative Commons Attribution 4.0 (CC BY 4.0).

- **Used by:** offline country / city / currency reference data
  (`apps/registries/currency.py`, `apps/siteconfig` feature-control catalogs).

---

## Maintenance

- When adding a dependency that bundles **data** (geographic, postal, dictionary,
  etc.) or one whose code license requires a notice (e.g. attribution-style or
  weak-copyleft terms that must travel with binaries), add it here.
- Permissively licensed *code* dependencies (MIT/BSD/Apache/ISC/PSF) do **not**
  need an entry here — their license text ships inside each package.
- The full dependency inventory and SBOM live in
  [`artifacts/security/sbom-baseline.json`](artifacts/security/sbom-baseline.json).
