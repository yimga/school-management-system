# Developer platform / SDK / extension DX

Extension manifest, app SDK shape, local dev workflow, webhooks, sandbox, certification, and publisher docs (Execution Master §3.9, §7).

## Requirements

- **Extension manifest design:** Canonical manifest schema for marketplace apps (name, version, scopes, widgets, workflow_actions, integration_adapters); versioned and auditable.
- **App SDK shape:** Clear API for apps to read tenant context (scoped), call platform APIs, and register widgets/workflows; no direct DB or cross-tenant access.
- **Local extension dev workflow:** Run and test an app against a local or staging tenant; sandbox mode; no production data.
- **Webhook testing tools:** Simulate webhooks; verify signing and payload; audit in control plane.
- **Sandbox tooling:** Isolated execution for app code; timeout and scope limits; see marketplace sandbox_inspector.
- **Certification flow:** Review and approve apps before publish; compatibility harness; version compatibility matrix.
- **Compatibility harness:** Automated checks for app vs platform version; document in marketplace.
- **Publisher documentation system:** Docs for building and publishing apps; API reference; manifest reference.

## Implementation direction

- Manifest and SDK: align with existing `apps.marketplace` models (App, AppInstallation, manifest JSON); document manifest schema and required fields.
- Local dev: use sandbox mode and tenant-scoped install; document in developer_portal / developer_sdk templates and any runbooks.
- Webhooks and certification: implement or extend in marketplace app lifecycle; audit and testing tools in control plane.
- No new god-apps: keep developer surface in marketplace and a dedicated docs/ or developer portal area; single governed path.

## References

- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md) (Law 6, Law 9)
- apps/marketplace (models, views, sandbox_inspector)
- templates/schools/developer_portal.html, developer_sdk.html
- [PLATFORM_ENGINES.md](PLATFORM_ENGINES.md)
