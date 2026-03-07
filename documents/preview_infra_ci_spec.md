# Preview Infrastructure CI/CD Spec

This specification describes how to automate ephemeral preview environments for the School Management System so every pull request gains a sandboxed copy of the stack with synthetic data, a persistent “PREVIEW MODE” banner, and the RBAC controls we already surfaced in the admin.

## Goals
1. Spin up an isolated preview when a GitHub pull request is opened (Northflank/Vercel/Kubernetes).
2. Route preview traffic to the `sms_sandbox` database defined by `PREVIEW_DATABASE_URL`.
3. Seed the sandbox with AI-generated synthetic data instead of copying PII.
4. Surface the red “PREVIEW MODE – DATA WILL NOT BE SAVED” banner everywhere (admin + portal) and honor Act-As role switches.
5. Tear the preview environment down 24 h after the PR closes or merges.

## Platform
- **Runner**: GitHub Actions
- **Preview host**: Northflank (preferred) or Vercel/Kubernetes if required by team.
- **Build steps**:
  1. Checkout the PR branch.
  2. Run lint/tests as desired (optional).
  3. Build Docker images (app + any worker/queue).
  4. Deploy to an isolated Northflank project triggered by the PR slug.
  5. Inject environment variables:
     - `DJANGO_SETTINGS_MODULE=config.settings`
     - `PREVIEW_DATABASE_URL` pointing to a dedicated sandbox database (can be reused for multiple previews if namespaced).
     - `PREVIEW_MODE=true` (optional) to turn on the banner automatically.
  6. Run migrations against `PREVIEW_DATABASE_URL`.
  7. Seed synthetic data using the existing mock data loaders (e.g., `python manage.py seed --preview`) or a custom script that only produces fake students/teachers.

## Synthetic Data Mandate
* Never copy real student or guardian data—use faker routines or prerecorded JSON to populate required tables (students, classrooms, communications, etc.).
* Log a warning if any fixture relies on `SEED_REAL_DATA=true`; the default must be synthetic.
* Add an audit row to `apps.observability` or logging channel that the preview environment used synthetic data.

## Preview Access & RBAC
* Inject `X-Preview-Mode: true` header (or the session flag) into all requests so the banner and DB router stay active.
* Provide a temporary Super Admin account that can toggle Act-As roles inside the preview (our admin banner drop-down covers this).
* Ensure preview URLs are not public (restrict by GitHub PR ID or Basic Auth).

## Teardown Policy
* Add a GitHub Action job triggered on `pull_request.closed` that calls Northflank/Vercel/K8s API to:
  - Delete the preview deployment associated with the PR.
  - Revoke secrets for that preview.
* Automatically schedule a 24-hour TTL on every preview environment so leaked deployments are automatically destroyed.

## Documentation
Link this spec from the admin preview banner (`documents/preview_infra_ci_spec.md`) and ensure the synthetic-data warning text (`templates/admin/components/theme_preview_section.html`) cites the CI/CD page so operators know where the sandbox came from.
