<!--
  RunMyCampus — README
  Copyright (C) 2026 RunMyCampus.
  Licensed under the GNU Affero General Public License v3.0 or later (see LICENSE).
-->

# RunMyCampus — the open Education OS

RunMyCampus is a multi-tenant school-management platform (the "Education OS"):
admissions, academics, attendance, finance/fees, communication, reporting, and
an operator control plane — built to run a real school end to end.

It is **open source under the [GNU AGPL-3.0-or-later](LICENSE)**, and built to be
**self-hosted** — on a single cheap VPS to get started, and to **scale out to
large / edge infrastructure** without a rewrite.

---

## Why open source

We want schools — including under-resourced ones and those in regions the big
vendors ignore — to be able to **run, inspect, and own** their own student
information system. AGPL keeps it that way: anyone who runs a modified
RunMyCampus as a network service must share their changes, so improvements flow
back to everyone instead of disappearing into closed forks.

- **Platform & companion clients:** AGPL-3.0-or-later (this repo).
- **Integration SDKs** (`packages/runmycampus-webhook-verifier-*`): Apache-2.0,
  so you can embed them in *any* project, open or closed, with no copyleft.
- **Commercial licensing:** organisations that cannot accept AGPL obligations
  can obtain a separate commercial license — contact the maintainers.

## Design principle: cheap to start, built to scale

Every external dependency is **swappable by environment variable** (12-factor),
with a free/local default and a scale-out path — so you spend nothing on
infrastructure until you need to, and never hit a rewrite when you do:

| Concern | Default (free / local) | Scale-out path (by env) |
|---|---|---|
| Database | SQLite | PostgreSQL (`DATABASE_URL`), read-replicas per region |
| Cache / queue | in-memory + inline tasks | Redis/Valkey (`REDIS_URL`), Celery workers |
| Media storage | local filesystem | S3-compatible — self-hosted **MinIO**, R2, B2, S3, or an edge bucket (`MEDIA_STORAGE_BACKEND=s3`) |
| Email | console / any SMTP | self-hosted relay (Postal/Postfix) or a provider, all via `EMAIL_*` |
| AI / LLM | rules + local **Ollama** (`RMC_DEPLOYMENT_PROFILE=edge`) | cloud models via an OpenAI-compatible gateway |
| Errors / metrics | off | self-hosted **GlitchTip** (Sentry-compatible) via `SENTRY_DSN`; Prometheus `/metrics/` |
| Edge / regions | single host | region header routing, per-region DB replicas, CDN media |

See [docs/SELF_HOSTING_AND_EXTERNAL_DEPENDENCIES_BACKLOG.md](docs/SELF_HOSTING_AND_EXTERNAL_DEPENDENCIES_BACKLOG.md)
and [docs/OPEN_SOURCE_POSTURE_AUDIT_2026_06_03.md](docs/OPEN_SOURCE_POSTURE_AUDIT_2026_06_03.md)
for the full self-host story and the FOSS-readiness audit.

## Stack

Django 5.2 · PostgreSQL · Celery · Redis (optional) · DRF · WhiteNoise ·
multi-tenant (subdomain) · PWA · OneRoster/LTI/SAML interop.

## Quick start (local, zero external services)

```bash
cd beta/school-management-system
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on *nix
pip install -r requirements.txt
cp .env.example .env                                # all-blank defaults run locally
python manage.py migrate
python manage.py runserver
```

With everything blank in `.env`, the app runs on SQLite + local-filesystem media
+ inline background tasks + console email — no Postgres, Redis, or cloud account
needed. Fill in `.env` to scale up (see the table above and `.env.example`).

## Tests

```bash
python manage.py test <labels> --settings=config.settings_test --parallel=1
```

## Contributing & security

- [CONTRIBUTING.md](CONTRIBUTING.md) — how to propose changes (incl. the DCO sign-off).
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community standards.
- [SECURITY.md](SECURITY.md) — how to report a vulnerability privately.

## License

GNU Affero General Public License v3.0 or later — see [LICENSE](LICENSE).
Copyright (C) 2026 RunMyCampus.

Third-party code and open-data attributions (json-logic, GeoLite2, GeoNames) are
recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
