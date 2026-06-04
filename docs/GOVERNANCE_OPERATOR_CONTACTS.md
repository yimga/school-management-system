# Governance operator contacts

Maintainer checklist for open-source governance channels referenced in-repo. These
cannot be proven monitored from code alone — operators must verify delivery and
response SLAs out-of-band.

## Current workspace status (refresh with `gh` / verifier)

| Repo | Status (typical for this fork) | What to do |
| --- | --- | --- |
| `yimga/school-management-system` | **Public** (SDK + `origin` aligned) | Enable Issues/Discussions; run `--require-public` after visibility changes |
| `runmycampus/runmycampus` | Legacy SDK slug — retargeted to `yimga/...` | Create org repo later if you migrate canonical hosting |

Authenticated check (maintainer machine):

```bash
gh repo view yimga/school-management-system --json visibility,isPrivate,url
gh repo view runmycampus/runmycampus --json visibility,isPrivate,url  # fails if repo missing
python scripts/verify_open_source_github_repo_visibility.py --write
```

## Step 1 — GitHub visibility (pick one path)

### Path A — Publish this fork (fastest for `origin`)

1. GitHub → **yimga/school-management-system** → **Settings** → **General** → **Danger Zone** → **Change repository visibility** → **Public**.
2. Enable **Issues** (and **Discussions** if you linked them in `config.yml`).
3. Re-run evidence + gate:

```bash
python scripts/verify_open_source_github_repo_visibility.py --write
python scripts/verify_open_source_github_repo_visibility.py --require-public --repo yimga/school-management-system
```

CLI equivalent (requires confirm): `gh repo edit yimga/school-management-system --visibility public`

4. **Align SDK metadata** so PyPI/npm issue links match the public repo (until then, `--require-public` still fails on `runmycampus/runmycampus` discovered from `packages/*/pyproject.toml`). Update `Repository` / `Issues` in:

- `packages/runmycampus-webhook-verifier-py/pyproject.toml`
- `packages/runmycampus-webhook-verifier-js/package.json`
- `sdk/pyproject.toml` and `sdk/js/package.json` (if present)

Then run `verify_open_source_github_repo_visibility.py --write` and `--require-public` again.

### Path B — Org canonical repo (`runmycampus/runmycampus`)

1. Create **runmycampus/runmycampus** (or rename/transfer), push platform tree, make **Public**, enable Issues.
2. Keep SDK URLs as-is; run `--require-public` (checks discovered canonical + workspace origin).

Do **not** publish SDKs pointing at a private or missing repo.

## Mailboxes

| Channel | Address | Referenced in | Operator action |
| --- | --- | --- | --- |
| Code of Conduct enforcement | conduct@runmycampus.com | [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Inbox monitored; documented escalation path; 48h ack target for reports |
| Security disclosure | security@runmycampus.com | [SECURITY.md](../SECURITY.md) | Inbox monitored; no auto-reply leaking stack traces; coordinate with SECURITY.md SLA |

## Step 2 — Verify conduct@ and security@ (quarterly)

From a mailbox **outside** the runmycampus.com org (or your personal email):

| To | Subject (example) | Body (minimal) | Pass criteria |
| --- | --- | --- | --- |
| conduct@runmycampus.com | `[governance-check] CoC inbox` | "Synthetic delivery test — no action required." | Delivered to monitored inbox within 24h; not bounced |
| security@runmycampus.com | `[governance-check] SECURITY inbox` | "Synthetic delivery test — not a vulnerability report." | Same |

Then:

1. Confirm SPF/DKIM/DMARC on the domain (Google Workspace / M365 / forwarder docs).
2. Note date + verifier initials in your **internal** runbook (not required in git).
3. Optional: reply from the on-call alias so future reporters see a human path.

Suggested cadence: repeat quarterly and after any DNS or mail-provider change.

## GitHub issue template URLs

[`.github/ISSUE_TEMPLATE/config.yml`](../.github/ISSUE_TEMPLATE/config.yml) contact links use the **workspace `git remote origin`** slug (`yimga/school-management-system` in this fork). That is correct when this repository is the active contribution target.

Published SDK metadata (PyPI/npm) points at **`runmycampus/runmycampus`** for issues and changelog links. If the canonical org repo differs from this fork:

- Either make `runmycampus/runmycampus` public and enable Issues/Discussions there, **or**
- Update SDK `Repository` / `Issues` URLs in `packages/*` and `sdk/*` to match the public slug you actually use.

Evidence JSON: run `python scripts/verify_open_source_github_repo_visibility.py --write`.

## Related verifiers

```bash
python scripts/verify_open_source_posture.py
python scripts/verify_open_source_posture.py --skip-github-network  # offline CI
```

Audit ledger: [OPEN_SOURCE_POSTURE_AUDIT_2026_06_03.md](OPEN_SOURCE_POSTURE_AUDIT_2026_06_03.md).
